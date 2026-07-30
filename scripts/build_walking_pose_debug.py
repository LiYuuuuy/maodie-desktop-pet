#!/usr/bin/env python3
"""Render the walking rig specification as eight color-coded structure frames."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np


CANVAS = 512
PHASE_PAW = (
    (36, 0),
    (24, 0),
    (8, 0),
    (-10, 0),
    (-27, 0),
    (-18, -14),
    (3, -30),
    (29, -17),
)
PHASE_KNEE = (
    (19, -48),
    (13, -47),
    (4, -46),
    (-5, -44),
    (-13, -41),
    (-20, -47),
    (-9, -56),
    (12, -56),
)


def alpha_over(background: np.ndarray, foreground: np.ndarray) -> np.ndarray:
    alpha = foreground[:, :, 3:4].astype(np.float32) / 255
    output = background.astype(np.float32)
    output[:, :, :3] = foreground[:, :, :3] * alpha + output[:, :, :3] * (1 - alpha)
    output[:, :, 3:4] = np.maximum(output[:, :, 3:4], foreground[:, :, 3:4])
    return np.clip(output, 0, 255).astype(np.uint8)


def body_layer(bob: int) -> np.ndarray:
    layer = np.zeros((CANVAS, CANVAS, 4), dtype=np.uint8)
    body_color = (174, 183, 214, 238)
    outline = (55, 62, 72, 255)
    cv2.ellipse(layer, (252, 375 + bob), (120, 61), 0, 0, 360, outline, 9)
    cv2.ellipse(layer, (252, 375 + bob), (116, 57), 0, 0, 360, body_color, -1)
    cv2.circle(layer, (365, 347 + bob), 54, outline, -1)
    cv2.circle(layer, (365, 347 + bob), 49, body_color, -1)
    cv2.ellipse(layer, (135, 376 + bob), (54, 13), -18, 170, 350, outline, 8)
    cv2.ellipse(layer, (135, 376 + bob), (49, 9), -18, 170, 350, body_color, -1)
    cv2.putText(
        layer,
        "BODY (locked)",
        (211, 370 + bob),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (45, 50, 60, 255),
        2,
        cv2.LINE_AA,
    )
    return layer


def limb_layer(
    name: str,
    anchor: tuple[int, int],
    phase: int,
    color: tuple[int, int, int],
    bob: int,
) -> np.ndarray:
    layer = np.zeros((CANVAS, CANVAS, 4), dtype=np.uint8)
    anchor_x, anchor_y = anchor[0], anchor[1] + bob
    paw_dx, paw_dy = PHASE_PAW[phase]
    knee_dx, knee_dy = PHASE_KNEE[phase]
    knee = (anchor_x + knee_dx, anchor_y + knee_dy + 47)
    paw = (anchor_x + paw_dx, 476 + paw_dy)
    opaque = (*color, 255)
    cv2.line(layer, (anchor_x, anchor_y), knee, opaque, 15, cv2.LINE_AA)
    cv2.line(layer, knee, paw, opaque, 13, cv2.LINE_AA)
    cv2.circle(layer, (anchor_x, anchor_y), 8, opaque, -1, cv2.LINE_AA)
    cv2.circle(layer, knee, 7, opaque, -1, cv2.LINE_AA)
    cv2.ellipse(layer, paw, (13, 7), 0, 0, 360, opaque, -1, cv2.LINE_AA)
    cv2.putText(
        layer,
        name,
        (paw[0] - 12, paw[1] - 10),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        (20, 20, 20, 255),
        2,
        cv2.LINE_AA,
    )
    return layer


def render_frame(spec: dict[str, object], frame_index: int) -> np.ndarray:
    frame = np.zeros((CANVAS, CANVAS, 4), dtype=np.uint8)
    frame[:, :, :3] = (244, 244, 244)
    frame[:, :, 3] = 255
    bob = round(2 * math.sin(frame_index / 8 * math.tau))
    limbs = spec["limbs"]

    for name in ("RF", "RH"):
        limb = limbs[name]
        phase = (frame_index + int(limb["phaseOffset"])) % 8
        frame = alpha_over(
            frame,
            limb_layer(
                name,
                tuple(limb["anchor"]),
                phase,
                tuple(limb["colorBgr"]),
                bob,
            ),
        )

    frame = alpha_over(frame, body_layer(bob))

    for name in ("LF", "LH"):
        limb = limbs[name]
        phase = (frame_index + int(limb["phaseOffset"])) % 8
        frame = alpha_over(
            frame,
            limb_layer(
                name,
                tuple(limb["anchor"]),
                phase,
                tuple(limb["colorBgr"]),
                bob,
            ),
        )

    frame_spec = spec["frames"][frame_index]
    cv2.putText(
        frame,
        f"POSE {frame_index + 1}/8  support: {'+'.join(frame_spec['support'])}",
        (22, 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (35, 35, 35, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.line(frame, (36, 487), (476, 487), (95, 95, 95, 255), 1, cv2.LINE_AA)
    return frame


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, default=Path("work/walking/walk_spec.json"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("work/walking/walking_pose_debug"),
    )
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text())
    args.output.mkdir(parents=True, exist_ok=True)

    frames = [render_frame(spec, index) for index in range(8)]
    for index, frame in enumerate(frames, start=1):
        cv2.imwrite(str(args.output / f"walking_pose_{index:02d}.png"), frame)

    sheet = np.zeros((CANVAS * 2, CANVAS * 4, 4), dtype=np.uint8)
    for index, frame in enumerate(frames):
        row, column = divmod(index, 4)
        sheet[row * CANVAS : (row + 1) * CANVAS, column * CANVAS : (column + 1) * CANVAS] = frame
    cv2.imwrite(str(args.output / "walking_pose_debug_sheet.png"), sheet)

    animation = cv2.Animation()
    animation.frames = frames
    animation.durations = [333] * len(frames)
    animation.loop_count = 0
    animation.bgcolor = (244, 244, 244, 255)
    if not cv2.imwriteanimation(str(args.output / "walking_pose_debug.webp"), animation):
        raise ValueError("unable to write walking pose debug animation")


if __name__ == "__main__":
    main()
