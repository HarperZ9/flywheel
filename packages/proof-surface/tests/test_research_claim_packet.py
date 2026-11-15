"""Tests for the research-claim proof packet validator (pipeline-math++).

A research packet joins source refs, a formal statement, prover/checker attempts,
verification checks, a verdict, and a promotion-ladder rung. Its defining honest
property: a failed or unverifiable attempt still produces a *valid* packet that
preserves sources, attempts, and next checks.
"""

from __future__ import annotations

from proof_surface.research_claim import validate_research_claim_packet

_HEX = "a" * 64


def _valid() -> dict:
    return {
        "version": "research-claim-proof-packet/v0",
        "packet_id": "rc-1",
        "claim": "The identity sum_{k=1}^n k = n(n+1)/2 held for a bounded numeric probe.",
        "scope": "One arithmetic identity; bounded probe n=1..1000; not a general proof.",
        "statement": "For all n >= 1, sum_{k=1}^n k = n(n+1)/2.",
        "sources": [
            {
                "ref": "OEIS A000217 (triangular numbers)",
                "url": "https://oeis.org/A000217",
            },
            {"ref": "local probe log", "sha256": _HEX},
        ],
        "attempts": [
            {
                "attempt_id": "a1",
                "method": "numeric-probe",
                "result": "bounded",
                "notes": "n=1..1000",
            }
        ],
        "checks": [
            {
                "checker": "numeric-probe",
                "status": "pass",
                "evidence": ["n=1..1000 all matched"],
            }
        ],
        "verdicts": {
            "overall": "MATCH",
            "per_check": [{"checker": "numeric-probe", "status": "MATCH"}],
        },
        "promotion": "PROBE_MATCH",
        "uncertainty": ["bounded probe, not a general proof for all n"],
        "decision_summary": {
            "decision": "approve",
            "reason": "the check passed",
            "confidence": "high",
            "missing_evidence": [],
            "next_action": "proceed",
        },
    }


def _paths(issues):
    return [i.path for i in issues]


def test_valid_packet_has_no_issues():
    assert validate_research_claim_packet(_valid()) == []


def test_failed_attempt_still_produces_a_valid_packet():
    d = _valid()
    d["claim"] = "A proof was attempted; the checker could not verify it."
    d["attempts"][0]["result"] = "failed"
    d["checks"][0]["status"] = "unverifiable"
    d["verdicts"]["overall"] = "UNVERIFIABLE"
    d["verdicts"]["per_check"][0]["status"] = "UNVERIFIABLE"
    d["promotion"] = "UNVERIFIABLE"
    # Honest failure is still a valid, useful packet.
    assert validate_research_claim_packet(d) == []


def test_unknown_root_field_rejected():
    d = _valid()
    d["solved"] = True
    assert any("solved" in p for p in _paths(validate_research_claim_packet(d)))


def test_source_without_ref_rejected():
    d = _valid()
    d["sources"][0] = {"url": "https://example.com"}
    assert any("sources[0].ref" in p for p in _paths(validate_research_claim_packet(d)))


def test_bad_source_digest_rejected():
    d = _valid()
    d["sources"][1]["sha256"] = "nope"
    assert any("sha256" in p for p in _paths(validate_research_claim_packet(d)))


def test_unknown_attempt_result_rejected():
    d = _valid()
    d["attempts"][0]["result"] = "obviously-true"
    assert any("result" in p for p in _paths(validate_research_claim_packet(d)))


def test_unknown_check_status_rejected():
    d = _valid()
    d["checks"][0]["status"] = "definitely"
    assert any("status" in p for p in _paths(validate_research_claim_packet(d)))


def test_promotion_must_be_on_the_ladder():
    d = _valid()
    d["promotion"] = "PROMOTED_LAW"  # reserved; not reachable by a packet
    assert any("promotion" in p for p in _paths(validate_research_claim_packet(d)))


def test_check_without_verdict_is_flagged():
    d = _valid()
    d["verdicts"]["per_check"] = []
    issues = validate_research_claim_packet(d)
    assert any("per_check" in i.path and "numeric-probe" in i.message for i in issues)


def test_authority_language_rejected():
    d = _valid()
    d["claim"] = "This theorem is CERTIFIED proven."
    assert validate_research_claim_packet(d) != []
