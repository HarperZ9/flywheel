"""Tests for Neutral Center v1 — covering the v1 success criteria (SC1–SC6).

Hermetic: StubMind/StubJudge, no model/network (SC6).
"""
from __future__ import annotations
import json

from center import CriterionSpec, StubMind, StubJudge, Verdict, reconcile_at_center

VIEWS = {
    "text": "A subject described in prose: it does X, integrates Y, and reports Z.",
    "diagram": "12 nodes, 9 edges; hub at center; lineage A->B->C feeding the hub.",
}
NOVELTY = CriterionSpec("creator", {"novelty": 0.6, "structure": 0.1, "function": 0.1,
                                    "completeness": 0.1, "grounded": 0.1})
CORRECT = CriterionSpec("researcher", {"novelty": 0.05, "structure": 0.25, "function": 0.25,
                                       "completeness": 0.25, "grounded": 0.20})


def _minds():
    return [StubMind("mind-A", "text"), StubMind("mind-B", "diagram")]


# --- R1: criterion is first-class, normalized, validated -----------------------------------
def test_criterion_normalizes_and_validates():
    c = CriterionSpec("x", {"a": 3, "b": 1}).normalized()
    assert abs(sum(c.dims.values()) - 1.0) < 1e-9 and abs(c.dims["a"] - 0.75) < 1e-9
    for bad in ({}, {"a": -1}, {"a": 0}):
        try:
            CriterionSpec("x", bad); assert False, "expected ValueError"
        except ValueError:
            pass
    try:
        CriterionSpec("", {"a": 1}); assert False
    except ValueError:
        pass


# --- SC1: end-to-end, Certificate names the criterion --------------------------------------
def test_end_to_end_certificate_names_criterion():
    cert = reconcile_at_center(VIEWS, _minds(), CORRECT, StubJudge())
    assert cert.verdict is Verdict.VERIFIED
    assert cert.criterion["name"] == "researcher"
    assert cert.winner in cert.scores and "weighted" in cert.scores[cert.winner]
    # round-trips (re-checkable, R5)
    from center import Certificate
    assert Certificate.from_dict(json.loads(json.dumps(cert.to_dict()))).winner == cert.winner


# --- SC2 / R6: criterion-relativity is live — the winner flips with the named criterion -----
def test_criterion_relativity_flips_winner():
    w_novelty = reconcile_at_center(VIEWS, _minds(), NOVELTY, StubJudge()).winner
    w_correct = reconcile_at_center(VIEWS, _minds(), CORRECT, StubJudge()).winner
    assert w_novelty != w_correct, "same subject, different named criterion must be able to flip the winner"
    # under correctness, a 'meeting' candidate should win (wholeness); under novelty, a solo
    assert w_correct.startswith("meeting:")
    assert not w_novelty.startswith("meeting:")


# --- SC5 / R3: the meeting genuinely differs from either solo -------------------------------
def test_meeting_differs_from_solos():
    cert = reconcile_at_center(VIEWS, _minds(), CORRECT, StubJudge())
    solos = {k: v for k, v in cert.scores.items() if not k.startswith("meeting:")}
    meetings = {k: v for k, v in cert.scores.items() if k.startswith("meeting:")}
    assert solos and meetings
    # the meeting's weighted score under a wholeness criterion exceeds the best solo
    assert max(m["weighted"] for m in meetings.values()) > max(s["weighted"] for s in solos.values())


# --- SC3 / R7: grounding guardrail flags an injected over-reach -----------------------------
def test_grounding_flags_overbuild():
    from center.grounding import grounding_penalty, unsupported_tokens
    grounded_text = "it does X integrates Y reports Z"     # all in VIEWS
    overbuilt = grounded_text + " quantumblockchain neuralfabrication telepathicledger"
    assert grounding_penalty(grounded_text, VIEWS) == 0.0
    assert grounding_penalty(overbuilt, VIEWS) > 0.0
    assert "quantumblockchain" in unsupported_tokens(overbuilt, VIEWS)


# --- SC4 / R8: fail-closed -------------------------------------------------------------------
def test_fail_closed():
    assert reconcile_at_center(VIEWS, _minds(), None, StubJudge()).verdict is Verdict.UNVERIFIABLE
    assert reconcile_at_center({"text": "  "}, _minds(), CORRECT, StubJudge()).verdict is Verdict.UNVERIFIABLE
    one_mind = [StubMind("solo", "text")]
    assert reconcile_at_center(VIEWS, one_mind, CORRECT, StubJudge()).verdict is Verdict.UNVERIFIABLE


# --- Adapters: the live path is expressible + hermetically testable with a fake model call ---
def test_callable_adapters_with_fake_model():
    from center.adapters import CallableMind, CallableJudge
    import json as _j

    def fake_model(prompt: str) -> str:
        # a deterministic stand-in for a model call
        if "Score this candidate" in prompt:
            # a fake judge: reward candidates that mention "reconcile"
            s = 0.9 if "reconcile" in prompt.lower() else 0.4
            return "scores: " + _j.dumps({d: s for d in
                   ("novelty", "structure", "function", "completeness", "grounded")})
        return "PROPOSAL: " + prompt.split(":")[-1].strip()[:60] + " (reconcile)"

    minds = [CallableMind("A", "text", fake_model), CallableMind("B", "diagram", fake_model)]
    cert = reconcile_at_center(VIEWS, minds, CORRECT, CallableJudge(fake_model))
    assert cert.verdict is Verdict.VERIFIED and cert.winner in cert.scores


def test_callable_judge_failsafe_on_garbage():
    from center.adapters import CallableJudge
    j = CallableJudge(lambda p: "not json at all")
    sc = j.score("anything", VIEWS)
    assert all(v == 0.0 for v in sc.values())   # unreadable witness -> no credit


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn(); print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {fn.__name__}: {e}")
        except Exception as e:
            failed += 1; print(f"ERROR {fn.__name__}: {e!r}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
