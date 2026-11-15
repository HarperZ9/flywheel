"""Tests for the model-eval builder + crucible bridge (directional gating)."""

from __future__ import annotations

from proof_surface.model_eval import (
    build_model_eval_packet,
    to_crucible_inputs,
    validate_model_eval_packet,
)

_HEX = "a" * 64
_MODEL = {"id": "claude-opus-4-8", "provider": "hosted", "config_hash": _HEX}
_EVAL = {"name": "arithmetic-bench", "ref": "datasets/arith@v1", "size": 500}
_OBJ = {"name": "accuracy-gate", "summary": "promote iff accuracy >= 0.90"}


def _build(metric):
    return build_model_eval_packet(
        model=_MODEL,
        eval_set=_EVAL,
        objective=_OBJ,
        metrics=[metric],
        claim="model evaluated against the gate",
        scope="offline eval; default-deny promotion",
        packet_id="me-1",
    )


def test_passing_maximize_metric_promotes():
    p = _build(
        {
            "metric": "accuracy",
            "value": 0.94,
            "target": 0.90,
            "direction": "maximize",
            "tolerance": 0.01,
            "unit": "ratio",
            "method": "exact-match",
            "evidence": [_HEX],
        }
    )
    assert validate_model_eval_packet(p) == []
    assert p["metrics"][0]["deviation"] == 0.0
    assert p["verdicts"]["overall"] == "MATCH"
    assert p["decision"]["outcome"] == "promote"


def test_failing_maximize_metric_rejects():
    p = _build(
        {
            "metric": "accuracy",
            "value": 0.80,
            "target": 0.90,
            "direction": "maximize",
            "tolerance": 0.01,
            "method": "exact-match",
            "evidence": [_HEX],
        }
    )
    assert validate_model_eval_packet(p) == []
    assert p["verdicts"]["overall"] == "DRIFT"
    assert p["decision"]["outcome"] == "reject"


def test_minimize_metric_within_target_is_match():
    p = _build(
        {
            "metric": "p95_latency_ms",
            "value": 90,
            "target": 100,
            "direction": "minimize",
            "tolerance": 5,
            "unit": "ms",
            "method": "timer",
            "evidence": [_HEX],
        }
    )
    assert p["verdicts"]["per_metric"][0]["status"] == "MATCH"
    assert p["decision"]["outcome"] == "promote"


def test_to_crucible_inputs_is_the_documented_contract():
    p = _build(
        {
            "metric": "accuracy",
            "value": 0.94,
            "target": 0.90,
            "direction": "maximize",
            "tolerance": 0.01,
            "method": "exact-match",
            "evidence": [_HEX],
        }
    )
    thesis, measurements = to_crucible_inputs(p)
    claim = thesis["claims"][0]
    assert claim["text"] and claim["falsification"]
    row = measurements["measurements"][0]
    assert row["claim"] == claim["text"]
    assert row["deviation"] == 0.0
    assert row["tolerance"] == 0.01
