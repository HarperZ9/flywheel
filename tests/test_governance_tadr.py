"""Tests for the TADR tier system, classification receipt, and control baseline."""
from __future__ import annotations

import hashlib
import json

import pytest

import harness.governance.tadr_receipt as tadr_receipt
import harness.governance.control_baseline as control_baseline

from harness.governance.tadr_tier import (
    T3_OVERRIDES,
    TADR_MODIFIERS,
    TADR_TIERS,
    TierClassification,
    classify,
    enforce_no_tier_inflation,
    tier_rank,
    validate_modifiers,
    validate_tier,
)
from harness.governance.tadr_receipt import (
    SCHEMA,
    build_classification_receipt,
    verify_classification_receipt,
    MATCH,
    TAMPERED,
    UNVERIFIABLE,
)
from harness.governance.control_baseline import (
    T1_CONTROLS,
    T2_CONTROLS,
    T3_CONTROLS,
    check_compliance,
)


# --- tier system --------------------------------------------------------


def test_tier_ranks():
    assert tier_rank("T1") == 1
    assert tier_rank("T2") == 2
    assert tier_rank("T3") == 3
    assert tier_rank("bogus") == 0


def test_validate_tier():
    assert validate_tier("T1") is True
    assert validate_tier("T3") is True
    assert validate_tier("T4") is False


def test_validate_modifiers():
    assert validate_modifiers(["A", "D"]) == []
    assert len(validate_modifiers(["A", "Z"])) == 1


def test_no_inflation_allows_same_or_lower():
    assert enforce_no_tier_inflation("T3", "T1") is True
    assert enforce_no_tier_inflation("T3", "T3") is True
    assert enforce_no_tier_inflation("T1", "T3") is False
    assert enforce_no_tier_inflation("T2", "T3") is False


@pytest.mark.parametrize(
    ("authorized", "requested"),
    [("T9", "T1"), ("T1", "T9"), ("T9", "T9"), ("", "T1")],
)
def test_no_inflation_rejects_unknown_tiers(authorized, requested):
    assert enforce_no_tier_inflation(authorized, requested) is False


# --- classify -----------------------------------------------------------


def test_classify_no_overrides_is_t1():
    result = classify([])
    assert result.tier == "T1"


def test_classify_t3_override():
    result = classify(["mass-casualty-potential"])
    assert result.tier == "T3"
    assert "mass-casualty-potential" in result.triggered_overrides


def test_classify_t2_override():
    result = classify(["multi-site-disruption"])
    assert result.tier == "T2"


def test_classify_t3_overrides_t2():
    result = classify(["multi-site-disruption", "mass-casualty-potential"])
    assert result.tier == "T3"


def test_classify_stage_b_escalates_on_catastrophic_magnitude():
    result = classify([], assessment={"consequence_magnitude": "catastrophic"})
    assert result.tier == "T3"


def test_classify_stage_b_escalates_on_uncontrolled_autonomy():
    result = classify([], assessment={"autonomy": "uncontrolled"})
    assert result.tier == "T3"


def test_classify_stage_b_escalates_on_irreversible():
    result = classify([], assessment={"reversibility": "irreversible"})
    assert result.tier == "T3"


def test_classify_with_modifiers():
    result = classify([], modifiers=["A", "D"])
    assert result.tier == "T1"
    assert "A" in result.modifiers
    assert "D" in result.modifiers
    assert "A" in result.label()
    assert "T1" in result.label()


def test_classify_rejects_invalid_modifiers():
    with pytest.raises(ValueError, match="invalid"):
        classify([], modifiers=["Z"])


def test_classify_rejects_unknown_override():
    with pytest.raises(ValueError, match="override"):
        classify(["plausible-but-unregistered"])


@pytest.mark.parametrize(
    "assessment",
    [
        {"unregistered_dimension": "high"},
        {"autonomy": "approximately-controlled"},
    ],
)
def test_classify_rejects_unknown_assessment_keys_and_values(assessment):
    with pytest.raises(ValueError, match="assessment"):
        classify([], assessment=assessment)


def test_classify_rejects_unknown_uncertainty():
    with pytest.raises(ValueError, match="uncertainty"):
        classify([], uncertainty="sometimes")


def test_tier_classification_to_dict():
    tc = TierClassification(tier="T2", modifiers=["A"])
    d = tc.to_dict()
    assert d["tier"] == "T2"
    assert "A" in d["modifiers"]


# --- classification receipt ---------------------------------------------


def test_build_receipt_is_sealed():
    r = build_classification_receipt(
        tier="T2", modifiers=["A", "D"], system_id="eval-001",
        consequence_analysis="agent with privileged tools",
        approving_authorities=["alice", "bob"])
    assert r["schema"] == SCHEMA
    assert len(r["seal_hash"]) == 64
    assert r["classification_id"] == r["seal_hash"]
    assert r["seal_body"]["tier"] == "T2"
    assert "alice" in r["seal_body"]["approving_authorities"]


def test_verify_receipt_match():
    r = build_classification_receipt(
        tier="T1", modifiers=[], system_id="test",
        consequence_analysis="bounded risk")
    v = verify_classification_receipt(r)
    assert v["verdict"] == MATCH
    assert v["tier"] == "T1"


def test_verify_receipt_tampered():
    r = build_classification_receipt(
        tier="T2", modifiers=["A"], system_id="test",
        consequence_analysis="original")
    r["seal_body"]["consequence_analysis"] = "tampered"
    v = verify_classification_receipt(r)
    assert v["verdict"] == TAMPERED


