#!/usr/bin/env python3
"""Densely sample one complete side-view cat gait cycle from the source video."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np


CYCLE_START_SECONDS = 2.90
CYCLE_END_SECONDS = 7.24
CAPTURE_FPS = 125
SOURCE_PAGE = (
    "https://commons.wikimedia.org/wiki/"
    "File:Whole-Body-Mechanics-of-Stealthy-Walking-in-Cats-pone.0003808.s002.ogv"
)
SOURCE_AUTHOR = "Bishop K, Pai A, Schmitt D"
SOURCE_PAPER = "https://doi.org/10.1371/journal.pone.0003808"
LICENSE_PAGE = "https://creativecommons.org/licenses/by/2.5/"
REFERENCE_FRAME_COUNT = 25
CANDIDATE_FRAME_COUNT = 50


def clear_pngs(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for path in directory.glob("*.png"):
        path.unlink()


def read_frame(capture: cv2.VideoCapture, timestamp: float) -> np.ndarray:
    capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
    success, frame = capture.read()
    if not success:
        raise ValueError(f"unable to read video at {timestamp:.3f}s")
    return frame


def activity_crop(frame: np.ndarray) -> np.ndarray:
    """Crop overlays while retaining the complete cat, then face it to the right."""
    height, width = frame.shape[:2]
    if (width, height) != (352, 288):
        raise ValueError(f"unexpected source size {(width, height)}")
    crop = frame[55:240, 5:347]
    return cv2.flip(crop, 1)


def foreground_mask(frame: np.ndarray, background: np.ndarray) -> np.ndarray:
    """Isolate the moving cat from the fixed scientific-camera background."""
    difference = cv2.absdiff(frame, background)
    gray = cv2.cvtColor(difference, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    mask = np.where(gray > 13, 255, 0).astype(np.uint8)
    mask[:8] = 0
    mask[-8:] = 0
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)),
    )
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
    )
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    if component_count <= 1:
        raise ValueError("unable to isolate moving cat")
    candidates = [
        index
        for index in range(1, component_count)
        if stats[index, cv2.CC_STAT_AREA] >= 140
        and stats[index, cv2.CC_STAT_WIDTH] >= 18
        and stats[index, cv2.CC_STAT_HEIGHT] >= 15
    ]
    if not candidates:
        raise ValueError("unable to find cat-sized foreground component")
    largest = max(candidates, key=lambda index: stats[index, cv2.CC_STAT_AREA])
    return np.where(labels == largest, 255, 0).astype(np.uint8)


def stabilize_root_translation(
    frame: np.ndarray,
    background: np.ndarray,
    phase: float,
) -> tuple[np.ndarray, int]:
    """Remove world translation while preserving the cat's within-stride motion."""
    mask = foreground_mask(frame, background)
    yy, xx = np.indices(mask.shape)
    # The cat advances monotonically across this fixed-camera clip. Constrain
    # foreground selection to that trajectory so cage bars and the white plate
    # cannot take over the tracker when a leg overlaps the background.
    expected_x = 78 + phase * 180
    tracking_region = (
        (yy >= 42)
        & (yy <= 178)
        & (xx >= expected_x - 72)
        & (xx <= expected_x + 72)
    )
    ys, xs = np.where((mask > 0) & tracking_region)
    if len(xs) < 100:
        center_x = int(round(expected_x))
    else:
        center_x = int(round(float(np.median(xs))))
    target_x = frame.shape[1] // 2
    shift_x = target_x - center_x
    stabilized = cv2.warpAffine(
        frame,
        np.float32([[1, 0, shift_x], [0, 1, 0]]),
        (frame.shape[1], frame.shape[0]),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REFLECT_101,
    )
    return stabilized, shift_x


def write_frame(path: Path, frame: np.ndarray) -> None:
    resized = cv2.resize(frame, (1280, 720), interpolation=cv2.INTER_CUBIC)
    if not cv2.imwrite(str(path), resized):
        raise ValueError(f"unable to write {path}")


