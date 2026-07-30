#!/usr/bin/env python3
"""Build the walking-only 64-frame animation from a persistent four-limb rig.

Unlike the legacy pipeline, this script never interpolates complete cat images.
The body and each named limb are extracted once from the generated rig sheet,
then composited from continuous joint trajectories. Limb count and identity
therefore cannot change between frames.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from process_animation_assets import (
    CANVAS_SIZE,
    TARGET_BASELINE_Y,
    chroma_to_bgra,
    fur_median_bgr,
    normalize_color,
    soften,
)


RUNTIME_FRAMES = 64
KEYFRAME_STRIDE = 8
BODY_SCALE = 0.60
LEG_SCALE = 0.50
BODY_TOP = 257
BODY_CENTER_X = 256

# One cyclic gait sampled at the eight semantic poses in walk_spec.json.
# Positive rotation moves the paw forward (right) in OpenCV image coordinates.
ANGLE_DEGREES = np.array((13, 9, 3, -5, -13, -10, 0, 10), dtype=np.float32)
LIFT_PX = np.array((0, 0, 0, 0, 1, 12, 24, 14), dtype=np.float32)
LIMB_PHASE_OFFSETS = {"LF": 0, "RF": 4, "LH": 6, "RH": 2}
LIMB_ANCHOR_X = {"LF": 330, "RF": 306, "LH": 193, "RH": 169}
COMPONENT_ORDER = ("body", "LF", "RF", "LH", "RH")


def clear_pngs(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for path in directory.glob("*.png"):
        path.unlink()


def alpha_bounds(frame: np.ndarray, threshold: int = 20) -> tuple[int, int, int, int]:
    ys, xs = np.where(frame[:, :, 3] > threshold)
    if len(xs) == 0:
        raise ValueError("frame contains no visible component")
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def extract_components(sheet_path: Path) -> dict[str, np.ndarray]:
    sheet = cv2.imread(str(sheet_path), cv2.IMREAD_COLOR)
    if sheet is None:
        raise ValueError(f"unable to read {sheet_path}")
    rgba = chroma_to_bgra(sheet)
    mask = (rgba[:, :, 3] > 20).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    candidates: list[tuple[int, int, int, int, int, int]] = []
    for label in range(1, count):
        x, y, width, height, area = (int(value) for value in stats[label])
        if area >= 5_000:
            candidates.append((label, x, y, width, height, area))
    if len(candidates) != 5:
        raise ValueError(f"expected five rig components, found {len(candidates)}")

    # The body is largest. Remaining parts sort by row then x:
    # LF, RF on the upper row; LH, RH on the lower row.
    body_entry = max(candidates, key=lambda item: item[5])
    limb_entries = sorted(
        (item for item in candidates if item != body_entry),
        key=lambda item: (item[2], item[1]),
    )
    entries = [body_entry, *limb_entries]
    components: dict[str, np.ndarray] = {}
    for name, (label, x, y, width, height, _) in zip(
        COMPONENT_ORDER, entries, strict=True
    ):
        padding = 3
        left, top = max(0, x - padding), max(0, y - padding)
        right = min(rgba.shape[1], x + width + padding)
        bottom = min(rgba.shape[0], y + height + padding)
        component = rgba[top:bottom, left:right].copy()
        component_labels = labels[top:bottom, left:right]
        component[component_labels != label] = 0
        components[name] = component
    return components


def resize_component(component: np.ndarray, scale: float) -> np.ndarray:
    return cv2.resize(
        component,
        (
            max(1, round(component.shape[1] * scale)),
            max(1, round(component.shape[0] * scale)),
        ),
        interpolation=cv2.INTER_AREA,
    )


def alpha_over(background: np.ndarray, foreground: np.ndarray) -> np.ndarray:
    foreground_alpha = foreground[:, :, 3:4].astype(np.float32) / 255
    background_alpha = background[:, :, 3:4].astype(np.float32) / 255
    output_alpha = foreground_alpha + background_alpha * (1 - foreground_alpha)
    premultiplied = (
        foreground[:, :, :3].astype(np.float32) * foreground_alpha
        + background[:, :, :3].astype(np.float32)
        * background_alpha
        * (1 - foreground_alpha)
    )
    rgb = np.divide(
        premultiplied,
        np.maximum(output_alpha, 1 / 255),
        out=np.zeros_like(premultiplied),
        where=output_alpha > 0,
    )
    return np.concatenate((rgb, output_alpha * 255), axis=2).astype(np.uint8)


def place(
    canvas: np.ndarray,
    component: np.ndarray,
    left: int,
    top: int,
) -> np.ndarray:
    layer = np.zeros_like(canvas)
    source_left, source_top = max(0, -left), max(0, -top)
    source_right = min(component.shape[1], CANVAS_SIZE - left)
    source_bottom = min(component.shape[0], CANVAS_SIZE - top)
    if source_right <= source_left or source_bottom <= source_top:
        return canvas
    target_left, target_top = max(0, left), max(0, top)
    target_right = target_left + source_right - source_left
    target_bottom = target_top + source_bottom - source_top
    layer[target_top:target_bottom, target_left:target_right] = component[
        source_top:source_bottom, source_left:source_right
    ]
    return alpha_over(canvas, layer)


def translate(frame: np.ndarray, dx: int, dy: int) -> np.ndarray:
    return cv2.warpAffine(
        frame,
        np.float32(((1, 0, dx), (0, 1, dy))),
        (CANVAS_SIZE, CANVAS_SIZE),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )


def align_baseline(frame: np.ndarray) -> np.ndarray:
    _, _, _, bottom = alpha_bounds(frame)
    return translate(frame, 0, TARGET_BASELINE_Y - bottom)


def cyclic_sample(values: np.ndarray, phase: float) -> float:
    lower = int(np.floor(phase)) % len(values)
    fraction = phase - np.floor(phase)
    upper = (lower + 1) % len(values)
    eased = fraction * fraction * (3 - 2 * fraction)
    return float(values[lower] * (1 - eased) + values[upper] * eased)


def render_limb(
    component: np.ndarray,
    name: str,
    master_phase: float,
) -> np.ndarray:
    phase = (master_phase + LIMB_PHASE_OFFSETS[name]) % 8
    angle = cyclic_sample(ANGLE_DEGREES, phase)
    lift = cyclic_sample(LIFT_PX, phase)
    anchor_x = LIMB_ANCHOR_X[name]
    pivot_y = 305 if name in {"LF", "RF"} else 319

    layer = np.zeros((CANVAS_SIZE, CANVAS_SIZE, 4), dtype=np.uint8)
    pivot_in_component = (component.shape[1] // 2, 5)
    layer = place(
        layer,
        component,
        anchor_x - pivot_in_component[0],
        pivot_y - pivot_in_component[1],
    )
    rotated = cv2.warpAffine(
        layer,
        cv2.getRotationMatrix2D((anchor_x, pivot_y), angle, 1.0),
        (CANVAS_SIZE, CANVAS_SIZE),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )
    _, _, _, bottom = alpha_bounds(rotated)
    return translate(rotated, 0, round(TARGET_BASELINE_Y - lift - bottom))


def render_body(component: np.ndarray, frame_index: int) -> np.ndarray:
    # A one-pixel closed bob gives life without reintroducing anchor jitter.
    bob = round(np.sin(frame_index / RUNTIME_FRAMES * np.pi * 4))
    layer = np.zeros((CANVAS_SIZE, CANVAS_SIZE, 4), dtype=np.uint8)
    return place(
        layer,
        component,
        BODY_CENTER_X - component.shape[1] // 2,
        BODY_TOP + bob,
    )


def composite_on_green(frame: np.ndarray) -> np.ndarray:
    alpha = frame[:, :, 3:4].astype(np.float32) / 255
    green = np.zeros_like(frame[:, :, :3], dtype=np.float32)
    green[:, :, 1] = 255
    return np.clip(frame[:, :, :3] * alpha + green * (1 - alpha), 0, 255).astype(
        np.uint8
    )


def write_sheet(path: Path, frames: list[np.ndarray], columns: int) -> None:
    cell = 256
    rows = (len(frames) + columns - 1) // columns
    sheet = np.zeros((rows * cell, columns * cell, 3), dtype=np.uint8)
    sheet[:, :, 1] = 255
    for index, frame in enumerate(frames):
        row, column = divmod(index, columns)
        sheet[row * cell : (row + 1) * cell, column * cell : (column + 1) * cell] = (
            cv2.resize(composite_on_green(frame), (cell, cell), interpolation=cv2.INTER_AREA)
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), sheet):
        raise ValueError(f"unable to write {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--parts",
        type=Path,
        default=Path("work/walking/walking_render_v2/walking_rig_parts_green.png"),
    )
    parser.add_argument(
        "--runtime-output",
        type=Path,
        default=Path("src/assets/pet/walking"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/walking"),
    )
    parser.add_argument(
        "--target-color-frame",
        type=Path,
        default=Path("src/assets/pet/sitting/00.png"),
    )
    args = parser.parse_args()

    components = extract_components(args.parts)
    components["body"] = resize_component(components["body"], BODY_SCALE)
    for name in ("LF", "RF", "LH", "RH"):
        components[name] = resize_component(components[name], LEG_SCALE)

    target_frame = cv2.imread(str(args.target_color_frame), cv2.IMREAD_UNCHANGED)
    if target_frame is None or target_frame.shape[2] != 4:
        raise ValueError(f"unable to read target color frame {args.target_color_frame}")
    target_median = fur_median_bgr(target_frame)

    frames: list[np.ndarray] = []
    for frame_index in range(RUNTIME_FRAMES):
        phase = frame_index / RUNTIME_FRAMES * 8
        canvas = np.zeros((CANVAS_SIZE, CANVAS_SIZE, 4), dtype=np.uint8)
        # Far limbs first, near limbs second, locked torso last. The torso hides
        # all joint caps and makes the four attachment points visually stable.
        for name in ("RF", "RH", "LF", "LH"):
            canvas = alpha_over(
                canvas,
                render_limb(components[name], name, phase),
            )
        canvas = alpha_over(canvas, render_body(components["body"], frame_index))
        frames.append(
            align_baseline(normalize_color(soften(canvas), target_median))
        )

    clear_pngs(args.runtime_output)
    args.output.mkdir(parents=True, exist_ok=True)
    for index, frame in enumerate(frames):
        path = args.runtime_output / f"{index:02d}.png"
        if not cv2.imwrite(str(path), frame):
            raise ValueError(f"unable to write {path}")

    keyframes = frames[::KEYFRAME_STRIDE]
    for index, frame in enumerate(keyframes, start=1):
        path = args.output / f"walking_{index:02d}.png"
        if not cv2.imwrite(str(path), frame):
            raise ValueError(f"unable to write {path}")
    write_sheet(args.output / "walking_keyframes_sheet.png", keyframes, 4)
    write_sheet(args.output / "walking_runtime_sheet.png", frames, 8)

    preview = cv2.Animation()
    preview.frames = frames
    preview.durations = [42] * RUNTIME_FRAMES
    preview.loop_count = 0
    preview.bgcolor = (0, 255, 0, 255)
    if not cv2.imwriteanimation(str(args.output / "walking_preview.webp"), preview):
        raise ValueError("unable to write walking preview")

    metadata = {
        "method": "persistent five-layer walking rig; no whole-image optical flow",
        "runtimeFrames": RUNTIME_FRAMES,
        "fps": 24,
        "cycleSeconds": round(RUNTIME_FRAMES / 24, 4),
        "keyframes": [f"walking_{index:02d}.png" for index in range(1, 9)],
        "limbPhaseOffsets": LIMB_PHASE_OFFSETS,
        "renderOrder": ["RF", "RH", "LF", "LH", "body"],
        "bodyScale": BODY_SCALE,
        "legScale": LEG_SCALE,
        "baselineY": TARGET_BASELINE_Y,
    }
    (args.output / "walking_render_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
