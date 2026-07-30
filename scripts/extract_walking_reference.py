#!/usr/bin/env python3
"""Extract a complete side-view cat gait cycle from the selected source video."""

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


def write_frame(path: Path, frame: np.ndarray) -> None:
    resized = cv2.resize(frame, (1280, 720), interpolation=cv2.INTER_CUBIC)
    if not cv2.imwrite(str(path), resized):
        raise ValueError(f"unable to write {path}")


def write_sheet(path: Path, frames: list[np.ndarray], columns: int) -> None:
    cell_width = 384
    cell_height = 216
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
        default=Path("work/walking/walking_reference_candidates_12"),
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
        12,
        endpoint=False,
    )
    candidate_frames: list[np.ndarray] = []
    for index, timestamp in enumerate(candidate_times, start=1):
        frame = activity_crop(read_frame(capture, float(timestamp)))
        candidate_frames.append(frame)
        write_frame(args.candidates_output / f"{index:02d}.png", frame)

    reference_times = np.linspace(
        CYCLE_START_SECONDS,
        CYCLE_END_SECONDS,
        8,
        endpoint=False,
    )
    reference_frames: list[np.ndarray] = []
    for index, timestamp in enumerate(reference_times, start=1):
        frame = activity_crop(read_frame(capture, float(timestamp)))
        reference_frames.append(frame)
        write_frame(args.output / f"{index:02d}.png", frame)

    write_sheet(args.candidates_output / "contact_sheet.png", candidate_frames, 4)
    write_sheet(args.output / "contact_sheet.png", reference_frames, 4)

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
                    "candidateFrameCount": 12,
                    "referenceFrameCount": 8,
                    "referenceTimestampsSeconds": [
                        round(float(value), 4) for value in reference_times
                    ],
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
