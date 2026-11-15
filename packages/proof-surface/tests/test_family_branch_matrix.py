"""Branch matrix: a fenced branch claims no verdict and is not citable support.

Shared-spine gate (src/proof_surface/_branches.py), grounded in the dogfood
branch precedent (solver branches on optimization_workflow, prover branches on
research_claim). A packet may declare its full branch matrix up front: every
branch is EXECUTED (and must record the verdict it earned) or UNAVAILABLE_FENCED
(and must carry probe evidence of the fence, never a verdict). A promotion or
summary surface that cites a fenced branch_id as support is rejected.
"""

from __future__ import annotations

from proof_surface.optimization_workflow import (
    build_optimization_workflow_packet,
    validate_optimization_workflow_packet,
)
from proof_surface.research_claim import (
    build_research_claim_packet,
    validate_research_claim_packet,
)

_HEX = "a" * 64

_EXECUTED = {"branch_id": "exact-0", "status": "EXECUTED", "verdict": "MATCH"}
_FENCED = {
    "branch_id": "dwave-sampler",
    "status": "UNAVAILABLE_FENCED",
    "probe_evidence": "import dwave.sampler failed: ModuleNotFoundError",
}


def _paths(issues):
    return [i.path for i in issues]


def _opt(declared_branches=None, claim="the solver matched the exact baseline"):
    packet = build_optimization_workflow_packet(
        sources=[{"ref": "run:opt", "sha256": _HEX}],
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
        solver={
            "branch_id": "exact-0",
            "method": "exact",
            "status": "COMPLETED",
            "objective_value": 162,
            "constraint_status": "satisfied",
            "tolerance": 0.5,
        },
        claim=claim,
        scope="s",
        packet_id="opt-bm",
    )
    if declared_branches is not None:
        packet["declared_branches"] = declared_branches
    return packet


def _rc(declared_branches=None, claim="the identity held under a bounded probe"):
    packet = build_research_claim_packet(
        statement="for all n >= 1, sum_{k=1}^n k = n(n+1)/2",
        sources=[{"ref": "probe log", "sha256": _HEX}],
        attempts=[{"attempt_id": "a1", "method": "numeric-probe", "result": "bounded"}],
        checks=[
            {"checker": "numeric-probe", "status": "pass", "evidence": ["n=1..1000"]}
        ],
        claim=claim,
        scope="bounded probe; not a general proof",
        packet_id="rc-bm",
    )
    if declared_branches is not None:
        packet["declared_branches"] = declared_branches
    return packet


_WEDGES = [
    ("optimization", validate_optimization_workflow_packet, _opt),
    ("research", validate_research_claim_packet, _rc),
]


def test_declared_branches_is_optional():
    for name, validate, make in _WEDGES:
        assert validate(make()) == [], name


def test_executed_and_fenced_matrix_validates():
    for name, validate, make in _WEDGES:
        packet = make(declared_branches=[dict(_EXECUTED), dict(_FENCED)])
        assert validate(packet) == [], name


def test_fenced_branch_with_verdict_rejected():
    # The load-bearing rule: a fenced branch making any verdict claim is rejected.
    for name, validate, make in _WEDGES:
        fenced = {**_FENCED, "verdict": "MATCH"}
        issues = validate(make(declared_branches=[fenced]))
        assert any("declared_branches[0].verdict" in p for p in _paths(issues)), name


def test_executed_branch_without_verdict_rejected():
    for name, validate, make in _WEDGES:
        executed = {"branch_id": "exact-0", "status": "EXECUTED"}
        issues = validate(make(declared_branches=[executed]))
        assert any("declared_branches[0].verdict" in p for p in _paths(issues)), name


def test_fenced_branch_without_probe_evidence_rejected():
    for name, validate, make in _WEDGES:
        fenced = {"branch_id": "dwave-sampler", "status": "UNAVAILABLE_FENCED"}
        issues = validate(make(declared_branches=[fenced]))
        assert any(
            "declared_branches[0].probe_evidence" in p for p in _paths(issues)
        ), name


def test_unknown_branch_status_rejected():
    for name, validate, make in _WEDGES:
        branch = {**_EXECUTED, "status": "SKIPPED_QUIETLY"}
        issues = validate(make(declared_branches=[branch]))
        assert any("declared_branches[0].status" in p for p in _paths(issues)), name


