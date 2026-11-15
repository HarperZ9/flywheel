"""Tests for the shared N-instance replication gate (dogfood 0145).

Portable finding: a single-instance MATCH is never a generalization/scale claim.
A scale claim requires the SAME contract to replay across two or more independent
instances, all MATCH, with per-instance warnings preserved. The gate is a shared
helper reused verbatim by every wedge that carries a `replication` object.
"""

from __future__ import annotations

from proof_surface._replication import validate_replication
from proof_surface._validate import Issue


def _issues(value):
    issues: list[Issue] = []
    validate_replication(value, issues, "$.replication")
    return issues


def _paths(issues):
    return [i.path for i in issues]


def test_absent_replication_is_valid():
    assert _issues(None) == []


def test_two_match_instances_with_generalization_claim_is_valid():
    value = {
        "instances": [
            {"instance_id": "run-a", "verdict": "MATCH"},
            {"instance_id": "run-b", "verdict": "MATCH"},
        ],
        "generalization_claim": True,
    }
    assert _issues(value) == []


def test_generalization_claim_with_one_instance_is_rejected():
    value = {
        "instances": [{"instance_id": "run-a", "verdict": "MATCH"}],
        "generalization_claim": True,
    }
    assert any("generalization_claim" in p for p in _paths(_issues(value)))


def test_generalization_claim_with_drift_instance_is_rejected():
    value = {
        "instances": [
            {"instance_id": "run-a", "verdict": "MATCH"},
            {"instance_id": "run-b", "verdict": "DRIFT"},
        ],
        "generalization_claim": True,
    }
    issues = _issues(value)
    assert any("generalization_claim" in p for p in _paths(issues))


def test_generalization_claim_with_unverifiable_instance_is_rejected():
    value = {
        "instances": [
            {"instance_id": "run-a", "verdict": "MATCH"},
            {"instance_id": "run-b", "verdict": "UNVERIFIABLE"},
        ],
        "generalization_claim": True,
    }
    assert any("generalization_claim" in p for p in _paths(_issues(value)))


def test_malformed_instance_verdict_enum_is_rejected():
    value = {
        "instances": [
            {"instance_id": "run-a", "verdict": "MATCH"},
            {"instance_id": "run-b", "verdict": "maybe"},
        ],
        "generalization_claim": False,
    }
    assert any("verdict" in p for p in _paths(_issues(value)))


def test_single_instance_without_generalization_claim_is_valid():
    value = {
        "instances": [{"instance_id": "run-a", "verdict": "MATCH"}],
        "generalization_claim": False,
    }
    assert _issues(value) == []


def test_non_match_instance_without_generalization_claim_is_valid():
    # Honest single-instance drift is fine; only the scale claim is gated.
    value = {
        "instances": [{"instance_id": "run-a", "verdict": "DRIFT"}],
        "generalization_claim": False,
    }
    assert _issues(value) == []


def test_warnings_are_preserved_not_dropped():
    warnings = ["seed differed", "hardware differed"]
    value = {
        "instances": [
            {"instance_id": "run-a", "verdict": "MATCH", "warnings": list(warnings)},
            {"instance_id": "run-b", "verdict": "MATCH"},
        ],
        "generalization_claim": True,
    }
    assert _issues(value) == []
    # The validator never mutates the input; warnings stay intact.
    assert value["instances"][0]["warnings"] == warnings


def test_warnings_must_be_non_empty_strings():
    value = {
        "instances": [{"instance_id": "run-a", "verdict": "MATCH", "warnings": [""]}],
        "generalization_claim": False,
    }
    assert any("warnings" in p for p in _paths(_issues(value)))


def test_missing_instance_id_is_rejected():
    value = {
        "instances": [{"verdict": "MATCH"}],
        "generalization_claim": False,
    }
    assert any("instance_id" in p for p in _paths(_issues(value)))


def test_missing_generalization_claim_is_rejected():
    value = {"instances": [{"instance_id": "run-a", "verdict": "MATCH"}]}
    assert any("generalization_claim" in p for p in _paths(_issues(value)))


def test_empty_instances_list_is_rejected():
    value = {"instances": [], "generalization_claim": False}
    assert any("instances" in p for p in _paths(_issues(value)))


def test_unknown_instance_field_is_rejected():
    value = {
        "instances": [{"instance_id": "run-a", "verdict": "MATCH", "extra": 1}],
        "generalization_claim": False,
    }
    assert any("extra" in p for p in _paths(_issues(value)))


def test_unknown_replication_field_is_rejected():
    value = {
        "instances": [{"instance_id": "run-a", "verdict": "MATCH"}],
        "generalization_claim": False,
        "surprise": 1,
    }
    assert any("surprise" in p for p in _paths(_issues(value)))
