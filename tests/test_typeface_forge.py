"""The typeface forge must be a deterministic instrument: the same seed and
parameters mint the same face with the same receipt; the legibility rules
are verifiers that can refuse; and every outline is a closed, drawable
polygon whose style follows the pen, not chance."""

import pytest

from harness.typeface_forge import DEFAULTS, mint


def test_same_inputs_mint_the_same_receipt():
    a = mint(dict(DEFAULTS), seed=58)
    b = mint(dict(DEFAULTS), seed=58)
    assert a["receipt"]["mint_id"] == b["receipt"]["mint_id"]
    assert a["receipt"]["mint_id"] != mint(dict(DEFAULTS), seed=59)["receipt"]["mint_id"]


def test_outlines_are_closed_and_carry_area():
    face = mint(dict(DEFAULTS), seed=58)
    assert face["glyphs"], "a mint with no glyphs is not a face"
    for name, g in face["glyphs"].items():
        for contour in g["contours"]:
            assert len(contour) >= 8, f"{name}: contour too sparse"
            # closed: the expansion returns an explicit ring
            assert contour[0] == contour[-1], f"{name}: contour not closed"
            # signed area is nonzero: the pen laid down real ink
            area = 0.0
            for (x1, y1), (x2, y2) in zip(contour, contour[1:]):
                area += x1 * y2 - x2 * y1
            assert abs(area) > 100, f"{name}: degenerate contour"


def test_contrast_thins_the_horizontals():
    params = dict(DEFAULTS)
    params["contrast"] = 0.6
    face = mint(params, seed=58)
    o = face["glyphs"]["o"]
    assert o["h_stroke"] < o["v_stroke"]
    mono = mint({**dict(DEFAULTS), "contrast": 1.0}, seed=58)
    assert mono["glyphs"]["o"]["h_stroke"] == pytest.approx(
        mono["glyphs"]["o"]["v_stroke"], rel=0.05)


def test_the_legibility_gate_refuses_a_blind_face():
    params = dict(DEFAULTS)
    params["weight"] = 0.30          # stems so heavy the counters close
    params["x_height"] = 0.44
    result = mint(params, seed=58)
    assert result["refused"] is True
    assert any("counter" in r for r in result["refusals"])


def test_round_glyphs_overshoot_and_sit_tighter():
    face = mint(dict(DEFAULTS), seed=58)
    o = face["glyphs"]["o"]
    n = face["glyphs"]["n"]
    # overshoot: the round extreme pokes past the x-height line
    assert o["top"] > n["top"]
    # Tracy spacing: round sides carry smaller sidebearings than straight
    assert o["lsb"] < n["lsb"]


def test_the_receipt_names_its_rules_and_engine():
    face = mint(dict(DEFAULTS), seed=58)
    r = face["receipt"]
    assert r["engine_sha256"] and r["skeletons_sha256"]
    for rule in ("overshoot", "contrast-floor", "counter-minimum",
                 "tracy-spacing"):
        assert rule in r["rules_applied"]
    assert r["charset"] == sorted(set("adhesion"))
    assert "svg" in face and "<svg" in face["svg"]
