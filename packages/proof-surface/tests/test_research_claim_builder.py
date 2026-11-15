"""Tests for the research-claim packet builder + crucible bridge."""

from __future__ import annotations

from proof_surface.research_claim import (
    build_research_claim_packet,
    to_crucible_inputs,
    validate_research_claim_packet,
)


def _sources():
    return [{"ref": "OEIS A000217", "url": "https://oeis.org/A000217"}]


def _attempts():
    return [{"attempt_id": "a1", "method": "numeric-probe", "result": "bounded"}]


def _build(check):
    return build_research_claim_packet(
        statement="For all n >= 1, sum_{k=1}^n k = n(n+1)/2.",
        sources=_sources(),
        attempts=_attempts(),
        checks=[check],
        claim="The identity held under the stated check.",
        scope="Bounded probe; not a general proof.",
        packet_id="rc-1",
        uncertainty=["bounded probe only"],
    )


def test_pass_check_is_match_and_promotes_to_crucible_match():
    p = _build(
        {
            "checker": "numeric-probe",
            "status": "pass",
            "evidence": ["n=1..1000 matched"],
        }
    )
    assert validate_research_claim_packet(p) == []
    assert p["verdicts"]["overall"] == "MATCH"
    assert p["verdicts"]["per_check"][0]["status"] == "MATCH"
    assert p["promotion"] == "CRUCIBLE_MATCH"


def test_unverifiable_check_preserves_evidence_and_stays_unverifiable():
    p = _build(
        {
            "checker": "lean",
            "status": "unverifiable",
            "evidence": ["no Lean checker available"],
        }
    )
    assert validate_research_claim_packet(p) == []
    assert p["verdicts"]["overall"] == "UNVERIFIABLE"
    assert p["promotion"] == "UNVERIFIABLE"
    # the failed attempt's evidence is preserved
    assert p["checks"][0]["evidence"] == ["no Lean checker available"]


def test_failed_check_is_drift():
    p = _build(
        {
            "checker": "counterexample-search",
            "status": "fail",
            "evidence": ["found n=2 mismatch"],
        }
    )
    assert validate_research_claim_packet(p) == []
    assert p["verdicts"]["overall"] == "DRIFT"


def test_to_crucible_inputs_is_the_documented_contract():
    p = _build({"checker": "numeric-probe", "status": "pass", "evidence": ["ok"]})
    thesis, measurements = to_crucible_inputs(p)
    claim = thesis["claims"][0]
    assert claim["text"] and claim["falsification"]
    row = measurements["measurements"][0]
    assert row["claim"] == claim["text"]
    assert row["deviation"] == 0.0
    assert row["tolerance"] == 0.5
