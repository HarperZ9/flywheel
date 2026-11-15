"""Integration: every domain packet carries a derived, rendered decision_summary."""

from __future__ import annotations

from proof_surface import model_eval, research_claim
from proof_surface.model_eval import build_model_eval_packet
from proof_surface.research_claim import build_research_claim_packet

_HEX = "a" * 64


def _eval_packet(value):
    return build_model_eval_packet(
        model={"id": "m", "provider": "hosted"},
        eval_set={"name": "b", "ref": "r"},
        objective={"name": "o", "summary": "s"},
        metrics=[
            {
                "metric": "accuracy",
                "value": value,
                "target": 0.9,
                "direction": "maximize",
                "tolerance": 0.01,
                "method": "exact-match",
                "evidence": [_HEX],
            }
        ],
        claim="c",
        scope="s",
        packet_id="me",
    )


def test_match_yields_approve_and_renders_a_decision_section():
    p = _eval_packet(0.95)
    assert p["verdicts"]["overall"] == "MATCH"
    assert p["decision_summary"]["decision"] == "approve"
    assert p["decision_summary"]["confidence"] == "high"
    md = model_eval.render_report(p)
    assert "## Decision" in md and "APPROVE" in md


def test_drift_yields_block():
    p = _eval_packet(0.50)
    assert p["verdicts"]["overall"] == "DRIFT"
    assert p["decision_summary"]["decision"] == "block"


def test_unverifiable_yields_escalate_low_with_missing_evidence():
    p = build_research_claim_packet(
        statement="an open problem",
        sources=[{"ref": "x"}],
        attempts=[{"attempt_id": "a1", "method": "lean", "result": "incomplete"}],
        checks=[
            {"checker": "lean", "status": "unverifiable", "evidence": ["no checker"]}
        ],
        claim="c",
        scope="s",
        packet_id="rc",
        uncertainty=["the general claim is unproven"],
    )
    assert p["verdicts"]["overall"] == "UNVERIFIABLE"
    ds = p["decision_summary"]
    assert ds["decision"] == "escalate"
    assert ds["confidence"] == "low"
    assert ds["missing_evidence"] == ["the general claim is unproven"]
    assert "ESCALATE" in research_claim.render_report(p)
