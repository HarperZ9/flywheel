"""Branch runtime + gap: align solver_branches with the SolverBranchReceipt/v1 spine.

Harvest of dogfood pass 0098 (SolverBranchReceipt Interop Schema, an implemented
11-field artifact). Each branch records the execution `runtime` (python/scipy,
python/ortools, buildlang/buildc, ...) so heterogeneous solvers fit one object,
and the builder derives the numeric `gap` from the exact baseline. A non-executed
branch may claim neither.
"""

from __future__ import annotations

from proof_surface.optimization_workflow import (
    build_optimization_workflow_packet,
    validate_optimization_workflow_packet,
)

_HEX = "a" * 64

_BASELINE = {
    "method": "exact-enumeration",
    "objective_value": 162,
    "feasible": True,
    "candidate_digest": _HEX,
}
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
        sources=[{"ref": "dogfood:pass-0098", "sha256": _HEX}],
        problem={"sense": "maximize", "objective": "value", "constraints": ["w<=29"]},
        baseline=_BASELINE,
        candidate_space={
            "variables": 12,
            "evaluated": 4096,
            "feasible": 2000,
            "infeasible": 2096,
        },
        solver=dict(_SOLVER),
        claim="branch runtimes",
        scope="knapsack",
        packet_id="opt-runtime",
        solver_branches=solver_branches,
    )


def test_runtime_is_recorded_and_gap_is_derived():
    packet = _packet(
        [
            {
                "branch_id": "scipy",
                "method": "scipy",
                "runtime": "python/scipy",
                "status": "COMPLETED",
                "objective_value": 162,
            },
            {
                "branch_id": "greedy",
                "method": "greedy",
                "runtime": "buildlang/buildc",
                "status": "COMPLETED",
                "objective_value": 146,
            },
        ]
    )
    assert validate_optimization_workflow_packet(packet) == []
    by_id = {b["branch_id"]: b for b in packet["solver_branches"]}
    assert by_id["scipy"]["runtime"] == "python/scipy"
    assert by_id["scipy"]["gap"] == 0
    assert by_id["greedy"]["gap"] == 16  # |146 - 162|


def test_dependency_missing_branch_has_no_gap():
    packet = _packet(
        [
            {
                "branch_id": "ortools",
                "method": "ortools",
                "runtime": "python/ortools",
                "status": "NOT_EXECUTED_DEPENDENCY_MISSING",
                "objective_value": None,
            }
        ]
    )
    assert validate_optimization_workflow_packet(packet) == []
    assert packet["solver_branches"][0].get("gap") is None


def test_forged_gap_on_a_non_executed_branch_is_rejected():
    packet = _packet(
        [
            {
                "branch_id": "ortools",
                "method": "ortools",
                "status": "NOT_EXECUTED_DEPENDENCY_MISSING",
                "objective_value": None,
            }
        ]
    )
    packet["solver_branches"][0]["gap"] = 0
    assert any(
        "solver_branches" in i.path
        for i in validate_optimization_workflow_packet(packet)
    )


def test_runtime_must_be_a_nonempty_string():
    packet = _packet(
        [
            {
                "branch_id": "x",
                "method": "scipy",
                "runtime": "  ",
                "status": "COMPLETED",
                "objective_value": 162,
            }
        ]
    )
    assert any(
        "runtime" in i.path for i in validate_optimization_workflow_packet(packet)
    )


def test_runtime_and_gap_are_optional():
    packet = _packet(
        [
            {
                "branch_id": "x",
                "method": "scipy",
                "status": "COMPLETED",
                "objective_value": 162,
            }
        ]
    )
    assert validate_optimization_workflow_packet(packet) == []
