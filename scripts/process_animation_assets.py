#!/usr/bin/env python3
"""Build stable pet animations and idle-state transitions from generated sheets.

The source sheets are generated at 1536x1024, so each cell is 384x512.
This script preserves that aspect ratio, removes the chroma-key background,
aligns every subject to a shared center/baseline, normalizes fur color against
the sitting anchor, and inserts a variable number of recursively generated 50%
poses between keyframes. Runtime playback remains fixed-rate: motion timing is
encoded entirely by frame density, never by holding individual frames longer.

OpenCV is intentionally an asset-authoring dependency only:

    PYTHONPATH=/tmp/maodie-image-tools python3 scripts/process_animation_assets.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np


STATES = ("sitting", "walking", "sleeping", "happy", "petting", "hissing")
LOOPING_STATES = {"sitting", "walking", "sleeping", "happy"}
GENERATED_TRANSITION_STATES = {"walking", "petting", "hissing"}
V4_STATES = {"walking", "petting", "hissing"}
INSERTION_COUNTS: dict[str, tuple[int, ...]] = {
    # Four equally spaced samples per gait interval prevent paw teleporting.
    "walking": (3, 3, 3, 3, 3, 3, 3, 3),
    # Fast chin lift, dense pleased hold, then a controlled return.
    "petting": (0, 0, 1, 3, 3, 1, 1),
    # Fast mouth opening/closing, dense full-hiss hold and neutral settle.
    "hissing": (0, 1, 0, 3, 0, 1, 3),
}
IDLE_TRANSITIONS = (
    ("sitting", "walking"),
    ("sitting", "sleeping"),
    ("walking", "sleeping"),
)
CANVAS_SIZE = 512
TARGET_CENTER_X = 256
TARGET_BASELINE_Y = 487


def chroma_to_bgra(cell: np.ndarray) -> np.ndarray:
    blue, green, red = cv2.split(cell.astype(np.float32))
    dominance = green - np.maximum(red, blue)
    alpha = np.full(green.shape, 255.0, dtype=np.float32)

    transition = (green > 125) & (dominance > 42)
    alpha[transition] = np.clip((102.0 - dominance[transition]) / 60.0 * 255.0, 0, 255)
    alpha[(green > 165) & (dominance >= 102)] = 0

    edge = alpha < 255
    green[edge] = np.minimum(green[edge], np.maximum(red[edge], blue[edge]) + 8)
    return cv2.merge(
        (
            np.clip(blue, 0, 255).astype(np.uint8),
            np.clip(green, 0, 255).astype(np.uint8),
            np.clip(red, 0, 255).astype(np.uint8),
            np.clip(alpha, 0, 255).astype(np.uint8),
        )
    )


def keep_primary_subject(frame: np.ndarray) -> np.ndarray:
    mask = (frame[:, :, 3] > 20).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if count <= 2:
        return frame

    primary = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    keep = (labels == primary).astype(np.uint8)
    keep = cv2.dilate(keep, np.ones((3, 3), dtype=np.uint8), iterations=1).astype(bool)
    output = frame.copy()
    output[~keep] = 0
    return output


def split_sheet(path: Path) -> list[np.ndarray]:
    sheet = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if sheet is None:
        raise ValueError(f"unable to read {path}")

    height, width = sheet.shape[:2]
    frames: list[np.ndarray] = []
    for index in range(8):
        column, row = index % 4, index // 4
        left, right = round(column * width / 4), round((column + 1) * width / 4)
        top, bottom = round(row * height / 2), round((row + 1) * height / 2)
        cell = keep_primary_subject(chroma_to_bgra(sheet[top:bottom, left:right]))

        scale = min(CANVAS_SIZE / cell.shape[1], CANVAS_SIZE / cell.shape[0], 1.0)
        if scale < 1:
            cell = cv2.resize(
                cell,
                (round(cell.shape[1] * scale), round(cell.shape[0] * scale)),
                interpolation=cv2.INTER_AREA,
            )

        canvas = np.zeros((CANVAS_SIZE, CANVAS_SIZE, 4), dtype=np.uint8)
        x = (CANVAS_SIZE - cell.shape[1]) // 2
        y = (CANVAS_SIZE - cell.shape[0]) // 2
        canvas[y : y + cell.shape[0], x : x + cell.shape[1]] = cell
        frames.append(canvas)
    return frames


def alpha_bounds(frame: np.ndarray, threshold: int = 20) -> tuple[int, int, int, int]:
    ys, xs = np.where(frame[:, :, 3] > threshold)
    if len(xs) == 0:
        raise ValueError("frame contains no visible subject")
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def translate(frame: np.ndarray, dx: int, dy: int) -> np.ndarray:
    matrix = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(
        frame,
        matrix,
        (CANVAS_SIZE, CANVAS_SIZE),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )


def align_frame(frame: np.ndarray) -> np.ndarray:
    left, _, right, bottom = alpha_bounds(frame)
    center = (left + right) / 2
    return translate(
        frame,
        round(TARGET_CENTER_X - center),
        TARGET_BASELINE_Y - bottom,
    )


def subject_pixel_area(frame: np.ndarray) -> int:
    return int(np.count_nonzero(frame[:, :, 3] > 20))


def scale_to_subject_area(frame: np.ndarray, target_area: float) -> np.ndarray:
    current_area = max(1, subject_pixel_area(frame))
    scale = float(np.clip(np.sqrt(target_area / current_area), 0.7, 1.8))
    if abs(scale - 1) < 0.01:
        return align_frame(frame)

    left, top, right, bottom = alpha_bounds(frame)
    crop = frame[top : bottom + 1, left : right + 1]
    resized = cv2.resize(
        crop,
        (max(1, round(crop.shape[1] * scale)), max(1, round(crop.shape[0] * scale))),
        interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA,
    )
    canvas = np.zeros_like(frame)
    height, width = resized.shape[:2]
    x = TARGET_CENTER_X - width // 2
    y = TARGET_BASELINE_Y - height + 1

    source_left, source_top = max(0, -x), max(0, -y)
    source_right = min(width, CANVAS_SIZE - x)
    source_bottom = min(height, CANVAS_SIZE - y)
    target_left, target_top = max(0, x), max(0, y)
    target_right = target_left + max(0, source_right - source_left)
    target_bottom = target_top + max(0, source_bottom - source_top)
    canvas[target_top:target_bottom, target_left:target_right] = resized[
        source_top:source_bottom, source_left:source_right
    ]
    return align_frame(canvas)


def fur_mask(frame: np.ndarray) -> np.ndarray:
    blue, green, red, alpha = cv2.split(frame)
    return (
        (alpha > 220)
        & (red.astype(np.int16) - blue.astype(np.int16) > 18)
        & (green.astype(np.int16) - blue.astype(np.int16) > 6)
        & (red > 65)
        & (green > 50)
    )


def fur_median_bgr(frame: np.ndarray) -> np.ndarray:
    mask = fur_mask(frame)
    pixels = frame[:, :, :3][mask]
    if len(pixels) < 100:
        raise ValueError("not enough fur pixels for color normalization")
    return np.median(pixels.astype(np.float32), axis=0)


def normalize_color(frame: np.ndarray, target_median: np.ndarray) -> np.ndarray:
    source_median = fur_median_bgr(frame)
    gains = np.clip(target_median / np.maximum(source_median, 1), 0.82, 1.18)

    output = frame.copy()
    rgb = output[:, :, :3].astype(np.float32)
    corrected = np.clip(rgb * gains.reshape(1, 1, 3), 0, 255)

    blue, green, red = cv2.split(rgb)
    warm = np.clip((red - blue - 5) / 55, 0, 1) * np.clip((green - blue) / 40, 0, 1)
    subject = output[:, :, 3].astype(np.float32) / 255
    weight = subject * (0.2 + 0.8 * warm)
    rgb = rgb * (1 - weight[:, :, None]) + corrected * weight[:, :, None]
    output[:, :, :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    return output


def soften(frame: np.ndarray) -> np.ndarray:
    smaller = cv2.resize(frame, (416, 416), interpolation=cv2.INTER_AREA)
    return cv2.resize(smaller, (CANVAS_SIZE, CANVAS_SIZE), interpolation=cv2.INTER_LINEAR)


def flow_input(frame: np.ndarray) -> np.ndarray:
    alpha = frame[:, :, 3:4].astype(np.float32) / 255
    composite = frame[:, :, :3].astype(np.float32) * alpha + 127 * (1 - alpha)
    return cv2.cvtColor(composite.astype(np.uint8), cv2.COLOR_BGR2GRAY)


def warp_halfway(frame: np.ndarray, flow: np.ndarray) -> np.ndarray:
    height, width = flow.shape[:2]
    grid_x, grid_y = np.meshgrid(
        np.arange(width, dtype=np.float32),
        np.arange(height, dtype=np.float32),
    )
    map_x = grid_x - flow[:, :, 0] * 0.5
    map_y = grid_y - flow[:, :, 1] * 0.5

    alpha = frame[:, :, 3:4].astype(np.float32) / 255
    premultiplied = frame[:, :, :3].astype(np.float32) * alpha
    packed = np.concatenate((premultiplied, alpha * 255), axis=2)
    return cv2.remap(
        packed,
        map_x,
        map_y,
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )


def transition_frame(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    first_gray = flow_input(first)
    second_gray = flow_input(second)
    forward_solver = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    backward_solver = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    for solver in (forward_solver, backward_solver):
        solver.setFinestScale(0)
        solver.setGradientDescentIterations(45)
        solver.setPatchSize(8)
        solver.setPatchStride(4)
        solver.setVariationalRefinementIterations(8)
        solver.setUseSpatialPropagation(True)

    forward = forward_solver.calc(first_gray, second_gray, None)
    backward = backward_solver.calc(second_gray, first_gray, None)

    first_warped = warp_halfway(first, forward)
    second_warped = warp_halfway(second, backward)
    mixed = (first_warped + second_warped) * 0.5

    alpha = np.clip(mixed[:, :, 3:4], 0, 255)
    rgb = np.divide(
        mixed[:, :, :3] * 255,
        np.maximum(alpha, 1),
        out=np.zeros_like(mixed[:, :, :3]),
        where=alpha > 0,
    )
    return np.concatenate((np.clip(rgb, 0, 255), alpha), axis=2).astype(np.uint8)


def write_frame(path: Path, frame: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), frame):
        raise ValueError(f"unable to write {path}")


def composite_on_green(frame: np.ndarray) -> np.ndarray:
    alpha = frame[:, :, 3:4].astype(np.float32) / 255
    green = np.zeros_like(frame[:, :, :3], dtype=np.float32)
    green[:, :, 1] = 255
    return np.clip(frame[:, :, :3] * alpha + green * (1 - alpha), 0, 255).astype(np.uint8)


def write_transition_sheet(path: Path, transitions: list[np.ndarray]) -> None:
    sheet = np.zeros((CANVAS_SIZE * 2, CANVAS_SIZE * 4, 3), dtype=np.uint8)
    sheet[:, :, 1] = 255
    for index, frame in enumerate(transitions):
        column, row = index % 4, index // 4
        top, left = row * CANVAS_SIZE, column * CANVAS_SIZE
        sheet[top : top + CANVAS_SIZE, left : left + CANVAS_SIZE] = composite_on_green(frame)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), sheet)


def write_final_sheet(path: Path, frames: list[np.ndarray]) -> None:
    cell_size = CANVAS_SIZE // 2
    columns = 8 if len(frames) > 16 else 4
    rows = (len(frames) + columns - 1) // columns
    sheet = np.zeros((cell_size * rows, cell_size * columns, 3), dtype=np.uint8)
    sheet[:, :, 1] = 255
    for index, frame in enumerate(frames):
        column, row = index % columns, index // columns
        preview = cv2.resize(
            composite_on_green(frame),
            (cell_size, cell_size),
            interpolation=cv2.INTER_AREA,
        )
        top, left = row * cell_size, column * cell_size
        sheet[top : top + cell_size, left : left + cell_size] = preview
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), sheet)


def frame_metrics(frame: np.ndarray, target_median: np.ndarray) -> dict[str, object]:
    left, top, right, bottom = alpha_bounds(frame)
    median = fur_median_bgr(frame)
    return {
        "bounds": [left, top, right, bottom],
        "centerX": round((left + right) / 2, 2),
        "baselineY": bottom,
        "furMedianBgr": [round(float(value), 2) for value in median],
        "furColorDistance": round(float(np.linalg.norm(median - target_median)), 2),
    }


def head_width(frame: np.ndarray) -> int:
    left, top, right, bottom = alpha_bounds(frame)
    head_bottom = top + round((bottom - top + 1) * 0.42)
    ys, xs = np.where(frame[top : head_bottom + 1, :, 3] > 20)
    if len(xs) == 0:
        return 0
    return int(xs.max() - xs.min() + 1)


def process(
    source_root: Path,
    override_source_root: Path,
    generated_transition_root: Path,
    override_generated_transition_root: Path,
    v4_source_root: Path,
    v4_midpoint_root: Path,
    v4_quarter_left_root: Path,
    v4_quarter_right_root: Path,
    idle_transition_source_root: Path,
    output_root: Path,
    idle_transition_output_root: Path,
    work_root: Path,
    report_path: Path,
) -> None:
    def state_source(state: str) -> Path:
        v4 = v4_source_root / f"{state}.png"
        if v4.exists():
            return v4
        override = override_source_root / f"{state}.png"
        return override if override.exists() else source_root / f"{state}.png"

    def generated_transition_source(state: str) -> Path:
        override = override_generated_transition_root / f"{state}.png"
        return override if override.exists() else generated_transition_root / f"{state}.png"

    keyframes = {
        state: [align_frame(frame) for frame in split_sheet(state_source(state))]
        for state in STATES
    }
    target_median = fur_median_bgr(keyframes["sitting"][0])

    for state in STATES:
        keyframes[state] = [
            soften(normalize_color(frame, target_median)) for frame in keyframes[state]
        ]

    generated_transitions = {
        state: [
            soften(normalize_color(align_frame(frame), target_median))
            for frame in split_sheet(generated_transition_source(state))
        ]
        for state in GENERATED_TRANSITION_STATES - V4_STATES
    }
    v4_midpoints = {
        state: [
            soften(normalize_color(align_frame(frame), target_median))
            for frame in split_sheet(v4_midpoint_root / f"{state}.png")
        ]
        for state in V4_STATES
    }
    v4_quarter_left = {
        state: [
            soften(normalize_color(align_frame(frame), target_median))
            for frame in split_sheet(v4_quarter_left_root / f"{state}.png")
        ]
        for state in ("walking", "petting")
    }
    v4_quarter_right = {
        state: [
            soften(normalize_color(align_frame(frame), target_median))
            for frame in split_sheet(v4_quarter_right_root / f"{state}.png")
        ]
        for state in ("walking", "petting")
    }

    report: dict[str, object] = {
        "method": {
            "timing": "fixed-rate playback; variable recursive 50% in-between frame density",
            "generatedTransitions": "walking, petting and hissing use constrained generated 50% poses",
            "otherStates": "50% bidirectional DIS dense optical-flow warp",
            "idleTransitions": "eight generated poses with exact endpoints and reversible playback",
        },
        "targetCenterX": TARGET_CENTER_X,
        "targetBaselineY": TARGET_BASELINE_Y,
        "targetFurMedianBgr": [round(float(value), 2) for value in target_median],
        "states": {},
        "idleTransitions": {},
    }

    for state in STATES:
        state_output = output_root / state
        final_frames: list[np.ndarray] = []
        midpoint_previews: list[np.ndarray] = []
        interval_count = 8 if state in LOOPING_STATES else 7
        insertion_counts = INSERTION_COUNTS.get(state, (1,) * interval_count)

        for index, keyframe in enumerate(keyframes[state]):
            final_frames.append(keyframe)
            if index >= interval_count:
                continue

            next_keyframe = keyframes[state][(index + 1) % 8]
            if state in V4_STATES:
                midpoint = v4_midpoints[state][index]
            elif state in GENERATED_TRANSITION_STATES:
                midpoint = generated_transitions[state][index]
            else:
                midpoint = transition_frame(keyframe, next_keyframe)
            midpoint_previews.append(midpoint)

            insertions = insertion_counts[index]
            if insertions == 0:
                continue
            if insertions == 1:
                final_frames.append(midpoint)
                continue
            if insertions != 3:
                raise ValueError(f"unsupported insertion count {insertions} for {state}")

            if state in v4_quarter_left:
                quarter_left = v4_quarter_left[state][index]
                quarter_right = v4_quarter_right[state][index]
            else:
                # A second 50% pass produces 25% and 75% poses while staying
                # bounded by the generated midpoint and its exact neighbors.
                quarter_left = transition_frame(keyframe, midpoint)
                quarter_right = transition_frame(midpoint, next_keyframe)
            final_frames.extend((quarter_left, midpoint, quarter_right))

        for index, frame in enumerate(final_frames):
            write_frame(state_output / f"{index:02d}.png", frame)
        write_transition_sheet(
            work_root / "transition-sheets" / f"{state}.png",
            (midpoint_previews + [midpoint_previews[-1]])[:8],
        )
        write_final_sheet(work_root / "final-sheets" / f"{state}.png", final_frames)

        metrics = [frame_metrics(frame, target_median) for frame in final_frames]
        centers = [float(item["centerX"]) for item in metrics]
        baselines = [int(item["baselineY"]) for item in metrics]
        colors = [float(item["furColorDistance"]) for item in metrics]
        widths = [head_width(frame) for frame in final_frames]
        report["states"][state] = {
            "frameCount": len(final_frames),
            "fixedRatePlayback": True,
            "insertionCounts": list(insertion_counts),
            "transitionMethod": (
                "variable recursive constrained 50% in-between poses"
                if state in V4_STATES
                else "constrained generated 50% in-between poses"
                if state in GENERATED_TRANSITION_STATES
                else "50% bidirectional DIS dense optical-flow warp"
            ),
            "maxCenterDriftPx": round(max(centers) - min(centers), 2),
            "maxBaselineDriftPx": max(baselines) - min(baselines),
            "maxFurColorDistance": round(max(colors), 2),
            "headWidthsPx": widths,
            "maxHeadWidthGrowthRatio": round(max(widths) / max(1, widths[0]), 3),
            "frames": metrics,
        }

    for start, end in IDLE_TRANSITIONS:
        name = f"{start}-{end}"
        transition_output = idle_transition_output_root / name
        existing_paths = [transition_output / f"{index:02d}.png" for index in range(8)]
        if all(path.exists() for path in existing_paths):
            # Preserve the already approved v3 transition interiors. Only the
            # endpoint that touches a replaced state sequence should change.
            generated = [
                cv2.imread(str(path), cv2.IMREAD_UNCHANGED) for path in existing_paths
            ]
            if any(frame is None or frame.shape[2] != 4 for frame in generated):
                raise ValueError(f"invalid existing transition frames for {name}")
        else:
            generated = [
                soften(normalize_color(align_frame(frame), target_median))
                for frame in split_sheet(idle_transition_source_root / f"{name}.png")
            ]
            start_area = subject_pixel_area(keyframes[start][0])
            end_area = subject_pixel_area(keyframes[end][0])
            generated = [
                scale_to_subject_area(
                    frame,
                    start_area + (end_area - start_area) * index / (len(generated) - 1),
                )
                for index, frame in enumerate(generated)
            ]
        # Exact runtime endpoints prevent a residual flash at either side.
        generated[0] = keyframes[start][0].copy()
        generated[-1] = keyframes[end][0].copy()

        for index, frame in enumerate(generated):
            write_frame(transition_output / f"{index:02d}.png", frame)
        write_final_sheet(work_root / "idle-transition-final-sheets" / f"{name}.png", generated)

        metrics = [frame_metrics(frame, target_median) for frame in generated]
        centers = [float(item["centerX"]) for item in metrics]
        baselines = [int(item["baselineY"]) for item in metrics]
        colors = [float(item["furColorDistance"]) for item in metrics]
        report["idleTransitions"][name] = {
            "frameCount": len(generated),
            "reversePlayback": True,
            "maxCenterDriftPx": round(max(centers) - min(centers), 2),
            "maxBaselineDriftPx": max(baselines) - min(baselines),
            "maxFurColorDistance": round(max(colors), 2),
            "frames": metrics,
        }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("artifacts/asset-work/v2/source-sheets"),
    )
    parser.add_argument(
        "--override-source-root",
        type=Path,
        default=Path("artifacts/asset-work/v3/source-sheets"),
    )
    parser.add_argument(
        "--generated-transition-root",
        type=Path,
        default=Path("artifacts/asset-work/v2/generated-transition-sheets"),
    )
    parser.add_argument(
        "--override-generated-transition-root",
        type=Path,
        default=Path("artifacts/asset-work/v3/generated-transition-sheets"),
    )
    parser.add_argument(
        "--idle-transition-source-root",
        type=Path,
        default=Path("artifacts/asset-work/v3/idle-transition-sheets"),
    )
    parser.add_argument(
        "--v4-source-root",
        type=Path,
        default=Path("artifacts/asset-work/v4/source-sheets"),
    )
    parser.add_argument(
        "--v4-midpoint-root",
        type=Path,
        default=Path("artifacts/asset-work/v4/generated-midpoint-sheets"),
    )
    parser.add_argument(
        "--v4-quarter-left-root",
        type=Path,
        default=Path("artifacts/asset-work/v4/generated-quarter-left-sheets"),
    )
    parser.add_argument(
        "--v4-quarter-right-root",
        type=Path,
        default=Path("artifacts/asset-work/v4/generated-quarter-right-sheets"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("src/assets/pet"),
    )
    parser.add_argument(
        "--idle-transition-output-root",
        type=Path,
        default=Path("src/assets/pet-transitions"),
    )
    parser.add_argument(
        "--work-root",
        type=Path,
        default=Path("artifacts/asset-work/v3"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("artifacts/asset-work/v3/quality-report.json"),
    )
    args = parser.parse_args()
    process(
        args.source_root,
        args.override_source_root,
        args.generated_transition_root,
        args.override_generated_transition_root,
        args.v4_source_root,
        args.v4_midpoint_root,
        args.v4_quarter_left_root,
        args.v4_quarter_right_root,
        args.idle_transition_source_root,
        args.output_root,
        args.idle_transition_output_root,
        args.work_root,
        args.report,
    )


if __name__ == "__main__":
    main()
