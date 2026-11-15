"""Optimization-workflow wedge: a solver branch must match the exact baseline.

Harvest of dogfood pass 0085/0086 (QuantumOptimizationWorkflowReceipt/v1). The
receipt invariant a future D-Wave / simulator / QUBO adapter must satisfy:
source binding, problem equation, candidate space, solver branch, exact
baseline, verifier verdict, and honest hardware / advantage boundaries. Quantum
is only the lead demo -- the primitive is domain-general optimization.
"""

from __future__ import annotations

from proof_surface.optimization_workflow import (
    build_optimization_workflow_packet,
    to_crucible_inputs,
    validate_optimization_workflow_packet,
)

_HEX = "a" * 64

_PROBLEM = {
    "sense": "maximize",
    "objective": "sum(value_i * x_i)",
    "constraints": ["sum(resource_i * x_i) <= 10"],
    "encoding": "QUBO surrogate",
}
_BASELINE = {
    "method": "exact-enumeration",
    "objective_value": 36,
    "feasible": True,
    "candidate_digest": _HEX,
}
_SPACE = {"variables": 6, "evaluated": 64, "feasible": 30, "infeasible": 34}


def _solver(**over):
    base = {
        "branch_id": "exact-0",
        "method": "exact",
        "status": "COMPLETED",
        "objective_value": 36,
        "constraint_status": "satisfied",
        "tolerance": 0.5,
        "selected": ["C", "D", "E", "F"],
    }
    base.update(over)
    return base


def _packet(solver=None, boundary=None):
    return build_optimization_workflow_packet(
        sources=[{"ref": "dogfood:pass-0086", "sha256": _HEX}],
        problem=_PROBLEM,
        baseline=_BASELINE,
        candidate_space=_SPACE,
        solver=solver if solver is not None else _solver(),
        claim="the exact optimum is C,D,E,F at value 36",
        scope="6-variable bounded knapsack",
        packet_id="opt-1",
        boundary=boundary,
    )


def test_solver_matching_baseline_is_a_MATCH():
    packet = _packet()
    assert validate_optimization_workflow_packet(packet) == []
    assert packet["verdicts"]["overall"] == "MATCH"
    # honest default: no quantum/hardware claim on an exact toy solve
    assert packet["boundary"]["quantum_advantage_claim"] is False
    assert packet["boundary"]["hardware_execution_claim"] is False


def test_solver_below_baseline_beyond_tolerance_is_a_DRIFT():
    packet = _packet(_solver(objective_value=30, tolerance=0.5))
    assert packet["verdicts"]["overall"] == "DRIFT"
    assert validate_optimization_workflow_packet(packet) == []


def test_constraint_violation_is_a_DRIFT_even_if_value_matches():
    # An infeasible answer that happens to hit the objective is not a valid optimum.
    packet = _packet(_solver(objective_value=36, constraint_status="violated"))
    assert packet["verdicts"]["overall"] == "DRIFT"


def test_not_run_solver_is_UNVERIFIABLE():
    packet = _packet(_solver(status="NOT_RUN", objective_value=None))
    assert packet["verdicts"]["overall"] == "UNVERIFIABLE"
    assert validate_optimization_workflow_packet(packet) == []


def test_hardware_execution_claim_requires_a_completed_hardware_branch():
    # Claiming hardware execution on an exact/NOT_RUN branch is an overclaim.
    packet = _packet(
        boundary={"quantum_advantage_claim": False, "hardware_execution_claim": True}
    )
    assert any(
        "boundary" in i.path for i in validate_optimization_workflow_packet(packet)
    )


def test_quantum_advantage_claim_requires_hardware_execution():
    packet = _packet(
        solver=_solver(method="hardware", status="COMPLETED"),
        boundary={"quantum_advantage_claim": True, "hardware_execution_claim": False},
    )
    assert any(
        "boundary" in i.path for i in validate_optimization_workflow_packet(packet)
    )


def test_candidate_space_counts_must_reconcile():
    packet = _packet()
    packet["candidate_space"]["feasible"] = 29  # 29 + 34 != 64
    assert any(
        "candidate_space" in i.path
        for i in validate_optimization_workflow_packet(packet)
    )


def test_to_crucible_inputs_round_trips_the_proof_obligation():
    thesis, measurements = to_crucible_inputs(_packet())
    assert thesis["claims"]
    row = measurements["measurements"][0]
    assert row["deviation"] == 0
    assert row["tolerance"] == 0.5
