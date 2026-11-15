"""Tests for the minimal stdlib PNG decoder."""

from __future__ import annotations

import struct

import pytest

from coherence_membrane.pngview import (
    PngDecodeError,
    decode_png,
    is_png,
    read_ihdr,
)


def test_roundtrip_rgb_filter0(make_png):
    pixels = bytes([255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 255])  # 2x2
    png = make_png(2, 2, pixels, color_type=2, filter_type=0)
    img = decode_png(png)
    assert (img.width, img.height, img.channels) == (2, 2, 3)
    assert img.pixels == pixels


@pytest.mark.parametrize("ftype", [0, 1, 2, 3, 4])
def test_all_filter_types_roundtrip(make_png, ftype):
    # 4x3 RGB with varied values so each filter actually transforms the row.
    w, h = 4, 3
    pixels = bytes((i * 7 + 3) % 256 for i in range(w * h * 3))
    png = make_png(w, h, pixels, color_type=2, filter_type=ftype)
    img = decode_png(png)
    assert img.pixels == pixels, f"filter {ftype} did not round-trip"


def test_grayscale_roundtrip(make_png):
    pixels = bytes([0, 64, 128, 255])  # 2x2 grayscale
    png = make_png(2, 2, pixels, color_type=0, filter_type=2)
    img = decode_png(png)
    assert img.channels == 1
    assert img.pixels == pixels


def test_rgba_roundtrip(make_png):
    pixels = bytes(range(16))  # 2x2 RGBA (4ch * 4px = 16)
    png = make_png(2, 2, pixels, color_type=6, filter_type=4)
    img = decode_png(png)
    assert img.channels == 4
    assert img.pixels == pixels


def test_read_ihdr(make_png):
    png = make_png(7, 5, bytes(7 * 5 * 3), color_type=2)
    w, h, depth, ctype = read_ihdr(png)
    assert (w, h, depth, ctype) == (7, 5, 8, 2)


def test_is_png_detects_signature(make_png):
    png = make_png(1, 1, bytes(3))
    assert is_png(png)
    assert not is_png(b"not a png")


def test_bad_signature_raises():
    with pytest.raises(PngDecodeError):
        decode_png(b"\x00\x01\x02\x03nope")


def test_sixteen_bit_unsupported(make_png):
    png = bytearray(make_png(2, 2, bytes(12), color_type=2))
    png[24] = 16  # IHDR bit_depth byte -> 16
    with pytest.raises(PngDecodeError):
        decode_png(bytes(png))


def test_interlaced_unsupported(make_png):
    png = bytearray(make_png(2, 2, bytes(12), color_type=2))
    png[28] = 1  # IHDR interlace byte -> Adam7
    with pytest.raises(PngDecodeError):
        decode_png(bytes(png))


def test_truncated_raises(make_png):
    png = make_png(4, 4, bytes(4 * 4 * 3))
    with pytest.raises(PngDecodeError):
        decode_png(png[:20])  # cut mid-stream


def test_decoder_never_returns_partial_on_bad_idat(make_png):
    png = bytearray(make_png(2, 2, bytes(12)))
    # corrupt a byte inside the IDAT zlib stream
    idat_marker = png.find(b"IDAT")
    png[idat_marker + 8] ^= 0xFF
    with pytest.raises(PngDecodeError):
        decode_png(bytes(png))
