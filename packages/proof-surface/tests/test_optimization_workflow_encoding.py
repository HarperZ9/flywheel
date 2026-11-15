"""Constraint encoding: a penalty surrogate can't self-certify feasibility.

Harvest of dogfood pass 0101 (Inequality-Safe BQM Receipt). A squared
equality-to-capacity penalty is NOT a valid encoding of a `<= capacity`
inequality: it returned an infeasible optimum (value 19, weight 5 > cap 4)
presented as solved, while a slack-variable encoding recovered the true feasible
optimum. So a penalty/surrogate encoding may not declare constraint_status
'satisfied' on its own.
"""

from __future__ import annotations

from proof_surface.optimization_workflow import (
    build_optimization_workflow_packet,
    validate_optimization_workflow_packet,
)

_HEX = "a" * 64


def _packet(*, encoding=None, constraint_status="satisfied"):
    solver = {
        "branch_id": "bqm-0",
        "method": "heuristic",
        "status": "COMPLETED",
        "objective_value": 10,
        "constraint_status": constraint_status,
        "tolerance": 0.5,
    }
    if encoding is not None:
        solver["constraint_encoding"] = encoding
    return build_optimization_workflow_packet(
        sources=[{"ref": "dogfood:pass-0101", "sha256": _HEX}],
        problem={"sense": "maximize", "objective": "v", "constraints": ["w <= 4"]},
        baseline={
            "method": "exact",
            "objective_value": 10,
            "feasible": True,
            "candidate_digest": _HEX,
        },
        candidate_space={
            "variables": 2,
            "evaluated": 4,
            "feasible": 2,
            "infeasible": 2,
        },
        solver=solver,
        claim="inequality knapsack",
        scope="2-var knapsack",
        packet_id="opt-enc",
    )


def test_slack_variable_encoding_may_certify_satisfied():
    packet = _packet(encoding="slack_variable", constraint_status="satisfied")
    assert validate_optimization_workflow_packet(packet) == []


def test_equality_penalty_certifying_satisfied_is_rejected():
    # The pass 0101 counterexample: an equality penalty can present an infeasible
    # optimum as solved, so it may not self-certify feasibility.
    packet = _packet(encoding="equality_penalty", constraint_status="satisfied")
    assert any(
        "constraint_encoding" in i.path
        for i in validate_optimization_workflow_packet(packet)
    )


def test_penalty_encoding_with_unknown_status_is_honest():
    packet = _packet(encoding="penalty", constraint_status="unknown")
    assert validate_optimization_workflow_packet(packet) == []


def test_unknown_encoding_is_rejected():
    packet = _packet(encoding="magic")
    assert any(
        i.path == "$.solver.constraint_encoding"
        for i in validate_optimization_workflow_packet(packet)
    )


def test_constraint_encoding_is_optional():
    assert validate_optimization_workflow_packet(_packet()) == []
