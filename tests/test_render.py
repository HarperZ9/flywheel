"""The export layer: one verdict, four scientific formats.

The formatter tests assert the two disciplines a renderer owes: never add a claim,
never drop a qualification. The Lean tests assert the fourth format is a genuine
re-check, and they run the Lean toolchain when it is present.
"""
import json
import shutil
from math import comb

import pytest

from harness.certificates.crossing import CrossingOracle
from harness.certificates.crossing_generator import convex_drawing
from harness.certificates.zarankiewicz import ZarankiewiczOracle
from harness.lean_export import (
    crossing_lean, lean_axioms, to_lean, zarankiewicz_lean,
)
from harness.render import FORMATS, render, to_latex, to_markdown, to_text

HAVE_LEAN = shutil.which("lean") is not None


def crossing_cert(n=5):
    return {"n": n, "edges": [[u, v] for u in range(n) for v in range(u + 1, n)],
            "coords": [list(p) for p in convex_drawing(n)], "crossings": comb(n, 4)}


def crossing_result(cert):
    return CrossingOracle().verify(json.dumps(cert),
                                   {"n": cert["n"], "edges": cert["edges"]})


@pytest.fixture
def result():
    return crossing_result(crossing_cert())


# --- the two disciplines a formatter owes -----------------------------------

@pytest.mark.parametrize("fmt", ["text", "markdown", "latex"])
def test_every_format_carries_the_optimality_caveat(result, fmt):
    """The exact surface where a checked count becomes a solved problem. The
    caveat must survive into every human-facing format."""
    out = render(result, fmt)
    # LaTeX escapes the underscores, so match the part that survives escaping.
    assert "OPTIMALITY" in out.upper()


@pytest.mark.parametrize("fmt", ["text", "markdown", "latex"])
def test_every_format_carries_the_verdict_and_objective(result, fmt):
    out = render(result, fmt)
    assert "PASS" in out
    assert "5" in out                       # the objective, the crossing count


@pytest.mark.parametrize("fmt", ["text", "markdown", "latex"])
def test_a_formatter_adds_no_optimality_language(result, fmt):
    """It must not INTRODUCE a claim. The only optimality word allowed is inside
    the NOT_PROVES_OPTIMALITY disclaimer."""
    low = render(result, fmt).lower()
    for banned in ("crossing number of", "optimal drawing", "minimum crossings"):
        assert banned not in low


def test_latex_escapes_special_characters(result):
    tex = to_latex(result)
    # the family name contains an underscore, which is a LaTeX control char
    assert r"\_" in tex
    assert "crossing_certificate" not in tex   # the raw form must be escaped


def test_markdown_has_a_verdict_heading(result):
    assert to_markdown(result).startswith("## Verdict: PASS")


def test_text_is_plain_and_lists_does_not_prove(result):
    t = to_text(result)
    assert t.startswith("verdict     : PASS")
    assert "does not prove:" in t


def test_an_unknown_format_is_refused(result):
    with pytest.raises(ValueError, match="unknown format"):
        render(result, "yaml")


# --- the Lean export is emitted correctly (no toolchain needed) --------------

def test_lean_export_needs_the_certificate(result):
    with pytest.raises(ValueError, match="cert.*required"):
        render(result, "lean")


def test_lean_export_refuses_a_non_pass():
    bad = crossing_cert()
    bad["crossings"] = 999
    r = crossing_result(bad)
    assert str(r.verdict()) == "FAIL"
    with pytest.raises(ValueError, match="for a PASS"):
        to_lean(r, bad)


def test_lean_export_refuses_a_family_with_no_encoding(result, monkeypatch):
    import harness.lean_export as le
    monkeypatch.setitem(le._EMITTERS, "rectilinear_crossing", le._EMITTERS["rectilinear_crossing"])
    # a made-up family has no emitter
    class Fake:
        cmd = "x:no_such_family"
        def verdict(self): return "PASS"
    with pytest.raises(ValueError, match="no Lean export"):
        to_lean(Fake(), {})


def test_emitted_lean_is_self_contained(result):
    src = crossing_lean(crossing_cert())
    assert "import Mathlib" not in src
    assert not any(ln.startswith("import ") for ln in src.splitlines())
    assert "#print axioms" in src         # the trust base is in the file
    assert "native_decide" in src


def test_emitted_lean_states_it_does_not_prove_optimality(result):
    assert "optimality" in crossing_lean(crossing_cert()).lower()


# --- the Lean export is a genuine re-check (needs the toolchain) --------------

@pytest.mark.skipif(not HAVE_LEAN, reason="lean toolchain not installed")
def test_lean_compiles_a_true_crossing_certificate():
    src = crossing_lean(crossing_cert())
    res = lean_axioms(src)
    assert res["ok"] is True, res
    assert res["axioms"], "a compiled proof must report its axioms"


@pytest.mark.skipif(not HAVE_LEAN, reason="lean toolchain not installed")
def test_lean_rejects_a_wrong_crossing_count():
    """The property that makes it a check and not a rubber stamp."""
    bad = crossing_cert()
    bad["crossings"] = comb(5, 4) - 1
    assert lean_axioms(crossing_lean(bad))["ok"] is False


@pytest.mark.skipif(not HAVE_LEAN, reason="lean toolchain not installed")
def test_lean_checks_zarankiewicz_and_rejects_a_k22():
    free = {"m": 3, "n": 3, "edges": [[0, 3], [0, 4], [1, 3], [2, 4]]}
    assert lean_axioms(zarankiewicz_lean(free))["ok"] is True
    k22 = {"m": 2, "n": 2, "edges": [[0, 0], [0, 1], [1, 0], [1, 1]]}
    assert lean_axioms(zarankiewicz_lean(k22))["ok"] is False


def test_lean_axioms_is_honest_when_no_toolchain(monkeypatch):
    """Absence of a checker is not a check. A missing toolchain returns ok=None,
    never a false pass."""
    import shutil
    import harness.lean_export as le
    monkeypatch.setattr(shutil, "which", lambda _x: None)
    res = le.lean_axioms("theorem t : True := trivial")
    assert res["ok"] is None
    assert "not on PATH" in res["note"]
