#!/usr/bin/env python3
"""Build the final 25-frame walking animation from a dense video-driven sheet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from process_animation_assets import (
    CANVAS_SIZE,
    TARGET_BASELINE_Y,
    TARGET_CENTER_X,
    alpha_bounds,
    chroma_to_bgra,
    fur_median_bgr,
    keep_primary_subject,
    normalize_color,
    soften,
    translate,
)


FRAME_COUNT = 25
SHEET_COLUMNS = 5
SHEET_ROWS = 5


def clear_pngs(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for path in directory.glob("*.png"):
        path.unlink()


def split_sheet(path: Path) -> list[np.ndarray]:
    sheet = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if sheet is None:
        raise ValueError(f"unable to read {path}")
    height, width = sheet.shape[:2]
    frames: list[np.ndarray] = []
    for index in range(FRAME_COUNT):
        row, column = divmod(index, SHEET_COLUMNS)
        left = round(column * width / SHEET_COLUMNS)
        right = round((column + 1) * width / SHEET_COLUMNS)
        top = round(row * height / SHEET_ROWS)
        bottom = round((row + 1) * height / SHEET_ROWS)
        frames.append(keep_primary_subject(chroma_to_bgra(sheet[top:bottom, left:right])))
    return frames


def place_and_align(cell: np.ndarray, scale: float) -> np.ndarray:
    resized = cv2.resize(
        cell,
        (
            max(1, round(cell.shape[1] * scale)),
            max(1, round(cell.shape[0] * scale)),
        ),
        interpolation=cv2.INTER_AREA,
    )
    canvas = np.zeros((CANVAS_SIZE, CANVAS_SIZE, 4), dtype=np.uint8)
    left = (CANVAS_SIZE - resized.shape[1]) // 2
    top = (CANVAS_SIZE - resized.shape[0]) // 2
    source_left, source_top = max(0, -left), max(0, -top)
    source_right = min(resized.shape[1], CANVAS_SIZE - left)
    source_bottom = min(resized.shape[0], CANVAS_SIZE - top)
    target_left, target_top = max(0, left), max(0, top)
    target_right = target_left + source_right - source_left
    target_bottom = target_top + source_bottom - source_top
    canvas[target_top:target_bottom, target_left:target_right] = resized[
        source_top:source_bottom, source_left:source_right
    ]

    subject_left, _, subject_right, subject_bottom = alpha_bounds(canvas)
    return translate(
        canvas,
        round(TARGET_CENTER_X - (subject_left + subject_right) / 2),
        TARGET_BASELINE_Y - subject_bottom,
    )


def write_frame(path: Path, frame: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), frame):
        raise ValueError(f"unable to write {path}")


def clean_transparency(frame: np.ndarray) -> np.ndarray:
    output = frame.copy()
    blue, green, red, alpha = cv2.split(output)
    green_residual = (
        (green.astype(np.int16) - np.maximum(red, blue).astype(np.int16) > 28)
        & (alpha < 220)
    )
    alpha[green_residual] = 0
    alpha[alpha < 5] = 0
    output[:, :, 3] = alpha
    output[alpha == 0, :3] = 0
    return output


def write_sheet(path: Path, frames: list[np.ndarray]) -> None:
    cell = 256
    sheet = np.zeros((cell * SHEET_ROWS, cell * SHEET_COLUMNS, 4), dtype=np.uint8)
    for index, frame in enumerate(frames):
        row, column = divmod(index, SHEET_COLUMNS)
        sheet[
            row * cell : (row + 1) * cell,
            column * cell : (column + 1) * cell,
        ] = cv2.resize(frame, (cell, cell), interpolation=cv2.INTER_AREA)
    write_frame(path, sheet)


def write_loop_sheet(path: Path, frames: list[np.ndarray]) -> None:
    """Show the wrap boundary in playback order for quick visual inspection."""
    cell = 256
    boundary = [frames[-2], frames[-1], frames[0], frames[1]]
    sheet = np.zeros((cell, cell * len(boundary), 4), dtype=np.uint8)
    for index, frame in enumerate(boundary):
        sheet[:, index * cell : (index + 1) * cell] = cv2.resize(
            frame,
            (cell, cell),
            interpolation=cv2.INTER_AREA,
        )
    write_frame(path, sheet)


def write_animation(path: Path, frames: list[np.ndarray], duration_ms: int) -> None:
    animation = cv2.Animation()
    animation.frames = frames
    animation.durations = [duration_ms] * len(frames)
    animation.loop_count = 0
    animation.bgcolor = (0, 0, 0, 0)
    if not cv2.imwriteanimation(str(path), animation):
        raise ValueError(f"unable to write animation {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sheet",
        type=Path,
        default=Path(
            "work/walking/walking_render_v4/walking_video_driven_25_green.png"
        ),
    )
    parser.add_argument(
        "--spec",
        type=Path,
        default=Path("work/walking/walk_spec.json"),
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
    parser.add_argument(
        "--loop-bridge",
        type=Path,
        default=Path(
            "work/walking/walking_render_v4/walking_loop_bridge_25_green.png"
        ),
    )
    parser.add_argument("--scale", type=float, default=1.46)
    args = parser.parse_args()

    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    target_frame = cv2.imread(str(args.target_color_frame), cv2.IMREAD_UNCHANGED)
    if target_frame is None or target_frame.shape != (512, 512, 4):
        raise ValueError(f"unable to read color anchor {args.target_color_frame}")
    target_median = fur_median_bgr(target_frame)

    source_cells = split_sheet(args.sheet)
    frames = [
        clean_transparency(
            soften(normalize_color(place_and_align(cell, args.scale), target_median))
        )
        for cell in source_cells
    ]
    bridge_source = cv2.imread(str(args.loop_bridge), cv2.IMREAD_COLOR)
    if bridge_source is None:
        raise ValueError(f"unable to read loop bridge {args.loop_bridge}")
    bridge = keep_primary_subject(chroma_to_bgra(bridge_source))
    target_area = float(
        np.median([np.count_nonzero(frame[:, :, 3] > 20) for frame in frames])
    )
    bridge_area = max(1, int(np.count_nonzero(bridge[:, :, 3] > 20)))
    bridge_scale = np.sqrt(target_area / bridge_area)
    # Phase 25 is authored separately from phase 24, phase 01, the exact source
    # timestamp and the four-limb debug pose. This avoids both a generator wrap
    # jump and the broken-paw ghosts produced by whole-frame optical flow.
    frames[-1] = clean_transparency(
        soften(
            normalize_color(
                place_and_align(bridge, float(bridge_scale)),
                target_median,
            )
        )
    )

    clear_pngs(args.runtime_output)
    args.output.mkdir(parents=True, exist_ok=True)
    for stale in args.output.glob("walking_*.png"):
        stale.unlink()
    for index, frame in enumerate(frames):
        write_frame(args.runtime_output / f"{index:02d}.png", frame)
        write_frame(args.output / f"walking_{index + 1:02d}.png", frame)

    write_sheet(args.output / "walking_keyframes_sheet.png", frames)
    write_loop_sheet(args.output / "walking_loop_sheet.png", frames)
    duration_ms = round(1000 / float(spec["playback"]["fps"]))
    write_animation(args.output / "walking_preview.webp", frames, duration_ms)
    write_animation(args.output / "walking_preview.gif", frames, duration_ms)

    bounds = [alpha_bounds(frame) for frame in frames]
    areas = [int(np.count_nonzero(frame[:, :, 3] > 20)) for frame in frames]
    metadata = {
        "method": (
            "Twenty-five whole-cat phases rendered from 25 exact timestamps in one "
            "real-cat side-view stride. The natural cycle duration is unchanged, "
            "the duplicated endpoint is omitted, phase 25 is separately rendered "
            "from phases 24/01 plus its exact video/debug references, and no static "
            "torso rig or whole-frame flow bridge is used."
        ),
        "generator": "OpenAI built-in image generation",
        "promptSummary": (
            "Maodie identity and patina, exact 5x5 dense video-driven gait phases, "
            "persistent four-limb identities, whole-body weight shift, pure green "
            "background, and periodic frame-25-to-frame-01 continuity."
        ),
        "sourceSheet": str(args.sheet),
        "loopBridge": str(args.loop_bridge),
        "referenceFrames": "work/walking/walking_reference_frames",
        "poseDebug": "work/walking/walking_pose_debug",
        "frameCount": FRAME_COUNT,
        "fps": float(spec["playback"]["fps"]),
        "cycleSeconds": float(spec["playback"]["cycleSeconds"]),
        "scale": args.scale,
        "bounds": bounds,
        "visibleAreas": areas,
        "bodyCenters": [frame["body"]["center"] for frame in spec["frames"]],
        "limbStates": [
            {name: frame[name]["state"] for name in ("LF", "RF", "LH", "RH")}
            for frame in spec["frames"]
        ],
    }
    (args.output / "walking_render_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
