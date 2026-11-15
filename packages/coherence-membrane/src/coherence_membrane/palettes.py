"""Fixed retro-hardware color palettes.

Each palette is a list of (R, G, B) tuples with values in [0, 255].
All values are the canonical historical colors for the named hardware.

Sources:
  CGA:      IBM Color Graphics Adapter, Mode 4 Palette 1 High-Intensity
            https://en.wikipedia.org/wiki/Color_Graphics_Adapter#Color_palette
  EGA:      IBM Enhanced Graphics Adapter default 16-color palette
            https://en.wikipedia.org/wiki/Enhanced_Graphics_Adapter#Color_palette
  Game Boy: Original DMG Game Boy 4-shade green palette (LCD characteristic)
            https://en.wikipedia.org/wiki/Game_Boy#Technical_specifications
            Values from the authoritative Gambatte emulator DMG palette:
            #0f380f #306230 #8bac0f #9bbc0f (dark to light)
  C64:      Commodore 64 VIC-II standard 16-color palette (VICE emulator values)
            https://www.c64-wiki.com/wiki/Color
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# CGA -- Mode 4 Palette 1 High-Intensity (4 colors)
# Black, Cyan, Magenta, White
# ---------------------------------------------------------------------------
_CGA: list[tuple[int, int, int]] = [
    (0, 0, 0),       # 0: Black
    (0, 255, 255),   # 1: Cyan (high intensity)
    (255, 0, 255),   # 2: Magenta (high intensity)
    (255, 255, 255), # 3: White
]

# ---------------------------------------------------------------------------
# EGA -- Standard 16-color palette
# ---------------------------------------------------------------------------
_EGA: list[tuple[int, int, int]] = [
    (0, 0, 0),       # 0:  Black
    (0, 0, 170),     # 1:  Blue
    (0, 170, 0),     # 2:  Green
    (0, 170, 170),   # 3:  Cyan
    (170, 0, 0),     # 4:  Red
    (170, 0, 170),   # 5:  Magenta
    (170, 85, 0),    # 6:  Brown
    (170, 170, 170), # 7:  Light Gray
    (85, 85, 85),    # 8:  Dark Gray
    (85, 85, 255),   # 9:  Bright Blue
    (85, 255, 85),   # 10: Bright Green
    (85, 255, 255),  # 11: Bright Cyan
    (255, 85, 85),   # 12: Bright Red
    (255, 85, 255),  # 13: Bright Magenta
    (255, 255, 85),  # 14: Yellow
    (255, 255, 255), # 15: White
]

# ---------------------------------------------------------------------------
# Game Boy -- Original DMG 4-shade green palette (dark to light)
# Gambatte emulator canonical values; ordered darkest -> lightest
# #0f380f  #306230  #8bac0f  #9bbc0f
# ---------------------------------------------------------------------------
_GAMEBOY: list[tuple[int, int, int]] = [
    (15, 56, 15),    # 0: Darkest green
    (48, 98, 48),    # 1: Dark green
    (139, 172, 15),  # 2: Light green
    (155, 188, 15),  # 3: Lightest green
]

# ---------------------------------------------------------------------------
# C64 -- VIC-II standard 16-color palette (VICE emulator values)
# ---------------------------------------------------------------------------
_C64: list[tuple[int, int, int]] = [
    (0, 0, 0),       # 0:  Black
    (255, 255, 255), # 1:  White
    (136, 0, 0),     # 2:  Red
    (170, 255, 238), # 3:  Cyan
    (204, 68, 204),  # 4:  Purple
    (0, 204, 85),    # 5:  Green
    (0, 0, 170),     # 6:  Blue
    (238, 238, 119), # 7:  Yellow
    (221, 136, 85),  # 8:  Orange
    (102, 68, 0),    # 9:  Brown
    (255, 119, 119), # 10: Light Red
    (51, 51, 51),    # 11: Dark Gray
    (119, 119, 119), # 12: Gray
    (170, 255, 102), # 13: Light Green
    (0, 136, 255),   # 14: Light Blue
    (187, 187, 187), # 15: Light Gray
]

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

RETRO_PALETTES: dict[str, list[tuple[int, int, int]]] = {
    "cga": _CGA,
    "ega": _EGA,
    "gameboy": _GAMEBOY,
    "c64": _C64,
}


def get_palette(name: str) -> list[tuple[int, int, int]]:
    """Return a palette by name (case-insensitive). Raises KeyError if unknown."""
    key = name.lower()
    if key not in RETRO_PALETTES:
        raise KeyError(f"Unknown retro palette {name!r}. Available: {sorted(RETRO_PALETTES)}")
    return RETRO_PALETTES[key]