def test_verify_receipt_bad_schema():
    v = verify_classification_receipt({"schema": "wrong"})
    assert v["verdict"] == UNVERIFIABLE


def test_verify_receipt_id_mismatch():
    r = build_classification_receipt(
        tier="T1", modifiers=[], system_id="test",
        consequence_analysis="x")
    r["classification_id"] = "0" * 64
    v = verify_classification_receipt(r)
    assert v["verdict"] == UNVERIFIABLE


def test_verify_receipt_rejects_resealed_open_classification_value():
    receipt = build_classification_receipt(
        tier="T1", modifiers=[], system_id="test",
        consequence_analysis="bounded")
    receipt["seal_body"]["uncertainty"] = "sometimes"
    canonical = json.dumps(
        receipt["seal_body"], separators=(",", ":"), ensure_ascii=False)
    receipt["seal_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    receipt["classification_id"] = receipt["seal_hash"]
    assert verify_classification_receipt(receipt)["verdict"] == UNVERIFIABLE


def test_build_receipt_rejects_invalid_tier():
    with pytest.raises(ValueError, match="invalid tier"):
        build_classification_receipt(
            tier="T4", modifiers=[], system_id="x",
            consequence_analysis="x")


def test_build_receipt_rejects_invalid_status():
    with pytest.raises(ValueError, match="invalid status"):
        build_classification_receipt(
            tier="T1", modifiers=[], system_id="x",
            consequence_analysis="x", status="bogus")


@pytest.mark.parametrize(
    ("field", "value"),
    [("uncertainty", "sometimes"), ("evidence_quality", "adequate-ish")],
)
def test_build_receipt_rejects_open_classification_values(field, value):
    kwargs = {field: value}
    with pytest.raises(ValueError, match=field):
        build_classification_receipt(
            tier="T1", modifiers=[], system_id="x",
            consequence_analysis="x", **kwargs)


# --- control baseline ---------------------------------------------------


def test_t1_has_14_controls():
    assert len(T1_CONTROLS) == 14


def test_t2_adds_18():
    assert len(T2_CONTROLS) == 18


def test_t3_adds_20():
    assert len(T3_CONTROLS) == 20


def test_check_compliance_unobserved_controls_are_unknown():
    report = check_compliance("T1")
    assert report.tier == "T1"
    assert report.required == 14
    assert report.measured == 0
    assert report.present == 0
    assert report.absent == 0
    assert report.unknown == 14
    assert all(check.observation.state == "unknown" for check in report.checks)


def test_check_compliance_t2_requires_more():
    observation = control_baseline.ControlObservation(
        control_id="tadr:T1:named-owner", state="present",
        source_ref="receipt://owner/1", observed_at="2026-08-02T00:00:00Z",
        checker_id="owner-check/v1")
    report = check_compliance("T2", observations=[observation])
    assert report.required == 32
    assert report.measured == 1
    assert report.present == 1
    assert report.unknown == 31


def test_check_compliance_t3_checked_count():
    report = check_compliance("T3")
    assert report.required == 52


def test_compliance_report_to_dict():
    report = check_compliance("T1")
    d = report.to_dict()
    assert d["tier"] == "T1"
    assert "checks" in d
    assert "compliant" in d


def test_compliance_not_compliant_when_controls_missing():
    report = check_compliance("T1")
    assert report.compliant is False
    assert report.unknown > 0


def test_control_observation_requires_evidence_for_measured_state():
    with pytest.raises(ValueError, match="source_ref"):
        control_baseline.ControlObservation(
            control_id="tadr:T1:named-owner", state="present",
            source_ref="", observed_at="2026-08-02T00:00:00Z",
            checker_id="owner-check/v1")


def test_check_compliance_rejects_invalid_tier_and_control_id():
    with pytest.raises(ValueError, match="tier"):
        check_compliance("T9")
    observation = control_baseline.ControlObservation(
        control_id="tadr:T1:not-a-control", state="absent",
        source_ref="receipt://scan/1", observed_at="2026-08-02T00:00:00Z",
        checker_id="control-check/v1")
    with pytest.raises(ValueError, match="control_id"):
        check_compliance("T1", observations=[observation])


def test_control_receipt_seals_complete_observation_list():
    observations = [control_baseline.ControlObservation(
        control_id="tadr:T1:named-owner", state="present",
        source_ref="receipt://owner/1", observed_at="2026-08-02T00:00:00Z",
        checker_id="owner-check/v1").to_dict()]
    receipt = tadr_receipt.build_control_receipt(
        system_id="system-1", classification_ref="a" * 64, tier="T1",
        observations=observations, checked_at="2026-08-02T00:01:00Z",
        checker_id="baseline-check/v1")
    assert receipt["schema"] == "flywheel.tadr-control/v1"
    assert receipt["seal_hash"] != "0" * 64
    assert receipt["seal_body"]["observations"] == observations
    assert tadr_receipt.verify_control_receipt(receipt)["verdict"] == MATCH


def test_control_receipt_detects_tampering():
    receipt = tadr_receipt.build_control_receipt(
        system_id="system-1", classification_ref="a" * 64, tier="T1",
        observations=[], checked_at="2026-08-02T00:01:00Z",
        checker_id="baseline-check/v1")
    receipt["seal_body"]["tier"] = "T2"
    assert tadr_receipt.verify_control_receipt(receipt)["verdict"] == TAMPERED
