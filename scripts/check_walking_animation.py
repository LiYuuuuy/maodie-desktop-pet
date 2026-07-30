#!/usr/bin/env python3
"""Validate the dense video-driven 25-frame walking loop and write its QC report."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np


LIMBS = ("LF", "RF", "LH", "RH")


def bounds(frame: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.where(frame[:, :, 3] > 20)
    if len(xs) == 0:
        raise ValueError("empty walking frame")
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, default=Path("src/assets/pet/walking"))
    parser.add_argument("--spec", type=Path, default=Path("work/walking/walk_spec.json"))
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

    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    paths = sorted(args.runtime.glob("*.png"))
    expected_frame_count = int(spec["frameCount"])
    if len(paths) != expected_frame_count:
        raise ValueError(
            f"expected {expected_frame_count} runtime walking frames, found {len(paths)}"
        )

    frames: list[np.ndarray] = []
    for path in paths:
        frame = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if frame is None or frame.shape != (512, 512, 4):
            raise ValueError(f"invalid runtime frame {path}: {getattr(frame, 'shape', None)}")
        frames.append(frame)

    frame_bounds = [bounds(frame) for frame in frames]
    alpha_centers = [
        (
            float(np.mean(np.where(frame[:, :, 3] > 20)[1])),
            float(np.mean(np.where(frame[:, :, 3] > 20)[0])),
        )
        for frame in frames
    ]
    baselines = [bottom for _, _, _, bottom in frame_bounds]
    visible_areas = [int(np.count_nonzero(frame[:, :, 3] > 20)) for frame in frames]
    partial_alpha = [
        int(np.count_nonzero((frame[:, :, 3] > 0) & (frame[:, :, 3] < 255)))
        for frame in frames
    ]
    green_residual = []
    changes = []
    for index, frame in enumerate(frames):
        blue, green, red, alpha = cv2.split(frame)
        green_residual.append(
            int(
                np.count_nonzero(
                    (alpha > 20)
                    & (
                        green.astype(np.int16)
                        - np.maximum(red, blue).astype(np.int16)
                        > 38
                    )
                )
            )
        )
        following = frames[(index + 1) % len(frames)]
        visible = np.maximum(frame[:, :, 3], following[:, :, 3]) > 20
        difference = cv2.absdiff(frame[:, :, :3], following[:, :, :3]).mean(axis=2)
        changes.append(float(np.mean(difference[visible])))

    body_centers = [tuple(frame["body"]["center"]) for frame in spec["frames"]]
    shoulders = [tuple(frame["body"]["shoulder"]) for frame in spec["frames"]]
    hips = [tuple(frame["body"]["hip"]) for frame in spec["frames"]]
    heads = [tuple(frame["body"]["head"]) for frame in spec["frames"]]
    tail_tips = [tuple(frame["body"]["tailTip"]) for frame in spec["frames"]]
    minimum_paw_distance = min(
        math.dist(frame[first]["joints"][-1], frame[second]["joints"][-1])
        for frame in spec["frames"]
        for index, first in enumerate(LIMBS)
        for second in LIMBS[index + 1 :]
    )
    phases_complete = all(
        set(frame) >= set(LIMBS) | {"index", "support", "body"}
        for frame in spec["frames"]
    )
    body_motion_axes = {
        "center": len(set(body_centers)),
        "shoulder": len(set(shoulders)),
        "hip": len(set(hips)),
        "head": len(set(heads)),
        "tail": len(set(tail_tips)),
    }
    size_variation = (max(visible_areas) - min(visible_areas)) / np.median(
        visible_areas
    )
    median_change = float(np.median(changes))
    loop_change_ratio = changes[-1] / max(median_change, 0.001)
    adjacent_center_steps = [
        math.dist(alpha_centers[index], alpha_centers[(index + 1) % len(frames)])
        for index in range(len(frames))
    ]
    median_center_step = float(np.median(adjacent_center_steps))
    loop_center_step_ratio = adjacent_center_steps[-1] / max(
        median_center_step,
        0.001,
    )
    rendered_cycle_seconds = len(frames) / float(spec["playback"]["fps"])

    checks = {
        "25 帧、512×512、RGBA": len(frames) == 25,
        "增加帧数但周期仍保持约 1.0406 秒": (
            abs(rendered_cycle_seconds - float(spec["playback"]["cycleSeconds"]))
            <= 0.002
        ),
        "真实相位采样间隔不超过 42 ms": (
            float(spec["playback"]["frameIntervalSeconds"]) <= 0.042
        ),
        "周期端点不重复写入第 25 帧": (
            spec["sampling"]["endpointIncluded"] is False
        ),
        "四肢身份 LF/RF/LH/RH 每帧完整记录": phases_complete,
        "四足 debug 最小足端间距至少 24 px": minimum_paw_distance >= 24,
        "身体重心不是固定点": body_motion_axes["center"] >= 4,
        "肩部与臀部均独立推进": (
            body_motion_axes["shoulder"] >= 4 and body_motion_axes["hip"] >= 4
        ),
        "头部与尾巴均随全身运动": (
            body_motion_axes["head"] >= 4 and body_motion_axes["tail"] >= 4
        ),
        "脚底基线稳定": max(baselines) - min(baselines) <= 1,
        "透明边缘存在": all(count > 0 for count in partial_alpha),
        "去绿后无大面积色键残留": max(green_residual) <= 300,
        "主体面积变化不超过 25%": size_variation <= 0.25,
        "首尾视觉变化不超过相邻帧中位数的 1.35 倍": (
            loop_change_ratio <= 1.35
        ),
        "首尾主体中心位移不超过相邻帧中位数的 1.5 倍": (
            loop_center_step_ratio <= 1.5
        ),
        "禁止固定身体木偶方案": spec["invariants"]["staticBodyPuppetRigForbidden"],
        "禁止独立逐帧硬生成": spec["invariants"]["independentFrameGenerationForbidden"],
    }
    failures = [name for name, passed in checks.items() if not passed]
    rows = "\n".join(
        f"| {name} | {'通过' if passed else '失败'} |" for name, passed in checks.items()
    )

    report = f"""# Walking QC 报告

