import pytest

import articulate
from articulate import detector, modes, profiles


def test_all_modes_load_and_are_valid():
    for name in modes.names():
        prof = modes.load(name)
        assert prof["slop"] in {"off", "flavored", "strict"}
        assert "gate_promote" in prof and "editor" in prof


def test_unknown_mode_raises():
    with pytest.raises(modes.ModeError):
        modes.load("nope/nope")


def test_promoted_categories_are_all_known():
    known = detector.known_categories()
    for name in modes.names():
        for cat in modes.load(name)["gate_promote"]:
            assert cat in known, f"{name} promotes unknown category {cat}"


def test_gate_promote_blocks_a_medium_category():
    txt = "Our platform is cutting-edge and seamless.\n"
    flav = articulate.check_text(txt, profile=profiles.load("flavored"))
    mk = articulate.check_text(txt, profile=modes.load("marketing/explain"))
    assert flav["gate"] == "ok"          # MEDIUM marketing not gated under flavored
    assert mk["gate"] == "blocked"       # marketing promoted -> gates


def test_argue_promotes_unsupported_authority():
    txt = "Studies have shown our approach works better.\n"
    r = articulate.check_text(txt, profile=modes.load("technical-docs/argue"))
    assert r["gate"] == "blocked"


def test_narrative_off_gates_nothing():
    txt = "You can watch what a model does. You cannot watch what it is.\n"
    r = articulate.check_text(txt, profile=modes.load("narrative/narrate"))
    assert r["gate"] == "ok"             # slop=off: reported, never gated


def test_gate_promote_only_adds_never_removes_the_floor():
    # A HIGH device still gates under any mode; gate_promote cannot un-gate it.
    txt = "This is not a tool, but a force.\n"   # antithesis (HIGH)
    for name in ("marketing/explain", "narrative/narrate"):
        prof = modes.load(name)
        r = articulate.check_text(txt, profile=prof)
        if prof["slop"] != "off":
            assert r["gate"] == "blocked"
