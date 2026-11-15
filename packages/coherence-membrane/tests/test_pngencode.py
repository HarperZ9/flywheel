"""Tests for the stdlib PNG encoder and the BGRA->RGB conversion."""

from __future__ import annotations

import pytest

from coherence_membrane.pngencode import bgra_to_rgb, encode_png
from coherence_membrane.pngview import decode_png


def test_encode_decode_rgb_roundtrip():
    pixels = bytes([255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 255])  # 2x2 RGB
    img = decode_png(encode_png(2, 2, pixels, channels=3))
    assert (img.width, img.height, img.channels) == (2, 2, 3)
    assert img.pixels == pixels


def test_encode_decode_grayscale_roundtrip():
    pixels = bytes([0, 64, 128, 255])
    img = decode_png(encode_png(2, 2, pixels, channels=1))
    assert img.channels == 1
    assert img.pixels == pixels


def test_encode_decode_rgba_roundtrip():
    pixels = bytes(range(16))  # 2x2 RGBA
    img = decode_png(encode_png(2, 2, pixels, channels=4))
    assert img.channels == 4
    assert img.pixels == pixels


def test_bgra_to_rgb_ordering():
    bgra = bytes([10, 20, 30, 255, 40, 50, 60, 255])  # 2 px, B,G,R,A
    assert bgra_to_rgb(bgra, 2, 1) == bytes([30, 20, 10, 60, 50, 40])


def test_size_mismatch_raises():
    with pytest.raises(ValueError):
        encode_png(2, 2, b"\x00\x01\x02", channels=3)
