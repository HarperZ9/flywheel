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
