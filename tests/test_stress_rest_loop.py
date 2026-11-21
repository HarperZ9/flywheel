"""Tests for adaptive loop-depth and sleep consolidation (harness/stress_rest_loop.py)."""
from __future__ import annotations

import hashlib

import pytest

from harness.manifold_memory import (
    MANIFOLD_CIRCULAR,
    MANIFOLD_LINEAR,
    VERDICT_DRIFT,
    VERDICT_MATCH,
    VERDICT_UNVERIFIABLE,
    ManifoldRecord,
)
from harness.stress_rest_loop import (
    DECISION_ADMIT,
    DECISION_REJECT,
    LOOP_DEPTH_SCHEMA,
    SLEEP_PLAN_SCHEMA,
    allocate_loop_depth,
    plan_sleep_consolidation,
    verify_stress_rest_receipt,
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sample_records() -> tuple[list[ManifoldRecord], dict[str, str]]:
    records = [
        ManifoldRecord("m1", MANIFOLD_LINEAR, (0.0, 0.0), "verified correction 1", _sha("payload-1")),
        ManifoldRecord("m2", MANIFOLD_LINEAR, (1.0, 0.0), "verified correction 2", _sha("payload-2")),
        ManifoldRecord("m3", MANIFOLD_LINEAR, (2.0, 0.0), "verified correction 3", _sha("payload-3")),
    ]
    hashes = {
        "m1": _sha("payload-1"),
        "m2": _sha("payload-2"),
        "m3": _sha("payload-3"),
    }
    return records, hashes


def test_allocate_loop_depth_scales_monotonically_with_surprise():
    surprises = [0.0, 0.15, 0.4, 0.8, 1.5, 4.0]
    results = [allocate_loop_depth(s, min_depth=1, max_depth=8, budget_remaining=100) for s in surprises]

    assert results[0]["schema"] == LOOP_DEPTH_SCHEMA
    assert results[0]["allocated_depth"] == 1
    assert results[-1]["allocated_depth"] == 8

    for earlier, later in zip(results, results[1:]):
        assert later["continuous_depth"] > earlier["continuous_depth"]
        assert later["allocated_depth"] >= earlier["allocated_depth"]
        assert earlier["budget_capped"] is False
        assert verify_stress_rest_receipt(earlier) is True
    assert verify_stress_rest_receipt(results[-1]) is True


def test_allocate_loop_depth_enforces_hard_compute_budget():
    capped = allocate_loop_depth(3.0, min_depth=1, max_depth=8, budget_remaining=3)
    assert capped["requested_depth"] == 8
    assert capped["allocated_depth"] == 3
    assert capped["budget_capped"] is True
    assert capped["budget_after"] == 0
    assert verify_stress_rest_receipt(capped) is True

    exhausted = allocate_loop_depth(1.0, min_depth=1, max_depth=8, budget_remaining=0)
    assert exhausted["allocated_depth"] == 0
    assert exhausted["budget_capped"] is True
    assert exhausted["budget_after"] == 0


def test_allocate_loop_depth_validation():
    for bad_s in (-0.1, float("nan"), float("inf"), True):
        with pytest.raises(ValueError, match="surprise"):
            allocate_loop_depth(bad_s)
    with pytest.raises(ValueError, match="min_depth"):
        allocate_loop_depth(0.5, min_depth=0)
    with pytest.raises(ValueError, match="max_depth"):
        allocate_loop_depth(0.5, min_depth=4, max_depth=2)
    with pytest.raises(ValueError, match="budget_remaining"):
        allocate_loop_depth(0.5, budget_remaining=-1)


def test_plan_sleep_consolidation_admits_on_match_and_non_regression():
    records, hashes = _sample_records()
    plan = plan_sleep_consolidation(
        records,
        baseline_score=0.82,
        candidate_score=0.87,
        source_hashes=hashes,
        budget_slots=16,
    )
    assert plan["schema"] == SLEEP_PLAN_SCHEMA
    assert plan["decision"] == DECISION_ADMIT
    assert plan["admitted"] is True
    assert plan["self_modified"] is False
    assert plan["provenance_verdict"] == VERDICT_MATCH
    assert plan["slot_count"] == 3
    assert plan["score_delta"] == pytest.approx(0.05)
    assert verify_stress_rest_receipt(plan) is True

    tie_plan = plan_sleep_consolidation(
        records,
        baseline_score=0.82,
        candidate_score=0.82,
        source_hashes=hashes,
        budget_slots=2,
    )
    assert tie_plan["decision"] == DECISION_ADMIT
    assert tie_plan["slot_count"] == 2
    assert tie_plan["self_modified"] is False


def test_plan_sleep_consolidation_rejects_on_provenance_drift_or_missing():
    records, hashes = _sample_records()
    drifted_hashes = dict(hashes)
    drifted_hashes["m2"] = _sha("tampered-payload")

    drift_plan = plan_sleep_consolidation(
        records,
        baseline_score=0.80,
        candidate_score=0.95,
        source_hashes=drifted_hashes,
    )
    assert drift_plan["decision"] == DECISION_REJECT
    assert drift_plan["admitted"] is False
    assert drift_plan["self_modified"] is False
    assert drift_plan["provenance_verdict"] == VERDICT_DRIFT
    assert verify_stress_rest_receipt(drift_plan) is True

    missing_plan = plan_sleep_consolidation(
        records,
        baseline_score=0.80,
        candidate_score=0.95,
        source_hashes={"m1": hashes["m1"]},
    )
    assert missing_plan["decision"] == DECISION_REJECT
    assert missing_plan["provenance_verdict"] == VERDICT_UNVERIFIABLE
    assert missing_plan["self_modified"] is False


def test_plan_sleep_consolidation_rejects_on_score_regression_and_detects_tamper():
    records = [
        ManifoldRecord("c1", MANIFOLD_CIRCULAR, (0.2,), "circular phase", _sha("c1")),
    ]
    plan = plan_sleep_consolidation(
        records,
        baseline_score=0.90,
        candidate_score=0.89,
        source_hashes={"c1": _sha("c1")},
    )
    assert plan["decision"] == DECISION_REJECT
    assert plan["admitted"] is False
    assert plan["self_modified"] is False
    assert plan["provenance_verdict"] == VERDICT_MATCH
    assert plan["score_delta"] == pytest.approx(-0.01)
    assert verify_stress_rest_receipt(plan) is True

    tampered = dict(plan)
    tampered["decision"] = DECISION_ADMIT
    assert verify_stress_rest_receipt(tampered) is False
