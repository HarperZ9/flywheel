"""Optimization-workflow proof packet -- contract v0.

Harvest of dogfood pass 0085/0086 (QuantumOptimizationWorkflowReceipt/v1). Binds
a source, a problem equation (objective + constraints + optional encoding), an
enumerated/searched candidate space, an exact baseline optimum, a solver branch,
and a re-derivable MATCH/DRIFT/UNVERIFIABLE verdict -- the proof obligation that
the solver's best feasible objective matches the exact baseline. Quantum is only
the lead demo; the primitive is domain-general optimization.

Stdlib-only. Reuses the proof-surface family's neutrality guards verbatim.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .._branches import (
    promotion_summary_surfaces,
    reject_fenced_branch_citations,
    validate_declared_branches,
)
from .._decision import validate_decision_summary
from .._failure import validate_failure_labels
from .._validate import Issue, reject_unknown, require_const, require_enum, require_text
from ..authorization_receipt import _reject_forbidden
from ..witness_receipt import _reject_authority_language
from ._boundary_gate import validate_boundary
from ._branches import validate_solver_branches
from ._encoding import CONSTRAINT_ENCODINGS, SURROGATE_ENCODINGS

PACKET_VERSION = "optimization-workflow-proof-packet/v0"

OVERALL_VERDICTS = {"MATCH", "DRIFT", "UNVERIFIABLE"}
SENSES = {"maximize", "minimize"}
SOLVER_METHODS = {"exact", "simulated", "hardware", "heuristic"}
SOLVER_STATUSES = {"COMPLETED", "NOT_RUN", "FAILED"}
CONSTRAINT_STATUSES = {"satisfied", "violated", "unknown"}

ROOT_FIELDS = {
    "version",
    "packet_id",
    "claim",
    "scope",
    "sources",
    "problem",
    "candidate_space",
    "baseline",
    "solver",
    "solver_branches",
    "declared_branches",
    "boundary",
    "failure_labels",
    "verdicts",
    "uncertainty",
    "decision_summary",
}
SOURCE_FIELDS = {"ref", "sha256"}
PROBLEM_FIELDS = {"sense", "objective", "constraints", "encoding"}
SPACE_FIELDS = {"variables", "evaluated", "feasible", "infeasible"}
BASELINE_FIELDS = {"method", "objective_value", "feasible", "candidate_digest"}
SOLVER_FIELDS = {
    "branch_id",
    "method",
    "status",
    "objective_value",
    "constraint_status",
    "constraint_encoding",
    "tolerance",
    "selected",
}
VERDICTS_FIELDS = {"overall"}

_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def load_packet(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def validate_optimization_workflow_packet(data: dict[str, Any]) -> list[Issue]:
    """Validate an optimization-workflow proof packet. Returns [] iff valid."""
    issues: list[Issue] = []
    _reject_forbidden(data, "$", issues)
    _reject_authority_language(data, "$", issues)
    reject_unknown(data, "$", ROOT_FIELDS, issues)
    require_const(data, "version", PACKET_VERSION, issues)
    require_text(data, "packet_id", issues)
    require_text(data, "claim", issues)
    require_text(data, "scope", issues)
    _validate_sources(data.get("sources"), issues)
    _validate_problem(data.get("problem"), issues)
    _validate_candidate_space(data.get("candidate_space"), issues)
    _validate_baseline(data.get("baseline"), issues)
    _validate_solver(data.get("solver"), issues)
    validate_solver_branches(data.get("solver_branches"), issues)
    declared_branches = data.get("declared_branches")
    validate_declared_branches(declared_branches, issues)
    reject_fenced_branch_citations(
        declared_branches, promotion_summary_surfaces(data), issues
    )
    validate_boundary(data.get("boundary"), data.get("solver"), issues)
    _validate_verdicts(data.get("verdicts"), issues)
    _validate_str_list(data.get("uncertainty"), "$.uncertainty", issues)
    validate_failure_labels(data.get("failure_labels"), issues)
    validate_decision_summary(
        data.get("decision_summary"), issues, "$.decision_summary"
    )
    return issues


def validate_optimization_workflow_packet_file(path: Path) -> list[Issue]:
    try:
        return validate_optimization_workflow_packet(load_packet(path))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        return [Issue("$", str(exc))]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _require_number(
    value: Any, path: str, issues: list[Issue], *, positive=False
) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        issues.append(Issue(path, "expected number"))
        return
    if positive and not value > 0:
        issues.append(Issue(path, "expected number > 0"))


def _require_nonneg_int(value: Any, path: str, issues: list[Issue]) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        issues.append(Issue(path, "expected non-negative integer"))


def _as_list(value: Any, path: str, issues: list[Issue]) -> list[Any]:
    if not isinstance(value, list):
        issues.append(Issue(path, "expected array"))
        return []
    return value


def _validate_sources(value: Any, issues: list[Issue]) -> None:
    for index, item in enumerate(_as_list(value, "$.sources", issues)):
        path = f"$.sources[{index}]"
        if not isinstance(item, dict):
            issues.append(Issue(path, "expected object"))
            continue
        reject_unknown(item, path, SOURCE_FIELDS, issues)
        require_text(item, "ref", issues, f"{path}.ref")
        sha = item.get("sha256")
        if not isinstance(sha, str) or not _HEX64.fullmatch(sha):
            issues.append(
                Issue(f"{path}.sha256", "expected 64-char lowercase hex digest")
            )


def _validate_problem(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.problem", "expected object"))
        return
    reject_unknown(value, "$.problem", PROBLEM_FIELDS, issues)
    require_enum(value, "sense", SENSES, issues, "$.problem.sense")
    require_text(value, "objective", issues, "$.problem.objective")
    _validate_str_list(value.get("constraints"), "$.problem.constraints", issues)
    encoding = value.get("encoding")
    if encoding is not None and (not isinstance(encoding, str) or not encoding.strip()):
        issues.append(Issue("$.problem.encoding", "expected non-empty string or null"))


def _validate_candidate_space(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.candidate_space", "expected object"))
        return
    reject_unknown(value, "$.candidate_space", SPACE_FIELDS, issues)
    for field in SPACE_FIELDS:
        _require_nonneg_int(value.get(field), f"$.candidate_space.{field}", issues)
    feasible, infeasible, evaluated = (
        value.get("feasible"),
        value.get("infeasible"),
        value.get("evaluated"),
    )
    if all(
        isinstance(n, int) and not isinstance(n, bool)
        for n in (feasible, infeasible, evaluated)
    ):
        if feasible + infeasible != evaluated:
            issues.append(
                Issue(
                    "$.candidate_space",
                    "feasible + infeasible must equal evaluated",
                )
            )


def _validate_baseline(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.baseline", "expected object"))
        return
    reject_unknown(value, "$.baseline", BASELINE_FIELDS, issues)
    require_text(value, "method", issues, "$.baseline.method")
    _require_number(value.get("objective_value"), "$.baseline.objective_value", issues)
    if not isinstance(value.get("feasible"), bool):
        issues.append(Issue("$.baseline.feasible", "expected boolean"))
    digest = value.get("candidate_digest")
    if not isinstance(digest, str) or not _HEX64.fullmatch(digest):
        issues.append(
            Issue(
                "$.baseline.candidate_digest", "expected 64-char lowercase hex digest"
            )
        )


def _validate_solver(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.solver", "expected object"))
        return
    reject_unknown(value, "$.solver", SOLVER_FIELDS, issues)
    require_text(value, "branch_id", issues, "$.solver.branch_id")
    require_enum(value, "method", SOLVER_METHODS, issues, "$.solver.method")
    require_enum(value, "status", SOLVER_STATUSES, issues, "$.solver.status")
    require_enum(
        value,
        "constraint_status",
        CONSTRAINT_STATUSES,
        issues,
        "$.solver.constraint_status",
    )
    _require_number(value.get("tolerance"), "$.solver.tolerance", issues, positive=True)
    _validate_objective_value(value, issues)
    _validate_constraint_encoding(value, issues)
    if value.get("selected") is not None:
        _validate_str_list(value.get("selected"), "$.solver.selected", issues)


def _validate_constraint_encoding(solver: dict[str, Any], issues: list[Issue]) -> None:
    encoding = solver.get("constraint_encoding")
    if encoding is None:
        return
    if encoding not in CONSTRAINT_ENCODINGS:
        issues.append(
            Issue(
                "$.solver.constraint_encoding",
                f"expected one of {sorted(CONSTRAINT_ENCODINGS)} or null",
            )
        )
        return
    if (
        encoding in SURROGATE_ENCODINGS
        and solver.get("constraint_status") == "satisfied"
    ):
        issues.append(
            Issue(
                "$.solver.constraint_encoding",
                "a penalty/surrogate encoding may not self-certify constraint_status "
                "'satisfied' (an equality penalty can present an infeasible optimum as "
                "solved -- pass 0101); record 'unknown' unless feasibility was verified",
            )
        )


def _validate_objective_value(solver: dict[str, Any], issues: list[Issue]) -> None:
    value = solver.get("objective_value")
    if solver.get("status") == "COMPLETED":
        _require_number(value, "$.solver.objective_value", issues)
    elif value is not None:
        issues.append(
            Issue(
                "$.solver.objective_value",
                "expected null unless the solver branch is COMPLETED",
            )
        )


def _validate_verdicts(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.verdicts", "expected object"))
        return
    reject_unknown(value, "$.verdicts", VERDICTS_FIELDS, issues)
    require_enum(value, "overall", OVERALL_VERDICTS, issues, "$.verdicts.overall")


def _validate_str_list(value: Any, path: str, issues: list[Issue]) -> None:
    for index, item in enumerate(_as_list(value, path, issues)):
        if not isinstance(item, str) or not item.strip():
            issues.append(Issue(f"{path}[{index}]", "expected non-empty string"))
