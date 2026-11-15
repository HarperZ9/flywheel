"""Tests for the center module (the neutral-center reconcile, on the spine's Certificate)."""
from __future__ import annotations
import json

from coherence_membrane.certificate import Verdict
from coherence_membrane.center import (CriterionSpec, StubMind, StubJudge, reconcile_at_center,
                                       winner_of, scores_of, criterion_of)
from coherence_membrane.center.adapters import CallableMind, CallableJudge
from coherence_membrane.center.grounding import grounding_penalty, unsupported_tokens

VIEWS = {"text": "A subject in prose: it does X, integrates Y, and reports Z.",
         "diagram": "12 nodes, 9 edges; hub at center; lineage A->B->C feeding the hub."}
NOVELTY = CriterionSpec("creator", {"novelty": 0.6, "structure": 0.1, "function": 0.1,
                                    "completeness": 0.1, "grounded": 0.1})
CORRECT = CriterionSpec("researcher", {"novelty": 0.05, "structure": 0.25, "function": 0.25,
                                       "completeness": 0.25, "grounded": 0.20})


def _minds():
    return [StubMind("mind-A", "text"), StubMind("mind-B", "diagram")]


def test_criterion_normalizes_and_validates():
    c = CriterionSpec("x", {"a": 3, "b": 1}).normalized()
    assert abs(sum(c.dims.values()) - 1.0) < 1e-9 and abs(c.dims["a"] - 0.75) < 1e-9
    for bad in ({}, {"a": -1}, {"a": 0}):
        try:
            CriterionSpec("x", bad); assert False
        except ValueError:
            pass


def test_emits_spine_certificate_naming_criterion():
    cert = reconcile_at_center(VIEWS, _minds(), CORRECT, StubJudge())
    assert cert.verdict is Verdict.VERIFIED and cert.oracle == "neutral-center-v1"
    assert criterion_of(cert) == "researcher"
    assert winner_of(cert) in scores_of(cert)
    # it IS a spine Certificate -- round-trips via the contract's own to_dict/from_dict
    from coherence_membrane.certificate import Certificate
    assert Certificate.from_dict(json.loads(json.dumps(cert.to_dict()))).oracle == cert.oracle


def test_criterion_relativity_flips_winner():
    wn = winner_of(reconcile_at_center(VIEWS, _minds(), NOVELTY, StubJudge()))
    wc = winner_of(reconcile_at_center(VIEWS, _minds(), CORRECT, StubJudge()))
    assert wn != wc
    assert wc.startswith("meeting:") and not wn.startswith("meeting:")


def test_meeting_beats_solos_under_wholeness():
    sc = scores_of(reconcile_at_center(VIEWS, _minds(), CORRECT, StubJudge()))
    solos = {k: v for k, v in sc.items() if not k.startswith("meeting:")}
    meets = {k: v for k, v in sc.items() if k.startswith("meeting:")}
    assert max(m["weighted"] for m in meets.values()) > max(s["weighted"] for s in solos.values())


def test_grounding_flags_overbuild():
    grounded = "it does X integrates Y reports Z"
    over = grounded + " quantumblockchain neuralfabrication telepathicledger"
    assert grounding_penalty(grounded, VIEWS) == 0.0
    assert grounding_penalty(over, VIEWS) > 0.0
    assert "quantumblockchain" in unsupported_tokens(over, VIEWS)


def test_fail_closed():
    assert reconcile_at_center(VIEWS, _minds(), None, StubJudge()).verdict is Verdict.UNVERIFIABLE
    assert reconcile_at_center({"text": " "}, _minds(), CORRECT, StubJudge()).verdict is Verdict.UNVERIFIABLE
    assert reconcile_at_center(VIEWS, [StubMind("s", "text")], CORRECT, StubJudge()).verdict is Verdict.UNVERIFIABLE


def test_callable_adapters_with_fake_model():
    def fake(prompt):
        if "Score this candidate" in prompt:
            s = 0.9 if "reconcile" in prompt.lower() else 0.4
            return "x " + json.dumps({d: s for d in ("novelty", "structure", "function",
                                                     "completeness", "grounded")})
        return "PROPOSAL " + prompt.split(":")[-1][:60] + " (reconcile)"
    minds = [CallableMind("A", "text", fake), CallableMind("B", "diagram", fake)]
    cert = reconcile_at_center(VIEWS, minds, CORRECT, CallableJudge(fake))
    assert cert.verdict is Verdict.VERIFIED and winner_of(cert) in scores_of(cert)


def test_callable_judge_failsafe():
    assert all(v == 0.0 for v in CallableJudge(lambda p: "not json").score("x", VIEWS).values())
