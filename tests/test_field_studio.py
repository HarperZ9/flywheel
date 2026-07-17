"""The field study must be physics, not a filter: the solve converges and
says so on the receipt, the same seed re-derives the same field and image,
and the source slots into the graph beside the other sources."""

import base64
import io

import pytest

pytest.importorskip("PIL")

from harness.creative_graph import run_graph
from harness.field_studio import field_study


def test_the_solve_converges_and_the_receipt_says_so():
    img, r = field_study(seed=58, width=320, height=200, iters=600)
    assert img is not None and img.size == (320, 200)
    assert r["equation"] == "laplace"
    assert r["converged"] is True, f"residual {r['residual']}"
    assert r["residual"] < 1e-4
    assert r["boundary_sha256"]


def test_same_seed_same_field_different_seed_different():
    _, a = field_study(seed=58, width=160, height=100)
    _, b = field_study(seed=58, width=160, height=100)
    assert a["boundary_sha256"] == b["boundary_sha256"]
    assert a["residual"] == b["residual"]
    _, c = field_study(seed=59, width=160, height=100)
    assert c["boundary_sha256"] != a["boundary_sha256"]


def test_the_image_carries_ink_and_the_frame():
    from PIL import Image
    img, _ = field_study(seed=58, width=320, height=200)
    grey = img.convert("L")
    lo, hi = grey.getextrema()
    assert hi - lo > 80, "the field left no light"
    # the measurement frame is the one hot mark
    rgb = img.convert("RGB")
    hot = sum(1 for p in rgb.getdata()
              if p[0] > 200 and p[1] < 180)
    assert hot > 10, "the measurement frame is missing"


def test_field_joins_the_graph_as_a_source():
    out = run_graph(
        [{"id": "f", "op": "field",
          "args": {"seed": 58, "width": 240, "height": 160, "iters": 300}},
         {"id": "film", "op": "film_frame",
          "args": {"grain": 0.3, "letterbox": True}}],
        [{"from": "f", "to": "film"}])
    assert not out["refused"], out["refusals"]
    trail = {n["id"]: n for n in out["receipt"]["nodes"]}
    assert trail["f"]["equation"] == "laplace"
    assert trail["f"]["converged"] in (True, False)
    assert base64.b64decode(out["outputs"]["film"])[:8].startswith(b"\x89PNG")
