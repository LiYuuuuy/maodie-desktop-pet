#!/usr/bin/env python3
"""Expand annotated gait anchors into a 25-sample periodic video phase spec."""

from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
from typing import Any


FRAME_COUNT = 25
LIMBS = ("LF", "RF", "LH", "RH")
BODY_POINTS = ("center", "shoulder", "hip", "head", "tailTip")
SCALARS = ("headAngleDegrees", "backArchPx")


def catmull_rom(
    before: float,
    start: float,
    end: float,
    after: float,
    amount: float,
) -> float:
    """Periodic Catmull-Rom interpolation through two annotated anchor poses."""
    amount2 = amount * amount
    amount3 = amount2 * amount
    return 0.5 * (
        2 * start
        + (-before + end) * amount
        + (2 * before - 5 * start + 4 * end - after) * amount2
        + (-before + 3 * start - 3 * end + after) * amount3
    )


def interpolate_value(values: list[float], phase: float) -> float:
    count = len(values)
    location = phase * count
    index = int(math.floor(location)) % count
    amount = location - math.floor(location)
    return catmull_rom(
        values[(index - 1) % count],
        values[index],
        values[(index + 1) % count],
        values[(index + 2) % count],
        amount,
    )


def interpolate_point(points: list[list[int]], phase: float) -> list[int]:
    return [
        round(interpolate_value([point[axis] for point in points], phase))
        for axis in range(2)
    ]


def nearest_anchor(anchors: list[dict[str, Any]], phase: float) -> dict[str, Any]:
    index = round(phase * len(anchors)) % len(anchors)
    return anchors[index]


def separate_paws(frame: dict[str, Any], minimum_distance: float = 26) -> None:
    """Keep four named paw endpoints readable without changing their gait order."""
    for left_index, left_name in enumerate(LIMBS):
        for right_name in LIMBS[left_index + 1 :]:
            left = frame[left_name]["joints"][-1]
            right = frame[right_name]["joints"][-1]
            dx = right[0] - left[0]
            dy = right[1] - left[1]
            distance = math.hypot(dx, dy)
            if distance >= minimum_distance:
                continue
            direction = 1 if dx >= 0 else -1
            if abs(dx) < 1:
                direction = 1 if right_name in {"LF", "LH"} else -1
            correction = math.ceil((minimum_distance - distance) / 2)
            left[0] -= direction * correction
            right[0] += direction * correction


def build_frame(
    anchors: list[dict[str, Any]],
    index: int,
    source_start: float,
    source_duration: float,
) -> dict[str, Any]:
    phase = (index - 1) / FRAME_COUNT
    nearest = nearest_anchor(anchors, phase)
    body: dict[str, Any] = {
        point: interpolate_point(
            [anchor["body"][point] for anchor in anchors],
            phase,
        )
        for point in BODY_POINTS
    }
    for scalar in SCALARS:
        value = interpolate_value(
            [float(anchor["body"][scalar]) for anchor in anchors],
            phase,
        )
        body[scalar] = round(value, 2) if scalar == "headAngleDegrees" else round(value)

    frame: dict[str, Any] = {
        "index": index,
        "phase": f"dense_video_phase_{index:02d}",
        "sourceSeconds": round(source_start + phase * source_duration, 4),
        "phaseFraction": round(phase, 4),
        "support": [],
        "occlusionOrder": copy.deepcopy(nearest["occlusionOrder"]),
        "body": body,
    }
    for limb in LIMBS:
        joint_count = len(anchors[0][limb]["joints"])
        joints = [
            interpolate_point(
                [anchor[limb]["joints"][joint] for anchor in anchors],
                phase,
            )
            for joint in range(joint_count)
        ]
        state = nearest[limb]["state"]
        if nearest["index"] != 1 or phase >= 1 / (FRAME_COUNT * 2):
            state = f"{state}_transition"
        frame[limb] = {"state": state, "joints": joints}

    separate_paws(frame)
    frame["support"] = [
        limb for limb in LIMBS if frame[limb]["joints"][-1][1] >= 431
    ]
    if index == FRAME_COUNT:
        frame["loopTo"] = 1
        frame["loopNote"] = (
            "The omitted 100% endpoint is the same pose as frame 01. Frame 25 to "
            "frame 01 is one normal 4% sampling interval, not a long wrap jump."
        )
    return frame


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--anchors",
        type=Path,
        default=Path("work/walking/walk_keyposes_8.json"),
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=Path("work/walking/walking_reference_source.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("work/walking/walk_spec.json"),
    )
    args = parser.parse_args()

    anchor_spec = json.loads(args.anchors.read_text(encoding="utf-8"))
    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    anchors = anchor_spec["frames"]
    cycle = metadata["selectedCycle"]
    natural_seconds = float(cycle["naturalDurationSeconds"])
    fps = FRAME_COUNT / natural_seconds

    spec = copy.deepcopy(anchor_spec)
    spec["name"] = "maodie-walking-video-driven-dense-v2"
    spec["schemaVersion"] = 3
    spec["frameCount"] = FRAME_COUNT
    spec["drivingReference"]["notes"] = (
        "One complete extended-walk stride, horizontally stabilized and sampled "
        "at 25 exact timestamps; the duplicated 100% endpoint is omitted."
    )
    spec["playback"] = {
        "fps": round(fps, 4),
        "cycleSeconds": natural_seconds,
        "frameIntervalSeconds": round(1 / fps, 4),
        "timingPolicy": (
            "25 equal phase samples across the same natural gait duration; higher "
            "frame count must not shorten or speed up the stride"
        ),
    }
    spec["sampling"] = {
        "sourceFrameCount": 25,
        "endpointIncluded": False,
        "periodicBoundary": True,
        "sourcePlaybackIntervalSeconds": cycle["referenceIntervalPlaybackSeconds"],
        "naturalIntervalSeconds": cycle["referenceIntervalNaturalSeconds"],
        "structuralMethod": (
            "Each output phase has an exact real-video timestamp. Periodic "
            "Catmull-Rom is used only to densify the manually identified whole-body "
            "landmarks while the source images remain the pose authority."
        ),
    }
    spec["frames"] = [
        build_frame(
            anchors,
            index,
            float(cycle["startSeconds"]),
            float(cycle["durationSeconds"]),
        )
        for index in range(1, FRAME_COUNT + 1)
    ]
    spec["invariants"]["frame25ToFrame1MustBeContinuous"] = True
    spec["invariants"].pop("frame8ToFrame1MustBeContinuous", None)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(spec, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