def test_unknown_branch_verdict_rejected():
    for name, validate, make in _WEDGES:
        branch = {**_EXECUTED, "verdict": "PROBABLY"}
        issues = validate(make(declared_branches=[branch]))
        assert any("declared_branches[0].verdict" in p for p in _paths(issues)), name


def test_unknown_branch_field_rejected():
    for name, validate, make in _WEDGES:
        branch = {**_EXECUTED, "vibes": True}
        issues = validate(make(declared_branches=[branch]))
        assert any("declared_branches[0].vibes" in p for p in _paths(issues)), name


def test_duplicate_branch_id_rejected():
    for name, validate, make in _WEDGES:
        issues = validate(make(declared_branches=[dict(_EXECUTED), dict(_EXECUTED)]))
        assert any("declared_branches[1].branch_id" in p for p in _paths(issues)), name


def test_claim_citing_fenced_branch_rejected():
    # A promotion/summary surface may not cite a fenced branch_id as support.
    for name, validate, make in _WEDGES:
        packet = make(
            declared_branches=[dict(_EXECUTED), dict(_FENCED)],
            claim="the dwave-sampler branch matched the exact baseline",
        )
        issues = validate(packet)
        assert any(p == "$.claim" for p in _paths(issues)), name


def test_summary_reason_citing_fenced_branch_rejected():
    for name, validate, make in _WEDGES:
        packet = make(declared_branches=[dict(_EXECUTED), dict(_FENCED)])
        packet["decision_summary"]["reason"] = (
            "dwave-sampler agreed with the exact baseline"
        )
        issues = validate(packet)
        assert any(p == "$.decision_summary.reason" for p in _paths(issues)), name


def test_claim_citing_executed_branch_validates():
    # Citing a branch that actually ran is fine; only the fence is uncitable.
    for name, validate, make in _WEDGES:
        packet = make(
            declared_branches=[dict(_EXECUTED), dict(_FENCED)],
            claim="branch exact-0 matched the exact baseline",
        )
        assert validate(packet) == [], name


def test_fenced_id_word_boundary_no_false_positive():
    # "exact-0" fenced must not fire on the unrelated word "exact-000x" etc.
    for name, validate, make in _WEDGES:
        fenced = {
            "branch_id": "or-tools",
            "status": "UNAVAILABLE_FENCED",
            "probe_evidence": "pip install ortools blocked by policy",
        }
        packet = make(
            declared_branches=[dict(_EXECUTED), fenced],
            claim="the or-tools-free exact enumeration matched the baseline",
        )
        assert validate(packet) == [], name


def test_builders_pass_declared_branches_through():
    opt = build_optimization_workflow_packet(
        sources=[{"ref": "run:opt", "sha256": _HEX}],
        problem={"sense": "maximize", "objective": "v", "constraints": []},
        baseline={
            "method": "exact",
            "objective_value": 1,
            "feasible": True,
            "candidate_digest": _HEX,
        },
        candidate_space={
            "variables": 1,
            "evaluated": 2,
            "feasible": 1,
            "infeasible": 1,
        },
        solver={
            "branch_id": "exact-0",
            "method": "exact",
            "status": "COMPLETED",
            "objective_value": 1,
            "constraint_status": "satisfied",
            "tolerance": 0.5,
        },
        claim="c",
        scope="s",
        packet_id="opt-b",
        declared_branches=[dict(_EXECUTED), dict(_FENCED)],
    )
    assert opt["declared_branches"] == [_EXECUTED, _FENCED]
    assert validate_optimization_workflow_packet(opt) == []

    rc = build_research_claim_packet(
        statement="s",
        sources=[{"ref": "r"}],
        attempts=[{"attempt_id": "a1", "method": "probe", "result": "bounded"}],
        checks=[{"checker": "probe", "status": "pass", "evidence": ["ok"]}],
        claim="c",
        scope="s",
        packet_id="rc-b",
        declared_branches=[dict(_EXECUTED), dict(_FENCED)],
    )
    assert rc["declared_branches"] == [_EXECUTED, _FENCED]
    assert validate_research_claim_packet(rc) == []
