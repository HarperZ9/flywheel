"""Tests for coherence_membrane.palettes -- retro palette registry."""
from __future__ import annotations

import pytest

from coherence_membrane.palettes import RETRO_PALETTES, get_palette


# ---------------------------------------------------------------------------
# Registry shape
# ---------------------------------------------------------------------------

def test_retro_palettes_is_dict_of_lists():
    assert isinstance(RETRO_PALETTES, dict)
    for name, palette in RETRO_PALETTES.items():
        assert isinstance(palette, list), f"{name} palette is not a list"
        for entry in palette:
            assert isinstance(entry, tuple), f"{name}: entry {entry!r} is not a tuple"
            assert len(entry) == 3, f"{name}: entry {entry!r} not (R,G,B)"
            r, g, b = entry
            assert 0 <= r <= 255, f"{name}: R {r} out of [0,255]"
            assert 0 <= g <= 255, f"{name}: G {g} out of [0,255]"
            assert 0 <= b <= 255, f"{name}: B {b} out of [0,255]"


# ---------------------------------------------------------------------------
# Required palettes and exact counts
# ---------------------------------------------------------------------------

def test_cga_4_colors():
    cga = RETRO_PALETTES["cga"]
    assert len(cga) == 4, f"CGA must have 4 colors, got {len(cga)}"


def test_ega_16_colors():
    ega = RETRO_PALETTES["ega"]
    assert len(ega) == 16, f"EGA must have 16 colors, got {len(ega)}"


def test_gameboy_4_colors():
    gb = RETRO_PALETTES["gameboy"]
    assert len(gb) == 4, f"Game Boy must have 4 colors, got {len(gb)}"


def test_c64_16_colors():
    c64 = RETRO_PALETTES["c64"]
    assert len(c64) == 16, f"C64 must have 16 colors, got {len(c64)}"


# ---------------------------------------------------------------------------
# Exact values -- CGA Mode 4 palette 1 high-intensity
# ---------------------------------------------------------------------------

def test_cga_first_color_is_black():
    """CGA: first entry is always black."""
    assert RETRO_PALETTES["cga"][0] == (0, 0, 0)


def test_cga_has_cyan_magenta_white():
    """CGA mode 4 palette 1 high: black, cyan, magenta, white."""
    cga = RETRO_PALETTES["cga"]
    assert (0, 255, 255) in cga   # cyan
    assert (255, 0, 255) in cga   # magenta
    assert (255, 255, 255) in cga # white


def test_ega_has_black_and_white():
    ega = RETRO_PALETTES["ega"]
    assert (0, 0, 0) in ega
    assert (255, 255, 255) in ega


def test_gameboy_all_greens():
    """All Game Boy colors have G >= R and G >= B (greenish)."""
    for r, g, b in RETRO_PALETTES["gameboy"]:
        assert g >= r and g >= b, f"({r},{g},{b}) is not greenish"


def test_gameboy_darkest_to_lightest():
    """Game Boy palette is ordered dark to light by luminance."""
    gb = RETRO_PALETTES["gameboy"]
    lums = [0.299 * r + 0.587 * g + 0.114 * b for r, g, b in gb]
    assert lums == sorted(lums), "Game Boy palette should be ordered dark-to-light"


def test_c64_black_and_white_present():
    c64 = RETRO_PALETTES["c64"]
    assert (0, 0, 0) in c64
    assert (255, 255, 255) in c64


# ---------------------------------------------------------------------------
# get_palette helper
# ---------------------------------------------------------------------------

def test_get_palette_returns_known_palette():
    cga = get_palette("cga")
    assert cga == RETRO_PALETTES["cga"]


def test_get_palette_case_insensitive():
    assert get_palette("CGA") == get_palette("cga")
    assert get_palette("EGA") == get_palette("ega")


def test_get_palette_unknown_raises():
    with pytest.raises(KeyError):
        get_palette("nonexistent_palette_xyz")
