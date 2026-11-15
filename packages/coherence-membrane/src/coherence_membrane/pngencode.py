"""A minimal, dependency-free PNG encoder -- stdlib only (zlib + struct).

The native capture path produces raw pixels; this turns them into a PNG the
VisualArtifactOrgan can witness (identity + dimensions + perceptual hash) with no
third-party image library in the trust path.  Filter type 0 (None) only -- simple,
correct, and the decoder handles all filter types regardless.
"""

from __future__ import annotations

import struct
import zlib

# channels -> PNG colour type
_COLOR_TYPE = {1: 0, 2: 4, 3: 2, 4: 6}


def _chunk(ctype: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + ctype + data + struct.pack(
        ">I", zlib.crc32(ctype + data) & 0xFFFFFFFF
    )


def encode_png(width: int, height: int, pixels: bytes, channels: int = 3) -> bytes:
    """Encode 8-bit pixels (row-major, width*height*channels bytes) to PNG bytes."""
    if channels not in _COLOR_TYPE:
        raise ValueError(f"unsupported channel count {channels}")
    stride = width * channels
    if len(pixels) != stride * height:
        raise ValueError("pixel buffer size does not match width*height*channels")
    body = bytearray()
    for y in range(height):
        body.append(0)  # filter: None
        body += pixels[y * stride : (y + 1) * stride]
    ihdr = struct.pack(">IIBBBBB", width, height, 8, _COLOR_TYPE[channels], 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(bytes(body), 6))
        + _chunk(b"IEND", b"")
    )


def bgra_to_rgb(bgra: bytes, width: int, height: int) -> bytes:
    """Convert a top-down BGRA buffer (the OS capture layout) to packed RGB."""
    mv = memoryview(bgra)
    out = bytearray(width * height * 3)
    out[0::3] = mv[2::4]  # R <- B-G-R-A's R
    out[1::3] = mv[1::4]  # G
    out[2::3] = mv[0::4]  # B
    return bytes(out)
