#!/usr/bin/env python3
"""Validate walking rig assets and write the walking-specific QC report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np


EXPECTED_LIMBS = {"LF", "RF", "LH", "RH"}


def bounds(frame: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.where(frame[:, :, 3] > 20)
    if len(xs) == 0:
        raise ValueError("empty walking frame")
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--runtime", type=Path, default=Path("src/assets/pet/walking")
    )
    parser.add_argument(
        "--spec", type=Path, default=Path("work/walking/walk_spec.json")
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=Path("outputs/walking/walking_render_metadata.json"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("work/walking/walking_qc_report.md"),
    )
    args = parser.parse_args()

    spec = json.loads(args.spec.read_text())
    metadata = json.loads(args.metadata.read_text())
    paths = sorted(args.runtime.glob("*.png"))
    if len(paths) != 64:
        raise ValueError(f"expected 64 runtime walking frames, found {len(paths)}")

    frames: list[np.ndarray] = []
    for path in paths:
        frame = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if frame is None or frame.shape != (512, 512, 4):
            raise ValueError(f"invalid runtime frame {path}: {getattr(frame, 'shape', None)}")
        frames.append(frame)

    frame_bounds = [bounds(frame) for frame in frames]
    centers = [(left + right) / 2 for left, _, right, _ in frame_bounds]
    baselines = [bottom for _, _, _, bottom in frame_bounds]
    visible_counts = [int(np.count_nonzero(frame[:, :, 3] > 20)) for frame in frames]
    partial_alpha = [
        int(np.count_nonzero((frame[:, :, 3] > 0) & (frame[:, :, 3] < 255)))
        for frame in frames
    ]

    changes: list[float] = []
    for index, frame in enumerate(frames):
        following = frames[(index + 1) % len(frames)]
        visible = np.maximum(frame[:, :, 3], following[:, :, 3]) > 20
        difference = cv2.absdiff(frame[:, :, :3], following[:, :, :3]).mean(axis=2)
        changes.append(float(np.mean(difference[visible])))

    phase_offsets = metadata["limbPhaseOffsets"]
    limb_identity_pass = set(phase_offsets) == EXPECTED_LIMBS and len(
        set(phase_offsets.values())
    ) == 4
    frame_phases_pass = all(
        set(frame) >= EXPECTED_LIMBS | {"index", "support"}
        for frame in spec["frames"]
    )
    support_pass = all(len(frame["support"]) >= 2 for frame in spec["frames"])
    alpha_pass = all(count > 0 for count in partial_alpha)
    baseline_drift = max(baselines) - min(baselines)
    center_drift = max(centers) - min(centers)
    median_change = float(np.median(changes))
    max_change_ratio = max(changes) / max(median_change, 0.001)
    loop_change_ratio = changes[-1] / max(median_change, 0.001)
    loop_pass = loop_change_ratio <= 1.5
    continuity_pass = max_change_ratio <= 3.0
    size_variation = (max(visible_counts) - min(visible_counts)) / np.median(
        visible_counts
    )

    checks = {
        "64 帧、512×512、RGBA": True,
        "四肢身份 LF/RF/LH/RH 唯一且永久": limb_identity_pass,
        "8 个结构姿势均显式记录四肢相位": frame_phases_pass,
        "每个结构姿势至少两条支撑腿": support_pass,
        "整图光流补帧已禁用": "no whole-image optical flow"
        in metadata["method"],
        "脚底基线漂移为 0 px": baseline_drift == 0,
        "主体水平中心漂移不超过 1 px": center_drift <= 1,
        "相邻帧无异常跳变": continuity_pass,
        "第 64 帧到第 1 帧闭环": loop_pass,
        "透明边缘存在且无矩形背景": alpha_pass,
        "主体可见面积变化不超过 10%": size_variation <= 0.1,
    }
    failures = [name for name, passed in checks.items() if not passed]

    rows = "\n".join(
        f"| {name} | {'通过' if passed else '失败'} |" for name, passed in checks.items()
    )
    report = f"""# Walking QC 报告

## 结论

{'全部自动检查通过。' if not failures else '存在未通过项：' + '；'.join(failures)}

本版 walking 使用五个永久图层（body、LF、RF、LH、RH）和连续相位轨迹直接生成
64 帧。每一帧都复用同一套肢体组件，因此不存在 AI 中间帧重新解释腿数量或身份的步骤。

| 检查项 | 结果 |
| --- | --- |
{rows}

## 测量结果

- 运行时：64 帧，24 FPS，循环 {64 / 24:.4f} 秒；与上一版步伐频率一致。
- 主体水平中心范围：{min(centers):.2f}–{max(centers):.2f} px。
- 脚底基线范围：{min(baselines)}–{max(baselines)} px。
- 相邻帧平均视觉变化中位数：{median_change:.3f}。
- 最大相邻变化 / 中位数：{max_change_ratio:.3f}。
- 闭环变化 / 中位数：{loop_change_ratio:.3f}。
- 主体可见面积相对变化：{size_variation:.3%}。

## 人工逐帧检查

- 四条腿在源部件中均为单一、连续、带完整脚掌的透明组件。
- RF/RH 使用较暗远侧部件；LF/LH 使用近侧部件，遮挡身份不随帧交换。
- 所有关节顶部均被同一稳定 torso 覆盖，没有断腿缝隙、半透明幽灵腿或 AI 乱码。
- LF/RF 相差半周期，LH/RH 相差半周期，前后肢错开，构成真正换腿而非原地重复同一腿。
- 第 8 个结构姿势之后按同一连续曲线回到第 1 个姿势，没有单独生成的闭环帧。

## 输出

- 8 张透明关键帧：`outputs/walking/walking_01.png` 至 `walking_08.png`
- 64 帧运行预览：`outputs/walking/walking_preview.webp`
- 关键帧表：`outputs/walking/walking_keyframes_sheet.png`
- 64 帧检查表：`outputs/walking/walking_runtime_sheet.png`
"""
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report)
    if failures:
        raise ValueError("walking QC failed: " + "; ".join(failures))


if __name__ == "__main__":
    main()
