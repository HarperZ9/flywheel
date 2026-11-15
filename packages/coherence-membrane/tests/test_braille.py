from __future__ import annotations

from coherence_membrane.field import Field, FieldKind
from coherence_membrane.braille import pack_braille, braille_text, braille_view


def _occ(w, h, vals, unknown=None):
    if unknown is None:
        unknown = (False,) * (w * h)
    return Field(w, h, FieldKind.OCCUPANCY, tuple(float(v) for v in vals), tuple(unknown))


def test_pack_full_cell_is_solid_glyph():
    assert pack_braille(_occ(2, 4, [1] * 8)) == ["⣿"]


def test_pack_empty_cell_is_blank_glyph():
    assert pack_braille(_occ(2, 4, [0] * 8)) == ["⠀"]


def test_pack_single_top_left_dot():
    vals = [0] * 8
    vals[0] = 1  # cell (x=0, y=0) -> dot 1 -> 0x01
    assert pack_braille(_occ(2, 4, vals)) == ["⠁"]


def test_pack_unknown_cell_is_not_ink():
    vals = [1] * 8
    unk = [False] * 8
    unk[0] = True  # (0,0) unknown -> no dot even though value is 1
    assert pack_braille(_occ(2, 4, vals, unknown=unk)) == [chr(0x2800 + 0xFE)]


def test_braille_text_joins_rows():
    assert braille_text(["ab", "cd"]) == "ab\ncd"


def test_braille_view_downscales_to_one_solid_glyph():
    f = _occ(4, 8, [1] * 32)  # 4x8 solid -> 1 glyph (2x4 dots), all set
    assert braille_view(f, cols=1, rows=1) == ["⣿"]


def test_braille_view_default_rows_preserve_aspect():
    f = _occ(8, 8, [1] * 64)
    view = braille_view(f, cols=2)   # dot_w=4 -> dot_h~4 -> 1 glyph row
    assert len(view) == 1 and len(view[0]) == 2


def test_sparse_braille_finds_edge_and_stays_sparse():
    from coherence_membrane.braille import sparse_braille

    # 8x8: left half dark, right half bright => one vertical edge
    vals = [0.0 if x < 4 else 1.0 for y in range(8) for x in range(8)]
    f = Field(8, 8, FieldKind.LUMINANCE, tuple(vals), (False,) * 64)
    glyphs = "".join(sparse_braille(f, cols=4, rows=2))
    assert any(ch != "⠀" for ch in glyphs)   # an edge was found (ink)
    assert any(ch == "⠀" for ch in glyphs)   # background stays blank (sparse)


def test_pack_braille_multi_glyph_layout():
    # 4 wide x 8 tall -> 2 glyph cols x 2 glyph rows
    # left half all ink, right half blank -> 2 glyphs per row, 2 rows
    vals = [1.0 if x < 2 else 0.0 for y in range(8) for x in range(4)]
    f = _occ(4, 8, vals)
    rows = pack_braille(f)
    assert len(rows) == 2          # 2 glyph rows (8 dots / 4 per glyph)
    assert len(rows[0]) == 2       # 2 glyph cols (4 dots / 2 per glyph)
    assert rows[0][0] != "⠀"      # left glyph has ink
    assert rows[0][1] == "⠀"      # right glyph is blank
    assert rows[1][0] != "⠀"      # second row left has ink
    assert rows[1][1] == "⠀"      # second row right is blank


def test_target_dot_grid_raises_on_zero_cols():
    import pytest
    from coherence_membrane.braille import target_dot_grid
    f = _occ(4, 4, [0.0] * 16)
    with pytest.raises(ValueError):
        target_dot_grid(f, cols=0, rows=None)
