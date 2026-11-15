"""Multi-branch solver comparison + dependency-boundary honesty.

Harvest of dogfood pass 0094 (consolidated QuantumOptimizationWorkflowReceipt).
Several solver branches are compared against the exact baseline; a branch whose
dependency is missing is marked NOT_EXECUTED_DEPENDENCY_MISSING -- a dependency
boundary, NOT implied coverage. The load-bearing honesty rule: a non-executed
branch may not claim an objective value.
"""

from __future__ import annotations

from typing import Any

from .._validate import Issue, reject_unknown, require_enum, require_text
from .._verdict import verdict_for_measurement
from ._encoding import CONSTRAINT_ENCODINGS, SURROGATE_ENCODINGS

BRANCH_STATUSES = {"COMPLETED", "NOT_RUN", "FAILED", "NOT_EXECUTED_DEPENDENCY_MISSING"}
BASELINE_MATCHES = {"MATCH", "DRIFT", "UNVERIFIABLE"}
BRANCH_FIELDS = {
    "branch_id",
    "method",
    "runtime",
    "status",
    "objective_value",
    "gap",
    "notes",
    "baseline_match",
    "constraint_encoding",
    "promotion_blocked",
    "counterexample_ref",
}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def derive_gap(branch: dict[str, Any], baseline: dict[str, Any]) -> Any:
    """The numeric distance from the exact baseline; None if the branch did not run."""
    if branch.get("status") != "COMPLETED":
        return None
    value = branch.get("objective_value")
    baseline_value = (
        baseline.get("objective_value") if isinstance(baseline, dict) else None
    )
    if not _is_number(value) or not _is_number(baseline_value):
        return None
    return abs(value - baseline_value)


def derive_baseline_match(
    branch: dict[str, Any], baseline: dict[str, Any], tolerance: Any
) -> str:
    """Score a completed branch against the exact baseline; else it claims nothing."""
    if branch.get("status") != "COMPLETED":
        return "UNVERIFIABLE"
    value = branch.get("objective_value")
    baseline_value = (
        baseline.get("objective_value") if isinstance(baseline, dict) else None
    )
    if (
        not _is_number(value)
        or not _is_number(baseline_value)
        or not _is_number(tolerance)
    ):
        return "UNVERIFIABLE"
    return verdict_for_measurement(
        abs(float(value) - float(baseline_value)), float(tolerance)
    )


def validate_solver_branches(
    value: Any, issues: list[Issue], path: str = "$.solver_branches"
) -> None:
    """Validate the optional solver_branches list. Absent or None is valid."""
    if value is None:
        return
    if not isinstance(value, list):
        issues.append(Issue(path, "expected array"))
        return
    for index, item in enumerate(value):
        branch_path = f"{path}[{index}]"
        if not isinstance(item, dict):
            issues.append(Issue(branch_path, "expected object"))
            continue
        reject_unknown(item, branch_path, BRANCH_FIELDS, issues)
        require_text(item, "branch_id", issues, f"{branch_path}.branch_id")
        require_text(item, "method", issues, f"{branch_path}.method")
        require_enum(item, "status", BRANCH_STATUSES, issues, f"{branch_path}.status")
        _validate_value(item, branch_path, issues)
        notes = item.get("notes")
        if notes is not None and (not isinstance(notes, str) or not notes.strip()):
            issues.append(
                Issue(f"{branch_path}.notes", "expected non-empty string or null")
            )
        match = item.get("baseline_match")
        if match is not None and match not in BASELINE_MATCHES:
            issues.append(
                Issue(
                    f"{branch_path}.baseline_match",
                    "expected MATCH / DRIFT / UNVERIFIABLE or null",
                )
            )
        runtime = item.get("runtime")
        if runtime is not None and (
            not isinstance(runtime, str) or not runtime.strip()
        ):
            issues.append(
                Issue(f"{branch_path}.runtime", "expected non-empty string or null")
            )
        _validate_gap(item, branch_path, issues)
        _validate_encoding_safety(item, branch_path, issues)


def _validate_encoding_safety(
    item: dict[str, Any], branch_path: str, issues: list[Issue]
) -> None:
    """Fixture-match is not encoding-soundness (pass 0103).

    A surrogate-encoded branch may match the fixture optimum, but its encoding is
    not a sound general reduction until proven -- so it must be promotion_blocked
    and cite the refuting counterexample.
    """
    encoding = item.get("constraint_encoding")
    if encoding is not None and encoding not in CONSTRAINT_ENCODINGS:
        issues.append(
            Issue(
                f"{branch_path}.constraint_encoding",
                f"expected one of {sorted(CONSTRAINT_ENCODINGS)} or null",
            )
        )
    blocked = item.get("promotion_blocked")
    if blocked is not None and not isinstance(blocked, bool):
        issues.append(Issue(f"{branch_path}.promotion_blocked", "expected boolean"))
    counterexample = item.get("counterexample_ref")
    if counterexample is not None and (
        not isinstance(counterexample, str) or not counterexample.strip()
    ):
        issues.append(
            Issue(
                f"{branch_path}.counterexample_ref", "expected non-empty string or null"
            )
        )
    if encoding in SURROGATE_ENCODINGS and blocked is not True:
        issues.append(
            Issue(
                f"{branch_path}.promotion_blocked",
                "a surrogate encoding that matches a fixture is still unsafe to promote "
                "generally; expected promotion_blocked=true (fixture-match is not "
                "encoding-soundness)",
            )
        )
    if blocked is True and not (
        isinstance(counterexample, str) and counterexample.strip()
    ):
        issues.append(
            Issue(
                f"{branch_path}.counterexample_ref",
                "a promotion_blocked branch must cite the refuting counterexample",
            )
        )


def _validate_gap(item: dict[str, Any], branch_path: str, issues: list[Issue]) -> None:
    gap = item.get("gap")
    if gap is None:
        return
    if item.get("status") != "COMPLETED":
        issues.append(
            Issue(
                f"{branch_path}.gap",
                "a non-executed branch must not claim a gap (dependency boundary, "
                "not implied coverage)",
            )
        )
        return
    if isinstance(gap, bool) or not isinstance(gap, (int, float)) or gap < 0:
        issues.append(Issue(f"{branch_path}.gap", "expected a non-negative number"))


def _validate_value(
    item: dict[str, Any], branch_path: str, issues: list[Issue]
) -> None:
    value = item.get("objective_value")
    if item.get("status") == "COMPLETED":
        if not _is_number(value):
            issues.append(
                Issue(
                    f"{branch_path}.objective_value",
                    "a COMPLETED branch must record a numeric objective_value",
                )
            )
    elif value is not None:
        issues.append(
            Issue(
                f"{branch_path}.objective_value",
                "a non-executed branch must not claim a value (dependency boundary, "
                "not implied coverage)",
            )
        )
