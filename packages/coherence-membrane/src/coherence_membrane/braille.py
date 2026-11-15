"""Braille encoder -- 2x4 dot packing (U+2800..U+28FF). 8x the spatial density of
an ASCII cell; ideal for sparse 'ink = signal' (negative-space) projections."""
from __future__ import annotations

from .field import Field
from .field_ops import boundary, downscale, threshold

_BRAILLE_BASE = 0x2800
# Bit per (row, col) inside a 2-wide x 4-tall cell. Standard braille numbering:
#   dot1 dot4
#   dot2 dot5
#   dot3 dot6
#   dot7 dot8
_DOT_BITS = (
    (0x01, 0x08),   # row 0: col0, col1
    (0x02, 0x10),   # row 1
    (0x04, 0x20),   # row 2
    (0x40, 0x80),   # row 3
)


def pack_braille(field: Field, ink_threshold: float = 0.5) -> list[str]:
    """Pack a field directly into braille glyphs (2 cols x 4 rows of dots each).
    A cell is 'ink' iff it is NOT UNVERIFIABLE and value >= ink_threshold. The
    field is padded: out-of-range cells contribute no dot."""
    glyph_cols = (field.width + 1) // 2
    glyph_rows = (field.height + 3) // 4
    lines: list[str] = []
    for gr in range(glyph_rows):
        chars: list[str] = []
        for gc in range(glyph_cols):
            bits = 0
            for dy in range(4):
                for dx in range(2):
                    x, y = gc * 2 + dx, gr * 4 + dy
                    if x >= field.width or y >= field.height:
                        continue
                    if field.is_unknown(x, y):
                        continue
                    if field.at(x, y) >= ink_threshold:
                        bits |= _DOT_BITS[dy][dx]
            chars.append(chr(_BRAILLE_BASE + bits))
        lines.append("".join(chars))
    return lines


def braille_text(view: list[str]) -> str:
    """The view as a single newline-joined string (the witnessed artifact form)."""
    return "\n".join(view)


def target_dot_grid(field: Field, cols: int, rows: int | None) -> tuple[int, int]:
    """Resolve the (dot_width, dot_height) to downscale to. `cols` is glyph
    columns (2 dots each); `rows` is glyph rows (4 dots each). Never upscales;
    a None `rows` preserves aspect at the dot level."""
    if cols <= 0:
        raise ValueError("cols must be positive")
    dot_w = min(2 * cols, field.width)
    if rows is None:
        dot_h0 = max(1, round(dot_w * field.height / field.width))
        rows = max(1, (dot_h0 + 3) // 4)
    if rows <= 0:
        raise ValueError("rows must be positive")
    dot_h = min(4 * rows, field.height)
    return dot_w, dot_h


def braille_view(
    field: Field,
    cols: int = 64,
    rows: int | None = None,
    ink_threshold: float = 0.5,
) -> list[str]:
    """Downscale a field to a braille dot grid, then pack to glyphs."""
    dot_w, dot_h = target_dot_grid(field, cols, rows)
    return pack_braille(downscale(field, dot_w, dot_h), ink_threshold)


def sparse_braille(
    field: Field,
    *,
    threshold_t: float = 0.5,
    edge_threshold: float = 0.1,
    cols: int = 64,
    rows: int | None = None,
) -> list[str]:
    """The canonical 'negatives' recipe: downscale -> threshold -> boundary ->
    braille. Ink = the (sparse) boundary, background = blank => maximum
    information per token. Computing the boundary at dot resolution keeps edges
    crisp and cheap."""
    dot_w, dot_h = target_dot_grid(field, cols, rows)
    small = downscale(field, dot_w, dot_h)
    edges = boundary(threshold(small, threshold_t), edge_threshold)
    return pack_braille(edges, ink_threshold=0.5)
