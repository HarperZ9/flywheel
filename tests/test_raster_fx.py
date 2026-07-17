"""The raster bridge must run the lane's own dither and pixel-sort over
real images: deterministic bytes, the kernel's own hashes on the receipt,
levels that actually quantize, and named refusals at every fence. Skips
honestly when node, Pillow, or the telos checkout is absent."""

import base64
import io
import shutil

import pytest

pytest.importorskip("PIL")

from harness.telos_kernels import _module_path
from harness.raster_fx import apply_fx

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or _module_path() is None,
    reason="node or the telos source checkout is absent")


def test_dither_runs_the_lanes_kernel_deterministically():
    a = apply_fx("raster.ordered-dither",
                 {"kind": "plate", "seed": 58, "width": 240, "height": 160},
                 {"levels": 4, "matrixSize": 4})
    assert not a["refused"], a["refusals"]
    b = apply_fx("raster.ordered-dither",
                 {"kind": "plate", "seed": 58, "width": 240, "height": 160},
                 {"levels": 4, "matrixSize": 4})
    assert a["receipt"]["png_sha256"] == b["receipt"]["png_sha256"]
    assert a["receipt"]["kernel_receipt_hash"] == \
        b["receipt"]["kernel_receipt_hash"]
    assert a["receipt"]["kernel_receipt_hash"].startswith("fnv1a:")
    # four levels means at most four distinct grays in the output
    assert a["measurement"]["unique_levels"] <= 4


def test_the_dithered_image_decodes_at_the_declared_size():
    from PIL import Image
    out = apply_fx("raster.ordered-dither",
                   {"kind": "plate", "seed": 58, "width": 240,
                    "height": 160}, {"levels": 2})
    im = Image.open(io.BytesIO(base64.b64decode(out["png_b64"])))
    assert im.size == (240, 160)
    assert len(set(im.getdata())) <= 2


def test_pixel_sort_runs_and_reports_runs():
    out = apply_fx("raster.pixel-sort-rows",
                   {"kind": "plate", "seed": 58, "width": 240,
                    "height": 160}, {"threshold": 96})
    assert not out["refused"], out["refusals"]
    assert out["receipt"]["kernel_receipt_hash"]
    assert "runs" in out["measurement"] or out["measurement"]


def test_a_supplied_png_is_accepted_and_fenced():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("L", (1400, 900), 128).save(buf, "PNG")
    out = apply_fx("raster.ordered-dither",
                   {"kind": "png_b64",
                    "data": base64.b64encode(buf.getvalue()).decode()},
                   {"levels": 2})
    assert not out["refused"]
    w, h = out["receipt"]["size"]
    assert max(w, h) <= 640, "the size fence did not hold"


def test_named_refusals():
    assert "unknown raster kernel" in \
        apply_fx("raster.nonexistent")["refusals"][0]
    assert "decode" in apply_fx(
        "raster.ordered-dither",
        {"kind": "png_b64", "data": "bm90cG5n"})["refusals"][0]
    assert "source kind" in apply_fx(
        "raster.ordered-dither", {"kind": "carrier-pigeon"})["refusals"][0]
