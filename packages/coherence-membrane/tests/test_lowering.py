from __future__ import annotations

import pytest

from coherence_membrane.field import FieldKind
from coherence_membrane.lowering import field_from_png
from coherence_membrane.pngencode import encode_png
from coherence_membrane.pngview import PngDecodeError


def _uniform_png(value, w=4, h=4):
    return encode_png(w, h, bytes([value, value, value] * (w * h)), channels=3)


def test_field_from_png_white_is_one():
    f = field_from_png(_uniform_png(255))
    assert f.kind is FieldKind.LUMINANCE
    assert f.width == 4 and f.height == 4
    assert all(abs(v - 1.0) < 1e-9 for v in f.values)
    assert not any(f.unknown)


def test_field_from_png_black_is_zero():
    f = field_from_png(_uniform_png(0))
    assert all(v == 0.0 for v in f.values)


def test_field_from_png_rejects_garbage():
    with pytest.raises(PngDecodeError):
        field_from_png(b"not a png")


def test_field_from_png_grayscale_1ch():
    # channels=1 (grayscale): uniform mid-gray 128 -> luma ~ 128/255
    png = encode_png(2, 2, bytes([128] * 4), channels=1)
    f = field_from_png(png)
    assert f.kind is FieldKind.LUMINANCE
    assert f.width == 2 and f.height == 2
    expected = 128 / 255.0
    assert all(abs(v - expected) < 1e-9 for v in f.values)


def test_field_from_png_gray_alpha_2ch():
    # channels=2 (grayscale + alpha): luma comes from first channel only
    # pixel = [200, 128] repeated -- alpha ignored, luma = 200/255
    png = encode_png(2, 2, bytes([200, 128] * 4), channels=2)
    f = field_from_png(png)
    assert f.kind is FieldKind.LUMINANCE
    expected = 200 / 255.0
    assert all(abs(v - expected) < 1e-9 for v in f.values)
