"""Tests for the shared decision_summary contract.

Every proof packet must end in a decision the operator can act on today. The
decision_summary is derived from the overall verdict and validated with a closed
vocabulary.
"""

from __future__ import annotations

from proof_surface._decision import (
    DECISION_OUTCOMES,
    derive_decision_summary,
    validate_decision_summary,
)


def _issues(ds):
    out = []
    validate_decision_summary(ds, out, "$.decision_summary")
    return out


def test_match_derives_approve_high():
    ds = derive_decision_summary("MATCH")
    assert ds["decision"] == "approve"
    assert ds["confidence"] == "high"
    assert ds["missing_evidence"] == []
    assert ds["reason"] and ds["next_action"]
    assert _issues(ds) == []


def test_drift_derives_block_high():
    ds = derive_decision_summary("DRIFT")
    assert ds["decision"] == "block"
    assert ds["confidence"] == "high"
    assert _issues(ds) == []


def test_unverifiable_derives_escalate_low_and_carries_missing_evidence():
    ds = derive_decision_summary(
        "UNVERIFIABLE", missing_evidence=["no after-state digest"]
    )
    assert ds["decision"] == "escalate"
    assert ds["confidence"] == "low"
    assert ds["missing_evidence"] == ["no after-state digest"]
    assert _issues(ds) == []


def test_validate_rejects_unknown_decision():
    ds = derive_decision_summary("MATCH")
    ds["decision"] = "yolo"
    assert any("decision" in i.path for i in _issues(ds))


def test_validate_rejects_unknown_confidence():
    ds = derive_decision_summary("MATCH")
    ds["confidence"] = "certain"
    assert any("confidence" in i.path for i in _issues(ds))


def test_validate_accepts_the_full_outcome_enum():
    for outcome in DECISION_OUTCOMES:
        ds = derive_decision_summary("MATCH")
        ds["decision"] = outcome
        assert _issues(ds) == []


def test_validate_rejects_non_object():
    issues = []
    validate_decision_summary("nope", issues, "$.decision_summary")
    assert issues
