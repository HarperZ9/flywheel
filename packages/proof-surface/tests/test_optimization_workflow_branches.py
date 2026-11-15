"""Multi-branch solver comparison + dependency-boundary honesty.

Harvest of dogfood pass 0094 (consolidated QuantumOptimizationWorkflowReceipt):
compare several solver branches against the exact baseline, and mark a branch
whose dependency is missing as NOT_EXECUTED_DEPENDENCY_MISSING -- a dependency
boundary, NOT implied coverage. A non-executed branch may not claim a value.
"""

from __future__ import annotations

from proof_surface.optimization_workflow import (
    build_optimization_workflow_packet,
    validate_optimization_workflow_packet,
)

_HEX = "a" * 64

_PROBLEM = {
    "sense": "maximize",
    "objective": "sum(value_i * x_i)",
    "constraints": ["sum(weight_i * x_i) <= 29"],
    "encoding": "0/1 knapsack",
}
_BASELINE = {
    "method": "exact-enumeration",
    "objective_value": 162,
    "feasible": True,
    "candidate_digest": _HEX,
}
_SPACE = {"variables": 12, "evaluated": 4096, "feasible": 2000, "infeasible": 2096}
_SOLVER = {
    "branch_id": "exact-0",
    "method": "exact",
    "status": "COMPLETED",
    "objective_value": 162,
    "constraint_status": "satisfied",
    "tolerance": 0.5,
}


def _packet(solver_branches=None):
    return build_optimization_workflow_packet(
        sources=[{"ref": "dogfood:pass-0094", "sha256": _HEX}],
        problem=_PROBLEM,
        baseline=_BASELINE,
        candidate_space=_SPACE,
        solver=dict(_SOLVER),
        claim="branch comparison knapsack",
        scope="12-variable knapsack",
        packet_id="opt-branches",
        solver_branches=solver_branches,
    )


_EXECUTED = [
    {
        "branch_id": "scipy_dual_annealing",
        "method": "scipy",
        "status": "COMPLETED",
        "objective_value": 162,
    },
    {
        "branch_id": "networkx_dag",
        "method": "networkx",
        "status": "COMPLETED",
        "objective_value": 162,
    },
]
_MISSING = {
    "branch_id": "ortools_knapsack",
    "method": "ortools",
    "status": "NOT_EXECUTED_DEPENDENCY_MISSING",
    "objective_value": None,
    "notes": "dependency boundary, not implied coverage",
}


def test_executed_branches_get_a_derived_baseline_match():
    packet = _packet(_EXECUTED)
    assert validate_optimization_workflow_packet(packet) == []
    matches = {b["branch_id"]: b["baseline_match"] for b in packet["solver_branches"]}
    assert matches["scipy_dual_annealing"] == "MATCH"
    assert matches["networkx_dag"] == "MATCH"


def test_a_branch_below_baseline_beyond_tolerance_is_drift():
    packet = _packet(
        [
            {
                "branch_id": "greedy",
                "method": "greedy",
                "status": "COMPLETED",
                "objective_value": 150,
            }
        ]
    )
    assert packet["solver_branches"][0]["baseline_match"] == "DRIFT"


def test_dependency_missing_branch_validates_and_claims_nothing():
    packet = _packet([*_EXECUTED, dict(_MISSING)])
    assert validate_optimization_workflow_packet(packet) == []
    missing = packet["solver_branches"][-1]
    assert missing["status"] == "NOT_EXECUTED_DEPENDENCY_MISSING"
    assert missing["objective_value"] is None
    assert missing["baseline_match"] == "UNVERIFIABLE"


def test_dependency_missing_branch_claiming_a_value_is_rejected():
    # The whole point: a not-run branch must not imply coverage.
    forged = dict(_MISSING)
    forged["objective_value"] = 162
    packet = _packet([forged])
    assert any(
        "solver_branches" in i.path
        for i in validate_optimization_workflow_packet(packet)
    )


def test_completed_branch_without_a_value_is_rejected():
    packet = _packet(
        [
            {
                "branch_id": "x",
                "method": "scipy",
                "status": "COMPLETED",
                "objective_value": None,
            }
        ]
    )
    assert any(
        "solver_branches" in i.path
        for i in validate_optimization_workflow_packet(packet)
    )


def test_unknown_branch_status_is_rejected():
    packet = _packet(
        [{"branch_id": "x", "method": "scipy", "status": "MAYBE", "objective_value": 1}]
    )
    assert any(
        "solver_branches" in i.path
        for i in validate_optimization_workflow_packet(packet)
    )


def test_solver_branches_is_optional():
    assert validate_optimization_workflow_packet(_packet()) == []
    assert "solver_branches" not in _packet()
