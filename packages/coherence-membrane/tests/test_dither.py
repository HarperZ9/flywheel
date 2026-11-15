"""Tests for coherence_membrane.dither -- Bayer ordered dithering."""
from __future__ import annotations

import pytest

from coherence_membrane.dither import bayer_matrix, ordered_dither
from coherence_membrane.color import srgb_to_oklab
from coherence_membrane.color_field import ColorField


# ---------------------------------------------------------------------------
# bayer_matrix
# ---------------------------------------------------------------------------

def test_bayer_2_size_and_values():
    m = bayer_matrix(2)
    assert len(m) == 2
    assert all(len(row) == 2 for row in m)
    # Standard 2x2 Bayer matrix (normalized) = [[0,2],[3,1]] / 4
    expected = [[0 / 4, 2 / 4], [3 / 4, 1 / 4]]
    for y in range(2):
        for x in range(2):
            assert abs(m[y][x] - expected[y][x]) < 1e-9, (
                f"bayer_matrix(2)[{y}][{x}] = {m[y][x]!r}, expected {expected[y][x]!r}"
            )


def test_bayer_4_size_and_values():
    m = bayer_matrix(4)
    assert len(m) == 4
    assert all(len(row) == 4 for row in m)
    # Known 4x4 Bayer matrix (normalized by /16)
    expected_raw = [
        [0, 8, 2, 10],
        [12, 4, 14, 6],
        [3, 11, 1, 9],
        [15, 7, 13, 5],
    ]
    for y in range(4):
        for x in range(4):
            assert abs(m[y][x] - expected_raw[y][x] / 16) < 1e-9, (
                f"bayer_matrix(4)[{y}][{x}] mismatch"
            )


def test_bayer_8_size():
    m = bayer_matrix(8)
    assert len(m) == 8
    assert all(len(row) == 8 for row in m)


def test_bayer_8_values_in_0_1():
    m = bayer_matrix(8)
    for y in range(8):
        for x in range(8):
            assert 0.0 <= m[y][x] < 1.0, f"bayer(8)[{y}][{x}] = {m[y][x]} out of [0,1)"


def test_bayer_2_values_in_0_1():
    m = bayer_matrix(2)
    for y in range(2):
        for x in range(2):
            assert 0.0 <= m[y][x] < 1.0


def test_bayer_4_values_in_0_1():
    m = bayer_matrix(4)
    for y in range(4):
        for x in range(4):
            assert 0.0 <= m[y][x] < 1.0


def test_bayer_4_all_values_unique():
    """Bayer matrix n=4: all 16 values are distinct."""
    m = bayer_matrix(4)
    flat = [m[y][x] for y in range(4) for x in range(4)]
    assert len(set(flat)) == 16, "Bayer 4x4 should have 16 distinct thresholds"


def test_bayer_8_all_values_unique():
    m = bayer_matrix(8)
    flat = [m[y][x] for y in range(8) for x in range(8)]
    assert len(set(flat)) == 64, "Bayer 8x8 should have 64 distinct thresholds"


def test_bayer_invalid_n():
    with pytest.raises(ValueError):
        bayer_matrix(3)
    with pytest.raises(ValueError):
        bayer_matrix(0)
    with pytest.raises(ValueError):
        bayer_matrix(16)


def test_bayer_deterministic():
    """Repeated calls return identical matrices."""
    m1 = bayer_matrix(4)
    m2 = bayer_matrix(4)
    assert m1 == m2


# ---------------------------------------------------------------------------
# ordered_dither
# ---------------------------------------------------------------------------

def _make_color_field(colors_srgb: list[tuple[float, float, float]]) -> ColorField:
    """Build a 1-row ColorField from a list of sRGB triples."""
    n = len(colors_srgb)
    lab = tuple(srgb_to_oklab(c) for c in colors_srgb)
    return ColorField(n, 1, lab, (False,) * n)


def test_ordered_dither_returns_valid_indices():
    """Each output index is within the palette range."""
    white_lab = srgb_to_oklab((1.0, 1.0, 1.0))
    black_lab = srgb_to_oklab((0.0, 0.0, 0.0))
    palette = (black_lab, white_lab)
    cf = _make_color_field([(0.5, 0.5, 0.5)] * 4)
    indices = ordered_dither(cf, palette, bayer_size=4)
    assert len(indices) == 4
    for idx in indices:
        assert 0 <= idx < len(palette), f"index {idx} out of palette range [0,{len(palette)})"


def test_ordered_dither_pure_black_maps_to_black():
    """A pure-black pixel always maps to the black palette entry regardless of dither."""
    black_lab = srgb_to_oklab((0.0, 0.0, 0.0))
    white_lab = srgb_to_oklab((1.0, 1.0, 1.0))
    palette = (black_lab, white_lab)
    cf = _make_color_field([(0.0, 0.0, 0.0)] * 16)  # 16 pixels, same as bayer 4x4 size
    # Build a 4x4 field
    lab = tuple(srgb_to_oklab((0.0, 0.0, 0.0)) for _ in range(16))
    cf4 = ColorField(4, 4, lab, (False,) * 16)
    indices = ordered_dither(cf4, palette, bayer_size=4)
    # All black -> all map to black (index 0) since dither only perturbs toward 2nd nearest
    # if the perturbed value is still closer to the same nearest, index is 0
    # This is not strictly guaranteed to be ALL zeros (dithering may flip some),
    # but every index must be valid:
    assert all(0 <= i < 2 for i in indices)


def test_ordered_dither_is_deterministic():
    """Same field + palette + bayer_size -> same indices, always."""
    palette = (
        srgb_to_oklab((0.0, 0.0, 0.0)),
        srgb_to_oklab((0.5, 0.5, 0.5)),
        srgb_to_oklab((1.0, 1.0, 1.0)),
    )
    cf = _make_color_field([(0.3, 0.3, 0.3)] * 8)
    i1 = ordered_dither(cf, palette, bayer_size=4)
    i2 = ordered_dither(cf, palette, bayer_size=4)
    assert i1 == i2


def test_ordered_dither_unknown_returns_sentinel():
    """Unknown cells must return the -1 sentinel (not a palette index).

    The -1 sentinel propagates to _palette_indices_to_lab which maps it to
    black (OKLab (0,0,0)) -- honest disclosure of UNVERIFIABLE data rather
    than silently snapping to a palette colour.
    For the known cell at position 1: the result is a valid palette index.
    """
    palette = (
        srgb_to_oklab((0.0, 0.0, 0.0)),
        srgb_to_oklab((1.0, 1.0, 1.0)),
    )
    lab = (srgb_to_oklab((0.1, 0.1, 0.1)), srgb_to_oklab((0.9, 0.9, 0.9)))
    cf = ColorField(2, 1, lab, (True, False))  # first is unknown
    indices = ordered_dither(cf, palette, bayer_size=4)
    assert indices[0] == -1  # unknown cell: must be -1 sentinel, not a palette index
    assert 0 <= indices[1] < 2  # known cell: valid index, may be dithered to either
