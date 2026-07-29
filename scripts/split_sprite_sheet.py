#!/usr/bin/env python3
"""Split a 4x2 RGB PNG contact sheet into eight 512px RGBA frames.

This intentionally uses only Python's standard library so asset preparation also
works in minimal build environments. It supports the non-interlaced 8-bit RGB
PNG files produced for this project.
"""

from __future__ import annotations

import argparse
import binascii
import struct
import zlib
from pathlib import Path


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else b if pb <= pc else c


def read_rgb_png(path: Path) -> tuple[int, int, bytes]:
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError(f"{path} is not a PNG")
    offset = len(PNG_SIGNATURE)
    chunks: list[bytes] = []
    width = height = 0
    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        offset += length + 12
        if kind == b"IHDR":
            width, height, depth, color_type, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
            if (depth, color_type, compression, filtering, interlace) != (8, 2, 0, 0, 0):
                raise ValueError("only non-interlaced 8-bit RGB PNG input is supported")
        elif kind == b"IDAT":
            chunks.append(payload)
        elif kind == b"IEND":
            break

    packed = zlib.decompress(b"".join(chunks))
    stride = width * 3
    output = bytearray(height * stride)
    source_offset = 0
    for y in range(height):
        filter_type = packed[source_offset]
        source_offset += 1
        row = packed[source_offset : source_offset + stride]
        source_offset += stride
        for x, value in enumerate(row):
            left = output[y * stride + x - 3] if x >= 3 else 0
            above = output[(y - 1) * stride + x] if y else 0
            upper_left = output[(y - 1) * stride + x - 3] if y and x >= 3 else 0
            if filter_type == 0:
                decoded = value
            elif filter_type == 1:
                decoded = value + left
            elif filter_type == 2:
                decoded = value + above
            elif filter_type == 3:
                decoded = value + ((left + above) // 2)
            elif filter_type == 4:
                decoded = value + _paeth(left, above, upper_left)
            else:
                raise ValueError(f"unsupported PNG filter {filter_type}")
            output[y * stride + x] = decoded & 0xFF
    return width, height, bytes(output)


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)
    )


def write_rgba_png(path: Path, width: int, height: int, rgba: bytes) -> None:
    rows = b"".join(
        b"\x00" + rgba[y * width * 4 : (y + 1) * width * 4] for y in range(height)
    )
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    path.write_bytes(
        PNG_SIGNATURE
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(rows, 9))
        + _chunk(b"IEND", b"")
    )


def chroma_alpha(r: int, g: int, b: int) -> tuple[int, int, int, int]:
    dominance = g - max(r, b)
    if g > 180 and dominance >= 105:
        return r, min(g, max(r, b) + 8), b, 0
    if g > 140 and dominance > 55:
        alpha = int(255 * (105 - dominance) / 50)
        return r, min(g, max(r, b) + 12), b, max(0, min(255, alpha))
    return r, g, b, 255


def split_sheet(source: Path, output_dir: Path) -> None:
    width, height, rgb = read_rgb_png(source)
    output_dir.mkdir(parents=True, exist_ok=True)
    for frame in range(8):
        column, row = frame % 4, frame // 4
        left, right = round(column * width / 4), round((column + 1) * width / 4)
        top, bottom = round(row * height / 2), round((row + 1) * height / 2)
        cell_width, cell_height = right - left, bottom - top
        rgba = bytearray(512 * 512 * 4)
        for out_y in range(512):
            source_y = top + min(cell_height - 1, int(out_y * cell_height / 512))
            for out_x in range(512):
                source_x = left + min(cell_width - 1, int(out_x * cell_width / 512))
                index = (source_y * width + source_x) * 3
                pixel = chroma_alpha(*rgb[index : index + 3])
                target = (out_y * 512 + out_x) * 4
                rgba[target : target + 4] = bytes(pixel)
        write_rgba_png(output_dir / f"{frame:02d}.png", 512, 512, bytes(rgba))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    split_sheet(args.source, args.output_dir)


if __name__ == "__main__":
    main()
