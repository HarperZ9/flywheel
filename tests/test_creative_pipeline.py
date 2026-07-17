"""The creative line must be an instrument: sources start it, transforms
bend it, the chain witnesses the order, and the same stages re-derive the
same still. Wireframes carry their geometry hash; film frames letterbox
for real; refusals come by name at every fence."""

import base64
import io
import shutil

import pytest

pytest.importorskip("PIL")

from harness.creative_pipeline import run_pipeline
from harness.retro_cgi import render_wireframe
from harness.telos_kernels import _module_path

_node = shutil.which("node") is not None and _module_path() is not None


def test_wireframe_renders_with_geometry_receipt():
    img, r = render_wireframe("cube", seed=58, width=320, height=200)
    assert img is not None and img.size == (320, 200)
    assert r["n_vertices"] == 8 and r["n_edges"] == 12
    assert r["geometry_sha256"]
    _, r2 = render_wireframe("cube", seed=58, width=320, height=200)
    assert r2["geometry_sha256"] == r["geometry_sha256"]
    _, r3 = render_wireframe("cube", seed=59, width=320, height=200)
    assert r3["geometry_sha256"] != r["geometry_sha256"]


def test_the_line_chains_and_re_derives():
    stages = [{"op": "wireframe",
               "args": {"primitive": "pyramid", "seed": 58,
                        "width": 320, "height": 200}},
              {"op": "film_frame",
               "args": {"seed": 58, "grain": 0.4, "title": "order"}}]
    a = run_pipeline(stages)
    assert not a["refused"], a["refusals"]
    b = run_pipeline(stages)
    assert a["receipt"]["pipeline_id"] == b["receipt"]["pipeline_id"]
    assert a["receipt"]["png_sha256"] == b["receipt"]["png_sha256"]
    assert a["receipt"]["n_stages"] == 2
    # reordering the SAME work moves the chain
    assert a["receipt"]["stages"][0]["chain"] != a["receipt"]["pipeline_id"]


def test_film_frame_letterboxes_for_real():
    from PIL import Image
    out = run_pipeline([
        {"op": "plate", "args": {"seed": 58, "width": 480, "height": 320}},
        {"op": "film_frame", "args": {"letterbox": True, "grain": 0.0,
                                      "vignette": 0.0}}])
    im = Image.open(io.BytesIO(base64.b64decode(out["png_b64"])))
    top = im.crop((0, 0, im.width, 4)).getcolors(maxcolors=16)
    assert top is not None and len(top) == 1, "the top bar is not uniform"


@pytest.mark.skipif(not _node, reason="node or telos checkout absent")
def test_a_lane_stage_joins_the_line():
    out = run_pipeline([
        {"op": "wireframe", "args": {"primitive": "orbit-sphere",
                                     "seed": 58, "width": 320,
                                     "height": 200}},
        {"op": "dither", "args": {"levels": 2}}])
    assert not out["refused"], out["refusals"]
    dither_stage = out["receipt"]["stages"][1]
    assert dither_stage["lane"] == "telos"
    assert dither_stage["kernel_receipt_hash"].startswith("fnv1a:")


def test_named_refusals_at_the_fences():
    assert "at least one" in run_pipeline([])["refusals"][0]
    assert "source" in run_pipeline(
        [{"op": "film_frame"}])["refusals"][0]
    assert "unknown op" in run_pipeline(
        [{"op": "plate"}, {"op": "teleport"}])["refusals"][0]
    assert "can only start" in run_pipeline(
        [{"op": "plate"}, {"op": "wireframe"}])["refusals"][0]
    long = [{"op": "plate"}] + [{"op": "film_frame"}] * 9
    assert "workflow" in run_pipeline(long)["refusals"][0]
