"""Shared test fixtures: a real PNG encoder for exercising the decoder.

The encoder forward-applies any of the five PNG filter types so the decoder's
inverse filters get genuine round-trip coverage (not just the filter-0 path).
"""

from __future__ import annotations

import struct
import zlib

import pytest

_CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4}


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def _chunk(ctype: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + ctype + data + struct.pack(
        ">I", zlib.crc32(ctype + data) & 0xFFFFFFFF
    )


def _encode(width: int, height: int, pixels: bytes, color_type: int = 2, filter_type: int = 0) -> bytes:
    channels = _CHANNELS[color_type]
    bpp = channels
    stride = width * channels
    assert len(pixels) == stride * height, "pixel buffer size mismatch"

    body = bytearray()
    prev = bytearray(stride)
    for y in range(height):
        row = bytearray(pixels[y * stride : (y + 1) * stride])
        filt = bytearray(stride)
        for i in range(stride):
            left = row[i - bpp] if i >= bpp else 0
            up = prev[i]
            up_left = prev[i - bpp] if i >= bpp else 0
            x = row[i]
            if filter_type == 0:
                f = x
            elif filter_type == 1:
                f = (x - left) & 0xFF
            elif filter_type == 2:
                f = (x - up) & 0xFF
            elif filter_type == 3:
                f = (x - ((left + up) >> 1)) & 0xFF
            elif filter_type == 4:
                f = (x - _paeth(left, up, up_left)) & 0xFF
            else:
                raise ValueError(f"bad filter {filter_type}")
            filt[i] = f
        body.append(filter_type)
        body.extend(filt)
        prev = row

    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(bytes(body), 9))
        + _chunk(b"IEND", b"")
    )


@pytest.fixture
def make_png():
    return _encode


@pytest.fixture
def gradient_rgb():
    """A 16x16 RGB image with real horizontal structure (for non-trivial dHash)."""

    def _build(invert: bool = False) -> bytes:
        w = h = 16
        px = bytearray()
        for _y in range(h):
            for x in range(w):
                v = int(x / (w - 1) * 255)
                if invert:
                    v = 255 - v
                px += bytes([v, v, v])
        return _encode(w, h, bytes(px), color_type=2)

    return _build


@pytest.fixture
def raw_bgra_frame():
    """Build a raw BGRA Frame with real horizontal structure (for the fast path).

    Returns (frame, bgra_bytes, width, height) so a test can both perceive the
    frame and re-derive its identity/perceptual hash independently.
    """
    from coherence_membrane.capture import Frame, FrameDescriptor

    def _build(width: int = 16, height: int = 16, *, invert: bool = False,
               frame_index: int = 0, source_id: str = "test") -> tuple:
        # R is a centre-peak tent (non-monotonic -> non-trivial dHash); B is a
        # horizontal ramp with a DIFFERENT profile, so an R<->B byte-order swap
        # changes the hash. invert flips the tent into a valley (a real change).
        cx = (width - 1) / 2 if width > 1 else 0.0
        bgra = bytearray()
        for _y in range(height):
            for x in range(width):
                r = int(255 * (1 - abs(x - cx) / cx)) if cx else 0
                if invert:
                    r = 255 - r
                b = (x * 255) // (width - 1) if width > 1 else 0
                bgra += bytes([b, 64, r, 255])  # B, G, R, A
        payload = bytes(bgra)
        frame = Frame(
            descriptor=FrameDescriptor(source_id=source_id, frame_index=frame_index,
                                       width=width, height=height, pixel_format="bgra"),
            payload=payload,
        )
        return frame, payload, width, height

    return _build
