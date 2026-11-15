from __future__ import annotations

import pytest

from coherence_membrane.color import srgb_to_oklab
from coherence_membrane.color_field import ColorField, color_field_from_png
from coherence_membrane.pngencode import encode_png
from coherence_membrane.pngview import PngDecodeError


def test_colorfield_validates_and_accesses():
    cf = ColorField(2, 1, ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)), (False, True))
    assert cf.at(0, 0) == (0.0, 0.0, 0.0)
    assert cf.is_unknown(1, 0) is True
    with pytest.raises(ValueError):
        ColorField(2, 1, ((0.0, 0.0, 0.0),), (False, False))   # lab len != w*h
    with pytest.raises(ValueError):
        ColorField(2, 1, ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)), (False,))   # unknown len != w*h


def test_color_field_from_png_red():
    # 1x1 pure red PNG -> OKLab of red
    png = encode_png(1, 1, bytes([255, 0, 0]), channels=3)
    cf = color_field_from_png(png)
    assert (cf.width, cf.height) == (1, 1)
    exp = srgb_to_oklab((1.0, 0.0, 0.0))
    assert all(abs(cf.at(0, 0)[i] - exp[i]) < 1e-9 for i in range(3))
    assert cf.is_unknown(0, 0) is False


def test_color_field_from_png_multipixel():
    # 2x1 red,green -> per-pixel OKLab at the right row-major offsets
    png = encode_png(2, 1, bytes([255, 0, 0, 0, 255, 0]), channels=3)
    cf = color_field_from_png(png)
    assert (cf.width, cf.height) == (2, 1)
    assert all(abs(cf.at(0, 0)[i] - srgb_to_oklab((1.0, 0.0, 0.0))[i]) < 1e-9 for i in range(3))
    assert all(abs(cf.at(1, 0)[i] - srgb_to_oklab((0.0, 1.0, 0.0))[i]) < 1e-9 for i in range(3))


def test_color_field_from_png_rejects_garbage():
    with pytest.raises(PngDecodeError):
        color_field_from_png(b"not a png")
