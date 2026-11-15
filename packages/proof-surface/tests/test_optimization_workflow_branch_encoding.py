"""Per-branch encoding safety: fixture-match is not encoding-soundness.

Harvest of dogfood pass 0103 (Constraint-Encoding Receipt Adapter). A solver
branch can match one fixture optimum and still use an encoding that is unsafe to
promote generally (the Ocean/dimod equality-penalty BQM matched the exact
optimum but is refuted by the pass-0101 counterexample). So a surrogate-encoded
branch must be promotion_blocked with a counterexample_ref, even at baseline
MATCH -- separating "matched this fixture" from "sound general reduction".
"""

from __future__ import annotations

from proof_surface.optimization_workflow import (
    build_optimization_workflow_packet,
    validate_optimization_workflow_packet,
)

_HEX = "a" * 64

_SOLVER = {
    "branch_id": "exact-0",
    "method": "exact",
    "status": "COMPLETED",
    "objective_value": 162,
    "constraint_status": "satisfied",
    "tolerance": 0.5,
}


def _packet(branch_extra):
    branch = {
        "branch_id": "ocean_dimod_exact_bqm",
        "method": "simulated",
        "status": "COMPLETED",
        "objective_value": 162,
    }
    branch.update(branch_extra)
    return build_optimization_workflow_packet(
        sources=[{"ref": "dogfood:pass-0103", "sha256": _HEX}],
        problem={"sense": "maximize", "objective": "v", "constraints": ["w <= 29"]},
        baseline={
            "method": "exact",
            "objective_value": 162,
            "feasible": True,
            "candidate_digest": _HEX,
        },
        candidate_space={
            "variables": 12,
            "evaluated": 4096,
            "feasible": 2000,
            "infeasible": 2096,
        },
        solver=dict(_SOLVER),
        claim="branch encoding safety",
        scope="knapsack",
        packet_id="opt-enc-safety",
        solver_branches=[branch],
    )


def test_safe_encoding_branch_needs_no_block():
    packet = _packet({"constraint_encoding": "slack_variable"})
    assert validate_optimization_workflow_packet(packet) == []


def test_surrogate_branch_matching_baseline_but_blocked_validates():
    # The pass 0103 Ocean/dimod case: matched the optimum, promotion-blocked.
    packet = _packet(
        {
            "constraint_encoding": "equality_penalty",
            "promotion_blocked": True,
            "counterexample_ref": "pass-0101: values=[10,9] weights=[3,2] cap=4",
        }
    )
    assert validate_optimization_workflow_packet(packet) == []
    assert packet["solver_branches"][0]["baseline_match"] == "MATCH"


def test_surrogate_branch_without_block_is_rejected():
    # Fixture-match does not make an unsafe encoding promotable.
    packet = _packet({"constraint_encoding": "equality_penalty"})
    assert any(
        "solver_branches[0]" in i.path
        for i in validate_optimization_workflow_packet(packet)
    )


def test_promotion_blocked_without_counterexample_is_rejected():
    packet = _packet({"constraint_encoding": "penalty", "promotion_blocked": True})
    assert any(
        "counterexample_ref" in i.path
        for i in validate_optimization_workflow_packet(packet)
    )


def test_unknown_branch_encoding_is_rejected():
    packet = _packet({"constraint_encoding": "made_up"})
    assert any(
        i.path == "$.solver_branches[0].constraint_encoding"
        for i in validate_optimization_workflow_packet(packet)
    )


def test_encoding_fields_are_optional():
    packet = _packet({})
    assert validate_optimization_workflow_packet(packet) == []
