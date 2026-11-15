"""Tests for the model-eval proof packet validator (model-foundry / eval forge).

A model run + eval set + directional metrics + objective -> a re-derivable verdict
and a default-deny promotion decision: a model may be promoted only if the overall
verdict is MATCH.
"""

from __future__ import annotations

from proof_surface.model_eval import validate_model_eval_packet

_HEX = "a" * 64


def _valid() -> dict:
    return {
        "version": "model-eval-proof-packet/v0",
        "packet_id": "me-1",
        "claim": "claude-opus-4-8 passed the arithmetic eval and met the accuracy objective.",
        "scope": "One offline eval suite (500 items); promotion gated on accuracy.",
        "model": {"id": "claude-opus-4-8", "provider": "hosted", "config_hash": _HEX},
        "eval_set": {
            "name": "arithmetic-bench",
            "ref": "datasets/arith@v1",
            "sha256": _HEX,
            "size": 500,
        },
        "objective": {
            "name": "accuracy-gate",
            "summary": "promote iff accuracy >= 0.90",
        },
        "metrics": [
            {
                "metric": "accuracy",
                "value": 0.94,
                "target": 0.90,
                "direction": "maximize",
                "tolerance": 0.01,
                "deviation": 0.0,
                "unit": "ratio",
                "method": "exact-match",
                "evidence": [_HEX],
            }
        ],
        "decision": {"outcome": "promote", "reason": "accuracy 0.94 >= target 0.90"},
        "verdicts": {
            "overall": "MATCH",
            "per_metric": [{"metric": "accuracy", "status": "MATCH"}],
        },
        "uncertainty": [],
        "decision_summary": {
            "decision": "approve",
            "reason": "all metrics met their objectives",
            "confidence": "high",
            "missing_evidence": [],
            "next_action": "proceed",
        },
    }


def _paths(issues):
    return [i.path for i in issues]


def test_valid_packet_has_no_issues():
    assert validate_model_eval_packet(_valid()) == []


def test_unknown_root_field_rejected():
    d = _valid()
    d["extra"] = 1
    assert any("extra" in p for p in _paths(validate_model_eval_packet(d)))


def test_unknown_provider_rejected():
    d = _valid()
    d["model"]["provider"] = "magic"
    assert any("provider" in p for p in _paths(validate_model_eval_packet(d)))


def test_unknown_direction_rejected():
    d = _valid()
    d["metrics"][0]["direction"] = "sideways"
    assert any("direction" in p for p in _paths(validate_model_eval_packet(d)))


def test_non_positive_tolerance_rejected():
    d = _valid()
    d["metrics"][0]["tolerance"] = 0
    assert any("tolerance" in p for p in _paths(validate_model_eval_packet(d)))


def test_promote_requires_overall_match():
    d = _valid()
    d["verdicts"]["overall"] = "DRIFT"
    d["verdicts"]["per_metric"][0]["status"] = "DRIFT"
    # decision still says promote -> default-deny invariant violated
    issues = validate_model_eval_packet(d)
    assert any("decision" in i.path for i in issues)


def test_metric_without_verdict_flagged():
    d = _valid()
    d["verdicts"]["per_metric"] = []
    issues = validate_model_eval_packet(d)
    assert any("per_metric" in i.path and "accuracy" in i.message for i in issues)


def test_bad_config_hash_rejected():
    d = _valid()
    d["model"]["config_hash"] = "nope"
    assert any("config_hash" in p for p in _paths(validate_model_eval_packet(d)))


def test_authority_language_rejected():
    d = _valid()
    d["claim"] = "This model is CERTIFIED production-ready."
    assert validate_model_eval_packet(d) != []


def test_legacy_packet_without_replication_validates():
    d = _valid()
    assert "replication" not in d
    assert validate_model_eval_packet(d) == []


def test_two_match_instances_with_generalization_claim_validates():
    d = _valid()
    d["replication"] = {
        "instances": [
            {"instance_id": "eval-a", "verdict": "MATCH"},
            {
                "instance_id": "eval-b",
                "verdict": "MATCH",
                "warnings": ["seed differed"],
            },
        ],
        "generalization_claim": True,
    }
    assert validate_model_eval_packet(d) == []


def test_generalization_claim_with_one_instance_rejected():
    d = _valid()
    d["replication"] = {
        "instances": [{"instance_id": "eval-a", "verdict": "MATCH"}],
        "generalization_claim": True,
    }
    issues = validate_model_eval_packet(d)
    assert any("generalization_claim" in p for p in _paths(issues))


def test_generalization_claim_with_drift_instance_rejected():
    d = _valid()
    d["replication"] = {
        "instances": [
            {"instance_id": "eval-a", "verdict": "MATCH"},
            {"instance_id": "eval-b", "verdict": "DRIFT"},
        ],
        "generalization_claim": True,
    }
    assert any(
        "generalization_claim" in p for p in _paths(validate_model_eval_packet(d))
    )


def test_malformed_instance_verdict_enum_rejected():
    d = _valid()
    d["replication"] = {
        "instances": [{"instance_id": "eval-a", "verdict": "maybe"}],
        "generalization_claim": False,
    }
    assert any("verdict" in p for p in _paths(validate_model_eval_packet(d)))
