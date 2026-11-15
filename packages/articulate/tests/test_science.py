"""Scientific-communication modes: making a hard proof or whitepaper legible
without losing rigor, and never asserting the result is correct.

The boundary is load-bearing and tested at the artifact: a clean gate or a Match
receipt screens the prose under a named ruleset; it says nothing about whether the
theorem is true. The editor also masks every math span so a rewrite cannot alter a
formula, a quantifier order, or an inequality direction.
"""
import os
import shutil

import pytest

import articulate
from articulate import editor, modes, profiles, receipt

_TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_sci")


@pytest.fixture()
def work():
    os.makedirs(_TMP, exist_ok=True)
    yield _TMP
    shutil.rmtree(_TMP, ignore_errors=True)


def _scored(v=4):
    return {"concreteness": v, "commitment": v, "economy": v, "rhythm": v,
            "restatable": v, "worst": ["w"]}


# --- the modes wire up ----------------------------------------------------- #

def test_academic_prove_wires():
    m = modes.load("academic/prove")
    assert m["slop"] == "flavored"             # inherits the proof base
    assert "theorem" in m["keep"] and "at scale" in m["keep"]
    assert m["gate_promote"] == ()
    assert m["editor"]["run_fix_by_default"] is False


def test_science_writing_explain_wires():
    m = modes.load("science-writing/explain")
    assert m["slop"] == "flavored"
    assert "vorticity" in m["keep"] and "at scale" in m["keep"]


# --- the detector does not over-flag rigorous prose ------------------------ #

def test_pde_idiom_not_register_jargon():
    txt = ("The vorticity satisfies the maximum principle at scale on the "
           "surface area of the domain.\n")
    r = articulate.check_text(txt, profile=modes.load("academic/prove"))
    assert "register-jargon" not in {f["category"] for f in r["medium"]}
    assert r["clean"] is True


def test_there_exists_is_not_an_expletive_opener():
    txt = "There exists a unique constant C such that the inequality holds for all t.\n"
    r = articulate.check_text(txt, profile=modes.load("academic/prove"))
    assert "expletive-opener" not in {f["category"] for f in r["low"]}


def test_two_sentence_contrast_passes_but_the_device_still_gates():
    ok = articulate.check_text("This establishes existence. It does not establish uniqueness.\n",
                               profile=modes.load("academic/prove"))
    banned = articulate.check_text("This is not a bound but an identity.\n",
                                   profile=modes.load("academic/prove"))
    assert ok["gate"] == "ok"
    assert banned["gate"] == "blocked"   # not-X-but-Y still gates, even in a proof


# --- routing and the in-source tag ----------------------------------------- #

def test_tex_under_papers_routes_math_aware():
    assert profiles.profile_for("papers/proof.tex") != "essay"
    assert profiles.profile_for("proofs/main.tex") == "proof"
    assert profiles.profile_for("essays/piece.tex") == "essay"   # essays stay device-free


def test_latex_comment_profile_tag():
    assert profiles.declared_profile("% writing-profile: proof\n\\section{x}\n") == "proof"
    assert profiles.declared_profile("writing-profile: proof\n") == "proof"


# --- the boundary, at the artifact ----------------------------------------- #

def test_receipt_carries_no_correctness_field():
    rec = receipt.make_receipt("Let x be given. Assume the bound holds. Then the "
                               "claim follows.\n", "proof")
    forbidden = {"approved", "verified", "correct", "trusted", "valid", "sound"}
    assert forbidden.isdisjoint(rec.keys())


# --- the editor protects math and refuses to rewrite a proof by default ---- #

def test_prove_mode_does_not_rewrite_by_default(work):
    src = os.path.join(work, "thm.tex")
    with open(src, "w", encoding="utf-8") as fh:
        fh.write("The estimate $\\|u\\|_{L^2} \\le C$ holds for all t.\n")
    out = os.path.join(work, "thm.polished.tex")

    def boom(*a):
        raise AssertionError("academic/prove must not rewrite by default")

    editor.polish(src, out, passes=2, bar=5, mode="academic/prove",
                  rewrite_fn=boom, judge_fn=lambda t: _scored())
    with open(out, encoding="utf-8") as fh:
        assert "$\\|u\\|_{L^2} \\le C$" in fh.read()


def test_math_spans_survive_a_rewrite(work):
    src = os.path.join(work, "note.tex")
    body = ("The estimate $\\|u\\|_{L^2} \\le C$ holds for all t.\n"
            "We bound the term \\[ \\int_0^T \\|\\nabla u\\|^2 \\, dt < \\infty. \\]\n")
    with open(src, "w", encoding="utf-8") as fh:
        fh.write(body)
    out = os.path.join(work, "note.polished.tex")

    # A hostile rewrite: it would strip every '$', but it never sees the math,
    # because mask_math replaces each span with a placeholder first.
    def rewrite_fn(t, mech, worst):
        return t.replace("estimate", "bound").replace("$", "")

    editor.polish(src, out, passes=1, bar=5,
                  rewrite_fn=rewrite_fn, judge_fn=lambda t: _scored())
    result = open(out, encoding="utf-8").read()
    assert "$\\|u\\|_{L^2} \\le C$" in result           # inline math intact
    assert "\\[ \\int_0^T \\|\\nabla u\\|^2 \\, dt < \\infty. \\]" in result  # display intact
    assert "bound" in result                            # the prose rewrite did land


def test_mask_and_splice_roundtrips():
    text = "before $a+b$ middle \\[ x = y \\] after"
    masked, spans = editor.mask_math(text)
    assert "$a+b$" not in masked and "\\[ x = y \\]" not in masked
    assert editor.splice_math(masked, spans) == text
