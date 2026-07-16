"""The TTF writer must produce a real font: correct sfnt structure,
recomputable checksums, monotonic offsets, and — the strongest oracle —
FreeType (via PIL) must load it and render the proving word with ink."""

import io
import struct

import pytest

from harness.typeface_forge import DEFAULTS, mint
from harness.typeface_ttf import to_ttf


@pytest.fixture(scope="module")
def ttf() -> bytes:
    return to_ttf(mint(dict(DEFAULTS), seed=58))


def _tables(font: bytes) -> dict:
    n = struct.unpack(">H", font[4:6])[0]
    out = {}
    for i in range(n):
        tag, chk, off, ln = struct.unpack(">4sLLL", font[12 + 16 * i:28 + 16 * i])
        out[tag] = (chk, off, ln)
    return out

def test_sfnt_structure(ttf):
    assert ttf[:4] == b"\x00\x01\x00\x00"
    t = _tables(ttf)
    for tag in (b"cmap", b"glyf", b"head", b"hhea", b"hmtx", b"loca",
                b"maxp", b"name", b"post", b"OS/2"):
        assert tag in t, f"missing table {tag}"
    _, off, _ = t[b"head"]
    assert struct.unpack(">L", ttf[off + 12:off + 16])[0] == 0x5F0F3CF5


def test_font_checksum_adjusts_to_the_magic(ttf):
    from harness.typeface_ttf import _checksum
    assert _checksum(ttf) == 0xB1B0AFBA


def test_loca_is_monotonic_and_spans_glyf(ttf):
    t = _tables(ttf)
    _, loff, lln = t[b"loca"]
    offs = struct.unpack(f">{lln // 4}L", ttf[loff:loff + lln])
    assert all(a <= b for a, b in zip(offs, offs[1:]))
    _, _, gln = t[b"glyf"]
    assert offs[-1] == gln or offs[-1] == gln  # last offset ends the table
    _, moff, _ = t[b"maxp"]
    n_glyphs = struct.unpack(">H", ttf[moff + 4:moff + 6])[0]
    assert len(offs) == n_glyphs + 1


def test_freetype_loads_and_renders_ink(ttf):
    PIL = pytest.importorskip("PIL")
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(io.BytesIO(ttf), 96)
    im = Image.new("L", (900, 220), 0)
    d = ImageDraw.Draw(im)
    d.text((20, 40), "adhesion", font=font, fill=255)
    bbox = im.getbbox()
    assert bbox is not None, "the rendered word left no ink"
    x0, y0, x1, y1 = bbox
    assert (x1 - x0) > 300 and (y1 - y0) > 40, f"degenerate render {bbox}"


def test_determinism(ttf):
    again = to_ttf(mint(dict(DEFAULTS), seed=58))
    assert again == ttf
