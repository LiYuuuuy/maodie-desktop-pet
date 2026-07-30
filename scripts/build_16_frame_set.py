#!/usr/bin/env python3
"""Interleave an eight-frame source sheet with an eight-frame midpoint sheet."""

from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path

from split_sprite_sheet import split_sheet


def build(source_sheet: Path, midpoint_sheet: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="maodie-frames-") as temporary:
        root = Path(temporary)
        source_frames = root / "source"
        midpoint_frames = root / "midpoint"
        split_sheet(source_sheet, source_frames)
        split_sheet(midpoint_sheet, midpoint_frames)
        for index in range(8):
            shutil.copyfile(source_frames / f"{index:02d}.png", output_dir / f"{index * 2:02d}.png")
            shutil.copyfile(
                midpoint_frames / f"{index:02d}.png",
                output_dir / f"{index * 2 + 1:02d}.png",
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_sheet", type=Path)
    parser.add_argument("midpoint_sheet", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    build(args.source_sheet, args.midpoint_sheet, args.output_dir)


if __name__ == "__main__":
    main()
