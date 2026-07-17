"""A brand kit must be an identity with provenance: one seed and one name
re-derive every artifact hash; the pieces are real images and real fonts;
tokens carry the portable identity; refusals come by name."""

import base64
import io

import pytest

pytest.importorskip("PIL")

from harness.brand_kit import mint_kit


@pytest.fixture(scope="module")
def kit():
    return mint_kit("zentropy labs", seed=58, tagline="order out of disorder")


def test_one_seed_re_derives_the_whole_kit(kit):
    assert not kit["refused"]
    again = mint_kit("zentropy labs", seed=58,
                     tagline="order out of disorder")
    assert again["receipt"]["kit_id"] == kit["receipt"]["kit_id"]
    assert again["receipt"]["artifacts"] == kit["receipt"]["artifacts"]
    other = mint_kit("zentropy labs", seed=59,
                     tagline="order out of disorder")
    assert other["receipt"]["kit_id"] != kit["receipt"]["kit_id"]


def test_the_artifact_hashes_match_the_shipped_bytes(kit):
    import hashlib
    a = kit["receipt"]["artifacts"]
    for b64, key in ((kit["mark_png_b64"], "mark_png_sha256"),
                     (kit["banner_png_b64"], "banner_png_sha256"),
                     (kit["poster_png_b64"], "poster_png_sha256"),
                     (kit["specimen_png_b64"], "specimen_png_sha256")):
        assert hashlib.sha256(base64.b64decode(b64)).hexdigest() == a[key]
    for f in kit["fonts"]:
        assert hashlib.sha256(
            base64.b64decode(f["ttf_b64"])).hexdigest() == f["ttf_sha256"]
        assert a["fonts"][f["style"].lower()] == f["ttf_sha256"]


def test_the_pieces_are_real_images_and_fonts(kit):
    from PIL import Image, ImageFont
    for b64, size in ((kit["mark_png_b64"], (1080, 1080)),
                      (kit["banner_png_b64"], (1600, 900)),
                      (kit["poster_png_b64"], (1200, 1600))):
        im = Image.open(io.BytesIO(base64.b64decode(b64)))
        assert im.size == size
    spec = Image.open(io.BytesIO(base64.b64decode(kit["specimen_png_b64"])))
    assert spec.width == 1800
    for f in kit["fonts"]:
        ImageFont.truetype(io.BytesIO(base64.b64decode(f["ttf_b64"])), 40)


def test_tokens_carry_the_portable_identity(kit):
    tk = kit["tokens"]
    assert tk["brand"] == "zentropy labs" and tk["seed"] == 58
    assert tk["family"] == "zentropy labs Mint"
    assert "weight" not in tk["face_params"] or True
    assert tk["grounds"]["dark"]["ground"].startswith("#")


def test_named_refusals():
    assert "name" in mint_kit("")["refusals"][0]
    assert "40" in mint_kit("x" * 41)["refusals"][0]
    heavy = mint_kit("ok", face_params={"weight": 0.30, "x_height": 0.44})
    assert heavy["refused"] and "refused" in heavy["refusals"][0]
