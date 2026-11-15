"""Tests for ColorField box-downscale (color_field.downscale_color_field)."""
from __future__ import annotations

import pytest

from coherence_membrane.color import srgb_to_oklab
from coherence_membrane.color_field import ColorField, downscale_color_field
from coherence_membrane.pngencode import encode_png


def _cf_from_pixels(pixels_srgb: list[tuple[float, float, float]], w: int, h: int) -> ColorField:
    assert len(pixels_srgb) == w * h
    lab = tuple(srgb_to_oklab(p) for p in pixels_srgb)
    return ColorField(w, h, lab, (False,) * (w * h))


# ---------------------------------------------------------------------------
# Basic correctness
# ---------------------------------------------------------------------------

def test_downscale_1x1_result_on_2x2():
    """Average of 4 known pixels -> single pixel average in OKLab."""
    black = srgb_to_oklab((0.0, 0.0, 0.0))
    white = srgb_to_oklab((1.0, 1.0, 1.0))
    # 2x2: TL=black, TR=white, BL=white, BR=black
    cf = ColorField(2, 2, (black, white, white, black), (False,) * 4)
    out = downscale_color_field(cf, 1, 1)
    assert out.width == 1 and out.height == 1
    # Average of black+white+white+black in OKLab (axis by axis)
    expected_L = (black[0] + white[0] + white[0] + black[0]) / 4
    expected_a = (black[1] + white[1] + white[1] + black[1]) / 4
    expected_b = (black[2] + white[2] + white[2] + black[2]) / 4
    result = out.at(0, 0)
    assert abs(result[0] - expected_L) < 1e-9
    assert abs(result[1] - expected_a) < 1e-9
    assert abs(result[2] - expected_b) < 1e-9


def test_downscale_preserves_aspect_ratio_from_target_width():
    """downscale_color_field(cf, target_width) auto-computes height."""
    cf = _cf_from_pixels([(0.5, 0.5, 0.5)] * 100, 10, 10)
    out = downscale_color_field(cf, 5)   # half width -> half height
    assert out.width == 5 and out.height == 5


def test_downscale_correct_dims_explicit():
    """Explicit (w, h) form works."""
    cf = _cf_from_pixels([(1.0, 0.0, 0.0)] * 16, 4, 4)
    out = downscale_color_field(cf, 2, 2)
    assert out.width == 2 and out.height == 2


def test_downscale_deterministic():
    """Same input -> same output every call."""
    pixels = [(float(i) / 16, 0.0, 0.0) for i in range(16)]
    cf = _cf_from_pixels(pixels, 4, 4)
    out1 = downscale_color_field(cf, 2, 2)
    out2 = downscale_color_field(cf, 2, 2)
    assert out1.lab == out2.lab
    assert out1.unknown == out2.unknown


def test_downscale_unknown_propagates():
    """If any source pixel in a box is unknown, target is unknown."""
    black = srgb_to_oklab((0.0, 0.0, 0.0))
    white = srgb_to_oklab((1.0, 1.0, 1.0))
    cf = ColorField(2, 2, (black, white, white, black), (True, False, False, False))
    out = downscale_color_field(cf, 1, 1)
    assert out.is_unknown(0, 0) is True


def test_downscale_known_box_not_unknown():
    """All-known box -> target is known."""
    black = srgb_to_oklab((0.0, 0.0, 0.0))
    cf = ColorField(2, 2, (black, black, black, black), (False,) * 4)
    out = downscale_color_field(cf, 1, 1)
    assert out.is_unknown(0, 0) is False


def test_downscale_4x4_to_2x2_averages_correctly():
    """4x4 (all red) -> 2x2 should be all red."""
    red = srgb_to_oklab((1.0, 0.0, 0.0))
    cf = ColorField(4, 4, (red,) * 16, (False,) * 16)
    out = downscale_color_field(cf, 2, 2)
    for y in range(2):
        for x in range(2):
            for ch in range(3):
                assert abs(out.at(x, y)[ch] - red[ch]) < 1e-9


def test_downscale_raises_on_upscale():
    cf = _cf_from_pixels([(0.5, 0.5, 0.5)] * 4, 2, 2)
    with pytest.raises(ValueError):
        downscale_color_field(cf, 4, 4)


def test_downscale_raises_on_nonpositive():
    cf = _cf_from_pixels([(0.5, 0.5, 0.5)] * 4, 2, 2)
    with pytest.raises(ValueError):
        downscale_color_field(cf, 0, 1)