def write_sheet(path: Path, frames: list[np.ndarray], columns: int) -> None:
    cell_width = 320
    cell_height = 180
    rows = (len(frames) + columns - 1) // columns
    sheet = np.full(
        (rows * cell_height, columns * cell_width, 3),
        236,
        dtype=np.uint8,
    )
    for index, frame in enumerate(frames):
        row, column = divmod(index, columns)
        thumbnail = cv2.resize(
            frame,
            (cell_width, cell_height),
            interpolation=cv2.INTER_CUBIC,
        )
        cv2.putText(
            thumbnail,
            f"{index + 1:02d}",
            (14, 34),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.82,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        sheet[
            row * cell_height : (row + 1) * cell_height,
            column * cell_width : (column + 1) * cell_width,
        ] = thumbnail
    if not cv2.imwrite(str(path), sheet):
        raise ValueError(f"unable to write {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("work/walking/walking_reference_frames"),
    )
    parser.add_argument(
        "--candidates-output",
        type=Path,
        default=Path("work/walking/walking_reference_candidates_50"),
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=Path("work/walking/walking_reference_source.json"),
    )
    args = parser.parse_args()

    capture = cv2.VideoCapture(str(args.video))
    if not capture.isOpened():
        raise ValueError(f"unable to open {args.video}")
    source_fps = float(capture.get(cv2.CAP_PROP_FPS))
    source_frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    cycle_seconds = CYCLE_END_SECONDS - CYCLE_START_SECONDS

    clear_pngs(args.output)
    clear_pngs(args.candidates_output)

    candidate_times = np.linspace(
        CYCLE_START_SECONDS,
        CYCLE_END_SECONDS,
        CANDIDATE_FRAME_COUNT,
        endpoint=False,
    )
    raw_candidate_frames = [
        activity_crop(read_frame(capture, float(timestamp)))
        for timestamp in candidate_times
    ]
    background = np.median(np.stack(raw_candidate_frames), axis=0).astype(np.uint8)
    candidate_frames: list[np.ndarray] = []
    for index, raw_frame in enumerate(raw_candidate_frames, start=1):
        phase = (index - 1) / CANDIDATE_FRAME_COUNT
        frame, _ = stabilize_root_translation(raw_frame, background, phase)
        candidate_frames.append(frame)
        write_frame(args.candidates_output / f"{index:02d}.png", frame)

    # endpoint=False is essential for a seamless loop: the omitted endpoint is
    # the same gait phase as frame 01. Therefore frame 25 -> frame 01 spans
    # exactly the same temporal interval as every other adjacent pair.
    reference_times = np.linspace(
        CYCLE_START_SECONDS,
        CYCLE_END_SECONDS,
        REFERENCE_FRAME_COUNT,
        endpoint=False,
    )
    reference_frames: list[np.ndarray] = []
    reference_shifts: list[int] = []
    for index, timestamp in enumerate(reference_times, start=1):
        raw_frame = activity_crop(read_frame(capture, float(timestamp)))
        phase = (index - 1) / REFERENCE_FRAME_COUNT
        frame, shift_x = stabilize_root_translation(raw_frame, background, phase)
        reference_frames.append(frame)
        reference_shifts.append(shift_x)
        write_frame(args.output / f"{index:02d}.png", frame)

    write_sheet(args.candidates_output / "contact_sheet.png", candidate_frames, 10)
    write_sheet(args.output / "contact_sheet.png", reference_frames, 5)

    args.metadata.parent.mkdir(parents=True, exist_ok=True)
    args.metadata.write_text(
        json.dumps(
            {
                "sourcePage": SOURCE_PAGE,
                "sourceAuthor": SOURCE_AUTHOR,
                "sourcePaper": SOURCE_PAPER,
                "license": "Creative Commons Attribution 2.5",
                "licensePage": LICENSE_PAGE,
                "sourceVideo": {
                    "fps": source_fps,
                    "frameCount": source_frame_count,
                    "durationSeconds": source_frame_count / source_fps,
                },
                "selectedCycle": {
                    "startSeconds": CYCLE_START_SECONDS,
                    "endSeconds": CYCLE_END_SECONDS,
                    "durationSeconds": cycle_seconds,
                    "naturalDurationSeconds": round(
                        cycle_seconds * source_fps / CAPTURE_FPS,
                        4,
                    ),
                    "captureFps": CAPTURE_FPS,
                    "candidateFrameCount": CANDIDATE_FRAME_COUNT,
                    "referenceFrameCount": REFERENCE_FRAME_COUNT,
                    "referenceIntervalPlaybackSeconds": round(
                        cycle_seconds / REFERENCE_FRAME_COUNT,
                        4,
                    ),
                    "referenceIntervalNaturalSeconds": round(
                        cycle_seconds
                        * source_fps
                        / CAPTURE_FPS
                        / REFERENCE_FRAME_COUNT,
                        4,
                    ),
                    "referenceTimestampsSeconds": [
                        round(float(value), 4) for value in reference_times
                    ],
                    "rootTranslationRemoved": True,
                    "horizontalStabilizationPixelsAtSourceResolution": reference_shifts,
                },
                "selectionReason": (
                    "Fixed scientific side-view camera, complete short-haired cat, "
                    "clear limbs and tail, high-speed capture, and one uninterrupted "
                    "natural extended-walk stride. Frames are flipped horizontally so "
                    "the desktop-pet reference faces right."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
