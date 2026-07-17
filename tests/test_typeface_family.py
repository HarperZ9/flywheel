"""A family must be a product line, not a folder: same seed means shared
bones, weights actually differ in the shipped bytes, a refused instance
is named while the rest still ship, and the family id re-derives."""

import base64
import io
import struct

import pytest

from harness.typeface_family import mint_family


@pytest.fixture(scope="module")
def fam():
    return mint_family(seed=58)


def test_the_line_ships_four_weights_deterministically(fam):
    assert not fam["refused"]
    styles = [i["style"] for i in fam["instances"]]
    assert styles == ["Light", "Regular", "Medium", "Bold"]
    again = mint_family(seed=58)
    assert again["receipt"]["family_id"] == fam["receipt"]["family_id"]
    assert [i["ttf_sha256"] for i in again["instances"]] == \
        [i["ttf_sha256"] for i in fam["instances"]]
    assert mint_family(seed=59)["receipt"]["family_id"] != \
        fam["receipt"]["family_id"]


def test_weights_differ_in_the_bytes_not_just_the_names(fam):
    def weight_class(b64):
        raw = base64.b64decode(b64)
        n = struct.unpack(">H", raw[4:6])[0]
        for i in range(n):
            tag, _, off, _ = struct.unpack(">4sLLL", raw[12 + 16 * i:28 + 16 * i])
            if tag == b"OS/2":
                return struct.unpack(">H", raw[off + 4:off + 6])[0]
        raise AssertionError("no OS/2 table")
    classes = [weight_class(i["ttf_b64"]) for i in fam["instances"]]
    assert classes == sorted(classes) and classes[0] < classes[-1]


def test_every_instance_loads_and_renders(fam):
    pytest.importorskip("PIL")
    from PIL import Image, ImageDraw, ImageFont
    for inst in fam["instances"]:
        font = ImageFont.truetype(
            io.BytesIO(base64.b64decode(inst["ttf_b64"])), 72)
        im = Image.new("L", (900, 160), 0)
        ImageDraw.Draw(im).text((10, 30), "adhesion 58", font=font, fill=255)
        assert im.getbbox() is not None, f"{inst['style']} left no ink"


def test_a_refused_weight_is_named_and_the_rest_ship():
    fam = mint_family(seed=58, instances=[("Regular", 0.085),
                                          ("Blind", 0.30)])
    assert not fam["refused"]
    assert [i["style"] for i in fam["instances"]] == ["Regular"]
    ref = fam["receipt"]["refused_instances"]
    assert len(ref) == 1 and ref[0]["style"] == "Blind"
    assert "counter" in ref[0]["refusals"][0]


def test_an_all_refused_family_refuses_by_name():
    fam = mint_family(seed=58, instances=[("Blind", 0.32)])
    assert fam["refused"] and "refused" in fam["refusals"][0]
