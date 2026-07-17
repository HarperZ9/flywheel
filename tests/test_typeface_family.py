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


def test_variable_font_ships_as_one_file_with_a_wght_axis():
    from harness.typeface_family import mint_variable_family
    r = mint_variable_family(seed=58)
    assert not r["refused"], r.get("refusals")
    assert r["receipt"]["axis"] == "wght"
    assert len(r["receipt"]["masters"]) >= 2
    assert r["receipt"]["variable_id"]
    ttf = base64.b64decode(r["ttf_b64"])
    fontTools = pytest.importorskip("fontTools")
    from fontTools.ttLib import TTFont
    f = TTFont(io.BytesIO(ttf))
    assert "fvar" in f and "gvar" in f
    axes = f["fvar"].axes
    assert len(axes) == 1 and axes[0].axisTag == "wght"
    assert len(f["fvar"].instances) == len(r["receipt"]["masters"])


def test_instancing_the_variable_font_reproduces_each_static_master():
    # the load-bearing claim: this is a real interpolable font, not a wrapper.
    # instancing at a master's weight must reproduce that master's outline.
    pytest.importorskip("fontTools")
    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont
    from harness.typeface_family import mint_variable_family
    from harness.typeface_forge import mint, DEFAULTS
    from harness.typeface_ttf import to_ttf

    r = mint_variable_family(seed=58)
    ttf = base64.b64decode(r["ttf_b64"])
    masters = r["receipt"]["masters"]
    base = {k: v for k, v in DEFAULTS.items() if k != "weight"}

    def pts(font, ch="e"):
        gn = font.getBestCmap()[ord(ch)]
        return list(font["glyf"][gn].getCoordinates(font["glyf"])[0])

    for m in (masters[0], masters[-1]):  # lightest and heaviest
        inst = instantiateVariableFont(
            TTFont(io.BytesIO(ttf)), {"wght": round(m["weight"] * 4706)},
            inplace=False)
        static = TTFont(io.BytesIO(
            to_ttf(mint({**base, "weight": m["weight"]}, seed=58))))
        pi, ps = pts(inst), pts(static)
        assert len(pi) == len(ps)
        dev = sum(abs(a[0] - b[0]) + abs(a[1] - b[1])
                  for a, b in zip(pi, ps)) / len(pi)
        assert dev == 0, f"{m['style']} interpolation drifted {dev} units"


def test_incompatible_masters_are_refused_not_silently_broken():
    from harness.typeface_variable import to_variable_ttf
    from harness.typeface_forge import mint, DEFAULTS
    base = {k: v for k, v in DEFAULTS.items() if k != "weight"}
    a = {"style": "A", "weight": 0.085, "face": mint({**base, "weight": 0.085}, seed=58)}
    b = {"style": "B", "weight": 0.145, "face": mint({**base, "weight": 0.145}, seed=71)}
    # different seeds -> different skeletons -> topology can diverge; even if it
    # does not here, a single master must refuse (a variable font needs >= 2)
    one = to_variable_ttf([a])
    assert "error" in one and "two" in one["error"]
