"""The poster composer must be an instrument: deterministic bytes under
one receipt, real ink on the plate, and named refusals for a blank title,
an unknown format, or a face the rules already refused."""

import base64
import io

import pytest

pytest.importorskip("PIL")

from harness.design_studio import FORMATS, compose


def test_same_inputs_compose_the_same_bytes():
    a = compose("Order out of disorder", "a zentropy labs plate", seed=58)
    b = compose("Order out of disorder", "a zentropy labs plate", seed=58)
    assert not a["refused"]
    assert a["receipt"]["png_sha256"] == b["receipt"]["png_sha256"]
    assert a["receipt"]["face_mint_id"] == b["receipt"]["face_mint_id"]


def test_the_plate_carries_ink_at_the_declared_size():
    from PIL import Image
    out = compose("Witnessed design", fmt="og", seed=58)
    png = base64.b64decode(out["png_b64"])
    im = Image.open(io.BytesIO(png))
    assert im.size == tuple(FORMATS["og"])
    grey = im.convert("L")
    lo, hi = grey.getextrema()
    assert hi - lo > 80, "the plate is blank"
    # the TITLE BLOCK specifically must carry ink: a poster whose type
    # landed on a discarded buffer is a plate, not a poster
    W, H = im.size
    block = grey.crop((int(W * 0.06), int(H * 0.55),
                       int(W * 0.60), int(H * 0.80)))
    blo, bhi = block.getextrema()
    assert bhi - blo > 60, "the title block is empty; the type never landed"


def test_named_refusals():
    assert "title" in compose("")["refusals"][0]
    assert "format" in compose("x", fmt="zine")["refusals"][0]
    assert "ground" in compose("x", ground="mauve")["refusals"][0]
    heavy = compose("x", face_params={"weight": 0.30, "x_height": 0.44})
    assert heavy["refused"] and "face refused" in heavy["refusals"][0]
    glyphless = compose("semicolons; why")
    assert glyphless["refused"] and "no glyph" in glyphless["refusals"][0]


def test_orb_presets_place_the_mark_and_refuse_the_unknown():
    for preset in ("center", "high", "right", "quiet"):
        r = compose("Zentropy", seed=58, orb=preset)
        assert not r["refused"], preset
        assert r["receipt"]["orb"] == preset
    bad = compose("Zentropy", seed=58, orb="nope")
    assert bad["refused"] and "orb preset" in bad["refusals"][0]


def test_density_scales_and_clamps():
    lo = compose("Zentropy", seed=58, density=0.1)   # clamps up to 0.4
    hi = compose("Zentropy", seed=58, density=9.0)   # clamps down to 2.0
    assert lo["receipt"]["density"] == 0.4
    assert hi["receipt"]["density"] == 2.0


def test_pdf_export_is_a_real_print_ready_pdf():
    r = compose("Order out of disorder", "a plate", seed=58, want_pdf=True)
    assert "pdf_b64" in r
    pdf = base64.b64decode(r["pdf_b64"])
    assert pdf[:5] == b"%PDF-"                       # a real PDF, not a rename
    assert r["receipt"]["pdf_sha256"]
    # deterministic: the same inputs make the same PDF
    r2 = compose("Order out of disorder", "a plate", seed=58, want_pdf=True)
    assert r["receipt"]["pdf_sha256"] == r2["receipt"]["pdf_sha256"]


def test_svg_export_is_a_scalable_container_with_the_viewbox():
    r = compose("Zentropy Labs", "the witnessed substrate", seed=58,
                want_svg=True)
    assert "svg_b64" in r
    svg = base64.b64decode(r["svg_b64"]).decode("utf-8")
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert 'viewBox="0 0' in svg and "data:image/png;base64," in svg
    # honest about what it is: a container, not vector line-work
    assert "not vector" in r["receipt"]["svg_note"]


def test_export_formats_are_off_by_default():
    r = compose("Zentropy", seed=58)
    assert "pdf_b64" not in r and "svg_b64" not in r
