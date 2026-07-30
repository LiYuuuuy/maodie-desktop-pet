#!/usr/bin/env python3
"""Render video-driven whole-body walking structure beside its source frames."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np


PANEL = 512
FRAME_WIDTH = PANEL * 2
LIMB_COLORS = {
    "LF": (68, 68, 239, 255),
    "RF": (246, 130, 59, 255),
    "LH": (94, 197, 34, 255),
    "RH": (8, 179, 234, 255),
}
NEAR_LIMBS = ("LF", "LH")
FAR_LIMBS = ("RF", "RH")


def clear_outputs(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for pattern in ("*.png", "*.webp"):
        for path in directory.glob(pattern):
            path.unlink()


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


def draw_limb(
    canvas: np.ndarray,
    name: str,
    limb: dict[str, object],
    far_side: bool,
) -> None:
    color = LIMB_COLORS[name]
    joints = [tuple(int(value) for value in point) for point in limb["joints"]]
    thickness = 12 if far_side else 16
    outline = (45, 48, 54, 255)
    cv2.polylines(canvas, [np.array(joints, np.int32)], False, outline, thickness + 6, cv2.LINE_AA)
    cv2.polylines(canvas, [np.array(joints, np.int32)], False, color, thickness, cv2.LINE_AA)
    for joint in joints:
        cv2.circle(canvas, joint, thickness // 2 + 3, outline, -1, cv2.LINE_AA)
        cv2.circle(canvas, joint, thickness // 2, color, -1, cv2.LINE_AA)
    paw = joints[-1]
    cv2.ellipse(canvas, paw, (14, 7), 0, 0, 360, outline, -1, cv2.LINE_AA)
    cv2.ellipse(canvas, paw, (11, 5), 0, 0, 360, color, -1, cv2.LINE_AA)
    cv2.putText(
        canvas,
        name,
        (paw[0] - 13, paw[1] - 13),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.46,
        (35, 35, 35, 255),
        2,
        cv2.LINE_AA,
    )


def draw_body(canvas: np.ndarray, body: dict[str, object]) -> None:
    center = tuple(int(value) for value in body["center"])
    shoulder = tuple(int(value) for value in body["shoulder"])
    hip = tuple(int(value) for value in body["hip"])
    head = tuple(int(value) for value in body["head"])
    tail_tip = tuple(int(value) for value in body["tailTip"])
    back_arch = int(body["backArchPx"])

    axis_angle = math.degrees(
        math.atan2(shoulder[1] - hip[1], shoulder[0] - hip[0])
    )
    outline = (55, 60, 69, 255)
    fill = (194, 201, 215, 245)
    cv2.ellipse(canvas, center, (121, 57), axis_angle, 0, 360, outline, -1, cv2.LINE_AA)
    cv2.ellipse(canvas, center, (116, 52), axis_angle, 0, 360, fill, -1, cv2.LINE_AA)

    neck_mid = ((shoulder[0] + head[0]) // 2, (shoulder[1] + head[1]) // 2)
    cv2.line(canvas, shoulder, neck_mid, outline, 48, cv2.LINE_AA)
    cv2.line(canvas, shoulder, neck_mid, fill, 40, cv2.LINE_AA)
    head_angle = float(body["headAngleDegrees"])
    cv2.ellipse(canvas, head, (49, 43), head_angle, 0, 360, outline, -1, cv2.LINE_AA)
    cv2.ellipse(canvas, head, (44, 38), head_angle, 0, 360, fill, -1, cv2.LINE_AA)
    ears = np.array(
        (
            (head[0] - 22, head[1] - 32),
            (head[0] - 10, head[1] - 62),
            (head[0] + 1, head[1] - 31),
            (head[0] + 15, head[1] - 31),
            (head[0] + 30, head[1] - 57),
            (head[0] + 36, head[1] - 24),
        ),
        np.int32,
    )
    cv2.fillPoly(canvas, [ears], outline, cv2.LINE_AA)

    tail_base = (hip[0] - 48, hip[1] - 12)
    control = (
        min(tail_base[0] - 18, tail_tip[0] + 28),
        min(tail_base[1] - 72, tail_tip[1] + 38),
    )
    tail_points = []
    for step in range(17):
        t = step / 16
        x = round(
            (1 - t) ** 2 * tail_base[0]
            + 2 * (1 - t) * t * control[0]
            + t**2 * tail_tip[0]
        )
        y = round(
            (1 - t) ** 2 * tail_base[1]
            + 2 * (1 - t) * t * control[1]
            + t**2 * tail_tip[1]
        )
        tail_points.append((x, y))
    cv2.polylines(
        canvas,
        [np.array(tail_points, np.int32)],
        False,
        outline,
        22,
        cv2.LINE_AA,
    )
    cv2.polylines(
        canvas,
        [np.array(tail_points, np.int32)],
        False,
        fill,
        15,
        cv2.LINE_AA,
    )

    back_points = np.array(
        (
            (hip[0] - 28, hip[1] - 47),
            (center[0] - 35, center[1] - 59 - back_arch),
            (center[0] + 35, center[1] - 58 - back_arch),
            (shoulder[0] + 15, shoulder[1] - 43),
        ),
        np.int32,
    )
    cv2.polylines(canvas, [back_points], False, (84, 92, 108, 255), 4, cv2.LINE_AA)
    cv2.arrowedLine(canvas, hip, shoulder, (126, 72, 34, 255), 3, cv2.LINE_AA, tipLength=0.08)
    cv2.circle(canvas, center, 7, (188, 72, 35, 255), -1, cv2.LINE_AA)
    cv2.putText(
        canvas,
        "COM",
        (center[0] - 20, center[1] - 12),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.4,
        (95, 45, 24, 255),
        1,
        cv2.LINE_AA,
    )


def render_structure(frame_spec: dict[str, object]) -> np.ndarray:
    canvas = np.full((PANEL, PANEL, 4), (247, 247, 245, 255), dtype=np.uint8)
    cv2.line(canvas, (28, 436), (484, 436), (112, 112, 112, 255), 2, cv2.LINE_AA)

    for name in FAR_LIMBS:
        draw_limb(canvas, name, frame_spec[name], far_side=True)
    body_layer = np.zeros_like(canvas)
    draw_body(body_layer, frame_spec["body"])
    canvas = alpha_over(canvas, body_layer)
    for name in NEAR_LIMBS:
        draw_limb(canvas, name, frame_spec[name], far_side=False)

    cv2.putText(
        canvas,
        f"WHOLE-BODY POSE {frame_spec['index']:02d}",
        (18, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (38, 38, 38, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        str(frame_spec["phase"]),
        (18, 56),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.52,
        (64, 64, 64, 255),
        1,
        cv2.LINE_AA,
    )
    return canvas


def render_comparison(reference: np.ndarray, structure: np.ndarray, frame_index: int) -> np.ndarray:
    output = np.full((PANEL, FRAME_WIDTH, 4), (238, 238, 236, 255), dtype=np.uint8)
    reference = cv2.resize(reference, (PANEL, 288), interpolation=cv2.INTER_CUBIC)
    reference_rgba = cv2.cvtColor(reference, cv2.COLOR_BGR2BGRA)
    output[104:392, 0:PANEL] = reference_rgba
    cv2.putText(
        output,
        f"VIDEO REFERENCE {frame_index:02d}",
        (18, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (38, 38, 38, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        output,
        "125 fps capture / fixed side view / full body",
        (18, 60),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        (70, 70, 70, 255),
        1,
        cv2.LINE_AA,
    )
    output[:, PANEL:FRAME_WIDTH] = structure
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, default=Path("work/walking/walk_spec.json"))
    parser.add_argument(
        "--references",
        type=Path,
        default=Path("work/walking/walking_reference_frames"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("work/walking/walking_pose_debug"),
    )
    args = parser.parse_args()

    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    clear_outputs(args.output)
    comparisons: list[np.ndarray] = []
    structures: list[np.ndarray] = []
    for frame_spec in spec["frames"]:
        index = int(frame_spec["index"])
        reference = cv2.imread(str(args.references / f"{index:02d}.png"))
        if reference is None:
            raise ValueError(f"missing reference frame {index:02d}")
        structure = render_structure(frame_spec)
        comparison = render_comparison(reference, structure, index)
        structures.append(structure)
        comparisons.append(comparison)
        cv2.imwrite(str(args.output / f"walking_pose_{index:02d}.png"), comparison)

    sheet = np.zeros((PANEL * 2, FRAME_WIDTH * 2, 4), dtype=np.uint8)
    for index, comparison in enumerate(comparisons):
        row, column = divmod(index, 2)
        if row >= 2:
            break
        sheet[
            row * PANEL : (row + 1) * PANEL,
            column * FRAME_WIDTH : (column + 1) * FRAME_WIDTH,
        ] = comparison
    # A compact sheet uses the structures alone so every phase remains legible.
    structure_sheet = np.zeros((PANEL * 2, PANEL * 4, 4), dtype=np.uint8)
    for index, structure in enumerate(structures):
        row, column = divmod(index, 4)
        structure_sheet[
            row * PANEL : (row + 1) * PANEL,
            column * PANEL : (column + 1) * PANEL,
        ] = structure
    cv2.imwrite(str(args.output / "walking_pose_debug_sheet.png"), structure_sheet)

    animation = cv2.Animation()
    animation.frames = structures
    animation.durations = [130] * len(structures)
    animation.loop_count = 0
    animation.bgcolor = (247, 247, 245, 255)
    if not cv2.imwriteanimation(str(args.output / "walking_pose_debug.webp"), animation):
        raise ValueError("unable to write walking pose debug animation")


if __name__ == "__main__":
    main()