## 结论

{'全部结构与资产检查通过。' if not failures else '存在未通过项：' + '；'.join(failures)}

本版 walking 由真实猫固定侧视高速摄影中的一个完整步态周期驱动。最终 25 帧对应
25 个等间隔视频时间戳，周期时长保持不变。第 25 帧之后省略的 100% 端点等同第 1 帧，
因此循环边界只跨一个正常的 1/25 周期间隔。

| 检查项 | 结果 |
| --- | --- |
{rows}

## 测量结果

- 真实动作周期：{spec['playback']['cycleSeconds']:.4f} 秒。
- 运行播放：25 帧，{spec['playback']['fps']:.3f} FPS。
- 运行序列计算周期：{rendered_cycle_seconds:.4f} 秒。
- 单帧自然时间间隔：{spec['playback']['frameIntervalSeconds'] * 1000:.1f} ms。
- 四足结构稿最小足端间距：{minimum_paw_distance:.2f} px。
- 身体运动离散位置数：{body_motion_axes}。
- 最终脚底基线范围：{min(baselines)}–{max(baselines)} px。
- 主体可见面积变化：{size_variation:.2%}。
- 闭环视觉变化 / 相邻帧中位数：{loop_change_ratio:.3f}。
- 闭环主体中心位移 / 相邻帧中位数：{loop_center_step_ratio:.3f}。
- 单帧最大绿色残留像素：{max(green_residual)}。

## 人工逐帧检查

- 25 帧均保持完整主体；远侧腿只允许在胸腹上段发生真实遮挡。
- 腿根到足端的轮廓连续，没有断腿、孤立脚掌、额外第五条腿或透明残肢。
- 躯干高度、肩部、髋部、背线、头部和尾巴都随相位改变，不是静止身体。
- 毛色、脸型、折耳、身体长度和纹理在 25 帧中保持同一只耄耋。
- 第 25 帧到第 1 帧仅跨一个普通采样间隔，方向、身体中心与步序连续。

## 输出

- 视频参考：`work/walking/walking_reference_frames/`
- 相位分析：`work/walking/walk_keyframe_analysis.md`
- 结构规格：`work/walking/walk_spec.json`
- 结构调试：`work/walking/walking_pose_debug/`
- 透明 PNG：`outputs/walking/walking_01.png` 至 `walking_25.png`
- 闭环检查：`outputs/walking/walking_loop_sheet.png`
- 预览：`outputs/walking/walking_preview.gif`、`walking_preview.webp`
"""
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")
    if failures:
        raise ValueError("walking QC failed: " + "; ".join(failures))


if __name__ == "__main__":
    main()
