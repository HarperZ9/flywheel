"""Tests for hypothetical exploration and ground-return loop (harness/hypothetical_loop.py)."""
from __future__ import annotations

import pytest

from harness.hypothetical_loop import (
    HypotheticalBranch,
    open_counterfactual_pair,
    return_to_ground,
)
from harness.negative_cache import NegativeRecord, build_negative_cache


def test_open_counterfactual_pair_seals_both_postures():
    b_true, b_false = open_counterfactual_pair(
        base_id="hyp-01",
        domain="physics",
        premise="refractive index gradient induces acoustic phase metamer",
        relaxed_constraints=("uniform_medium",),
        true_predictions=("phase velocity tracks n(x)",),
        false_predictions=("no cross-medium correlation",),
    )
    assert b_true["status"] == "HYPOTHETICAL"
    assert b_false["status"] == "HYPOTHETICAL"
    assert b_true["posture"] == "as_if_true"
    assert b_false["posture"] == "as_if_false"
    assert b_true["branch_sha256"] != b_false["branch_sha256"]


def test_ground_return_crystallizes_refutes_and_leaves_undecided():
    b_true, b_false = open_counterfactual_pair(
        base_id="hyp-02",
        domain="biology",
        premise="cambial impedance tracks drought recovery before needle browning",
    )
    cryst = return_to_ground(
        b_true,
        evaluator=lambda b: {
            "verdict": "MATCH",
            "measurement_sha256": "a" * 64,
            "detail": "replicated across 18 conifers",
        },
    )
    assert cryst["status"] == "CRYSTALLIZED"
    assert cryst["new_negative_record"] is None

    cache = build_negative_cache([
        NegativeRecord(
            record_id="neg-prior",
            domain="biology",
            hypothesis="cambial impedance tracks drought recovery before needle browning",
            failure_mode="sensor drift in wet bark",
            parameters={},
            measurement_sha256="b" * 64,
        )
    ])
    refuted = return_to_ground(
        b_false,
        negative_cache=cache,
        evaluator=lambda b: {
            "verdict": "DRIFT",
            "measurement_sha256": "c" * 64,
            "detail": "null difference after bark-moisture control",
            "parameters": {"n": 18},
        },
    )
    assert refuted["status"] == "REFUTED"
    assert refuted["prior_negative_cache"] == "HIT"
    assert refuted["new_negative_record"] is not None

    undecided = return_to_ground(
        b_true,
        evaluator=lambda b: {"verdict": "UNVERIFIABLE", "measurement_sha256": "", "detail": "no assay yet"},
    )
    assert undecided["status"] == "UNDECIDED"
    assert undecided["new_negative_record"] is None


def test_rejects_unknown_posture():
    with pytest.raises(ValueError):
        HypotheticalBranch("id", "physics", "premise", "guessing").to_dict()
