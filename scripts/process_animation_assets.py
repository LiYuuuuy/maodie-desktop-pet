#!/usr/bin/env python3
"""Build stable 16-frame pet animations from generated 4x2 keyframe sheets.

The source sheets are generated at 1536x1024, so each cell is 384x512.
This script preserves that aspect ratio, removes the chroma-key background,
aligns every subject to a shared center/baseline, normalizes fur color against
the sitting anchor, and creates a true 50% motion-compensated transition
between neighboring keyframes.

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
GENERATED_TRANSITION_STATES = {"walking"}
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
        cell = chroma_to_bgra(sheet[top:bottom, left:right])

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
    sheet = np.zeros((cell_size * 4, cell_size * 4, 3), dtype=np.uint8)
    sheet[:, :, 1] = 255
    for index, frame in enumerate(frames):
        column, row = index % 4, index // 4
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


def process(
    source_root: Path,
    output_root: Path,
    work_root: Path,
    report_path: Path,
) -> None:
    keyframes = {
        state: [align_frame(frame) for frame in split_sheet(source_root / f"{state}.png")]
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
            for frame in split_sheet(work_root / "generated-transition-sheets" / f"{state}.png")
        ]
        for state in GENERATED_TRANSITION_STATES
    }

    report: dict[str, object] = {
        "method": {
            "walking": "constrained generated 50% in-between poses",
            "otherStates": "50% bidirectional DIS dense optical-flow warp",
        },
        "targetCenterX": TARGET_CENTER_X,
        "targetBaselineY": TARGET_BASELINE_Y,
        "targetFurMedianBgr": [round(float(value), 2) for value in target_median],
        "states": {},
    }

    for state in STATES:
        state_output = output_root / state
        transitions: list[np.ndarray] = []
        final_frames: list[np.ndarray] = []

        for index, keyframe in enumerate(keyframes[state]):
            if state in GENERATED_TRANSITION_STATES:
                transition = generated_transitions[state][index]
            elif index == 7 and state not in LOOPING_STATES:
                transition = keyframe.copy()
            else:
                transition = transition_frame(keyframe, keyframes[state][(index + 1) % 8])
            transitions.append(transition)
            final_frames.extend((keyframe, transition))

        for index, frame in enumerate(final_frames):
            write_frame(state_output / f"{index:02d}.png", frame)
        write_transition_sheet(work_root / "transition-sheets" / f"{state}.png", transitions)
        write_final_sheet(work_root / "final-sheets" / f"{state}.png", final_frames)

        metrics = [frame_metrics(frame, target_median) for frame in final_frames]
        centers = [float(item["centerX"]) for item in metrics]
        baselines = [int(item["baselineY"]) for item in metrics]
        colors = [float(item["furColorDistance"]) for item in metrics]
        report["states"][state] = {
            "frameCount": len(final_frames),
            "transitionMethod": (
                "constrained generated 50% in-between poses"
                if state in GENERATED_TRANSITION_STATES
                else "50% bidirectional DIS dense optical-flow warp"
            ),
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
        "--output-root",
        type=Path,
        default=Path("src/assets/pet"),
    )
    parser.add_argument(
        "--work-root",
        type=Path,
        default=Path("artifacts/asset-work/v2"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("artifacts/asset-work/v2/quality-report.json"),
    )
    args = parser.parse_args()
    process(args.source_root, args.output_root, args.work_root, args.report)


if __name__ == "__main__":
    main()
