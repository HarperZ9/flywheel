"""Assemble an optimization-workflow packet and derive the proof-obligation verdict.

The obligation: the solver branch's best feasible objective matches the exact
baseline within tolerance. deviation = |solver_value - baseline_value|, scored by
the shared crucible-faithful rule. A constraint violation is a DRIFT regardless of
value (an infeasible answer is not a valid optimum); a non-COMPLETED branch is
UNVERIFIABLE. The boundary defaults to an honest no-quantum/no-hardware claim.
"""

from __future__ import annotations

from typing import Any

from .._decision import derive_decision_summary
from .._verdict import verdict_for_measurement
from ._branches import derive_baseline_match, derive_gap
from .packet import PACKET_VERSION


def _derive_verdict(solver: dict[str, Any], baseline: dict[str, Any]) -> str:
    if solver.get("status") != "COMPLETED":
        return "UNVERIFIABLE"
    if solver.get("constraint_status") == "violated":
        return "DRIFT"
    value = solver.get("objective_value")
    baseline_value = baseline.get("objective_value")
    tolerance = solver.get("tolerance")
    if (
        not _is_number(value)
        or not _is_number(baseline_value)
        or not _is_number(tolerance)
    ):
        return "UNVERIFIABLE"
    deviation = abs(float(value) - float(baseline_value))
    return verdict_for_measurement(deviation, float(tolerance))


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def build_optimization_workflow_packet(
    *,
    sources: list[dict[str, Any]],
    problem: dict[str, Any],
    baseline: dict[str, Any],
    candidate_space: dict[str, Any],
    solver: dict[str, Any],
    claim: str,
    scope: str,
    packet_id: str,
    boundary: dict[str, Any] | None = None,
    solver_branches: list[dict[str, Any]] | None = None,
    declared_branches: list[dict[str, Any]] | None = None,
    uncertainty: list[str] | None = None,
    failure_labels: list[str] | None = None,
) -> dict[str, Any]:
    overall = _derive_verdict(solver, baseline)
    tolerance = solver.get("tolerance")
    packet = {
        "version": PACKET_VERSION,
        "packet_id": packet_id,
        "claim": claim,
        "scope": scope,
        "sources": [dict(s) for s in sources],
        "problem": dict(problem),
        "candidate_space": dict(candidate_space),
        "baseline": dict(baseline),
        "solver": dict(solver),
        "boundary": dict(boundary)
        if boundary is not None
        else {"quantum_advantage_claim": False, "hardware_execution_claim": False},
        "verdicts": {"overall": overall},
        "uncertainty": list(uncertainty or []),
        "decision_summary": derive_decision_summary(overall),
    }
    if solver_branches is not None:
        packet["solver_branches"] = [
            _enrich_branch(b, baseline, tolerance) for b in solver_branches
        ]
    if declared_branches is not None:
        packet["declared_branches"] = [dict(b) for b in declared_branches]
    if failure_labels is not None:
        packet["failure_labels"] = list(failure_labels)
    return packet


def _enrich_branch(
    branch: dict[str, Any], baseline: dict[str, Any], tolerance: Any
) -> dict[str, Any]:
    enriched = {
        **dict(branch),
        "baseline_match": derive_baseline_match(branch, baseline, tolerance),
    }
    gap = derive_gap(branch, baseline)
    if gap is not None:
        enriched["gap"] = gap
    return enriched


def to_crucible_inputs(packet: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Emit crucible's (thesis, measurements) file contract for re-derivation."""
    solver = packet.get("solver", {}) or {}
    baseline = packet.get("baseline", {}) or {}
    value = solver.get("objective_value")
    baseline_value = baseline.get("objective_value")
    tolerance = solver.get("tolerance")
    deviation = (
        abs(float(value) - float(baseline_value))
        if _is_number(value) and _is_number(baseline_value)
        else None
    )
    text = (
        f"Solver branch {solver.get('branch_id')} ({solver.get('method')}) reached "
        f"objective {value}, matching the exact baseline {baseline_value} within "
        f"tolerance {tolerance}."
    )
    thesis = {
        "title": f"Optimization-workflow proof packet {packet.get('packet_id', '')}",
        "disposition": "publishable",
        "claims": [
            {
                "text": text,
                "falsification": (
                    "the solver's objective deviates beyond tolerance from the exact "
                    "baseline, or the returned assignment is infeasible."
                ),
            }
        ],
    }
    rows = [
        {
            "claim": text,
            "deviation": deviation,
            "tolerance": tolerance,
            "method": solver.get("method", "exact"),
            "evidence": [f"candidate_digest={baseline.get('candidate_digest', '')}"],
        }
    ]
    return thesis, {"measurements": rows}
