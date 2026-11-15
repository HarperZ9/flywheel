"""A minimal, dependency-free PNG decoder -- stdlib only (zlib + struct).

Why this exists: the membrane's job is to turn raw artifact bytes into a
*witnessed projection a model can ground on*.  For an image that means real
pixels, not a guess from a filename.  Keeping the decoder in the standard
library keeps the whole projection re-derivable by anyone, with no opaque
third-party image stack in the trust path.

Scope (honest about coverage): bit depth 8, non-interlaced, colour types
0 (grayscale), 2 (RGB), 4 (grayscale+alpha), 6 (RGBA).  Palette (type 3),
16-bit, and interlaced PNGs are not decoded -- `decode_png` raises
PngDecodeError and the caller degrades to identity-only, never crashes.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# colour type -> channels per pixel
_CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4}


class PngDecodeError(Exception):
    """Raised for any PNG this minimal decoder does not handle, or malformed
    input.  Callers treat it as 'cannot perceive', never as a crash."""


@dataclass(frozen=True)
class DecodedImage:
    width: int
    height: int
    channels: int
    color_type: int
    pixels: bytes  # row-major, width*height*channels bytes, 8-bit


def is_png(payload: bytes) -> bool:
    return payload[:8] == _PNG_SIGNATURE


def _iter_chunks(payload: bytes):
    offset = 8
    n = len(payload)
    while offset + 8 <= n:
        (length,) = struct.unpack(">I", payload[offset : offset + 4])
        ctype = payload[offset + 4 : offset + 8]
        start = offset + 8
        end = start + length
        if end + 4 > n:
            raise PngDecodeError("truncated chunk")
        yield ctype, payload[start:end]
        offset = end + 4  # skip the 4-byte CRC
    if offset != n:
        # trailing bytes after the last complete chunk
        raise PngDecodeError("trailing bytes after final chunk")


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _defilter(raw: bytes, width: int, height: int, channels: int) -> bytes:
    """Reverse PNG scanline filters (types 0-4) into raw pixel bytes."""
    stride = width * channels
    bpp = channels  # 8-bit: bytes-per-pixel == channels
    expected = (stride + 1) * height
    if len(raw) < expected:
        raise PngDecodeError("decompressed data shorter than expected")

    out = bytearray(stride * height)
    prev = bytearray(stride)  # the scanline above (all zero for row 0)
    pos = 0
    for row in range(height):
        ftype = raw[pos]
        pos += 1
        line = bytearray(raw[pos : pos + stride])
        pos += stride
        if ftype == 0:  # None
            pass
        elif ftype == 1:  # Sub
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + left) & 0xFF
        elif ftype == 2:  # Up
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:  # Average
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:  # Paeth
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                up_left = prev[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + _paeth(left, prev[i], up_left)) & 0xFF
        else:
            raise PngDecodeError(f"unknown filter type {ftype}")
        out[row * stride : (row + 1) * stride] = line
        prev = line
    return bytes(out)


def decode_png(payload: bytes) -> DecodedImage:
    """Decode an 8-bit, non-interlaced PNG to raw pixel bytes.

    Raises PngDecodeError for anything outside the supported scope or for
    malformed input -- never returns partial/garbage pixels.
    """
    if not is_png(payload):
        raise PngDecodeError("not a PNG (bad signature)")

    width = height = bit_depth = color_type = interlace = -1
    idat = bytearray()
    saw_ihdr = saw_iend = False

    for ctype, data in _iter_chunks(payload):
        if ctype == b"IHDR":
            if len(data) != 13:
                raise PngDecodeError("bad IHDR length")
            (width, height, bit_depth, color_type, _comp, _filt, interlace) = struct.unpack(
                ">IIBBBBB", data
            )
            saw_ihdr = True
        elif ctype == b"IDAT":
            idat.extend(data)
        elif ctype == b"IEND":
            saw_iend = True
            break

    if not saw_ihdr:
        raise PngDecodeError("missing IHDR")
    if not saw_iend:
        raise PngDecodeError("missing IEND")
    if bit_depth != 8:
        raise PngDecodeError(f"unsupported bit depth {bit_depth} (only 8 supported)")
    if interlace != 0:
        raise PngDecodeError("interlaced PNG not supported")
    if color_type not in _CHANNELS:
        raise PngDecodeError(f"unsupported colour type {color_type}")
    if width <= 0 or height <= 0:
        raise PngDecodeError("non-positive dimensions")

    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error as exc:
        raise PngDecodeError(f"zlib inflate failed: {exc}") from exc

    channels = _CHANNELS[color_type]
    pixels = _defilter(raw, width, height, channels)
    return DecodedImage(
        width=width,
        height=height,
        channels=channels,
        color_type=color_type,
        pixels=pixels,
    )


def read_ihdr(payload: bytes) -> tuple[int, int, int, int]:
    """Cheap header-only read: (width, height, bit_depth, color_type).

    Works even when full decode is unsupported (e.g. 16-bit or palette), so the
    organ can still report dimensions for any structurally-valid PNG.
    """
    if not is_png(payload):
        raise PngDecodeError("not a PNG (bad signature)")
    if len(payload) < 33:
        raise PngDecodeError("too short for IHDR")
    (length,) = struct.unpack(">I", payload[8:12])
    if payload[12:16] != b"IHDR" or length != 13:
        raise PngDecodeError("first chunk is not a valid IHDR")
    width, height, bit_depth, color_type = struct.unpack(">IIBB", payload[16:26])
    return width, height, bit_depth, color_type
