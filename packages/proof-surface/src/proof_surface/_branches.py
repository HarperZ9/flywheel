"""Shared branch-matrix contract: a fenced branch claims nothing.

A packet may declare its full branch matrix up front (the dogfood branch
precedent: solver branches on optimization_workflow, prover branches on
research_claim). Every declared branch is either EXECUTED, and must record the
verdict it earned, or UNAVAILABLE_FENCED, and must carry probe evidence of the
fence -- the observed failure that blocked execution. Two honesty rules are
load-bearing: a fenced branch may not claim a verdict, and a promotion/summary
surface may not cite a fenced branch_id as support. Optional and stdlib-only;
a packet without the field validates unchanged.
"""

from __future__ import annotations

import re
from typing import Any

from ._validate import Issue, reject_unknown, require_enum, require_text

DECLARED_BRANCH_STATUSES = {"EXECUTED", "UNAVAILABLE_FENCED"}
DECLARED_BRANCH_VERDICTS = {"MATCH", "DRIFT", "UNVERIFIABLE"}
DECLARED_BRANCH_FIELDS = {"branch_id", "status", "verdict", "probe_evidence"}


def validate_declared_branches(
    value: Any, issues: list[Issue], path: str = "$.declared_branches"
) -> None:
    """Validate the optional declared_branches list. Absent or None is valid."""
    if value is None:
        return
    if not isinstance(value, list):
        issues.append(Issue(path, "expected array"))
        return
    seen_ids: set[str] = set()
    for index, item in enumerate(value):
        branch_path = f"{path}[{index}]"
        if not isinstance(item, dict):
            issues.append(Issue(branch_path, "expected object"))
            continue
        reject_unknown(item, branch_path, DECLARED_BRANCH_FIELDS, issues)
        require_text(item, "branch_id", issues, f"{branch_path}.branch_id")
        require_enum(
            item, "status", DECLARED_BRANCH_STATUSES, issues, f"{branch_path}.status"
        )
        branch_id = item.get("branch_id")
        if isinstance(branch_id, str) and branch_id.strip():
            if branch_id in seen_ids:
                issues.append(Issue(f"{branch_path}.branch_id", "duplicate branch_id"))
            seen_ids.add(branch_id)
        _validate_branch_claims(item, branch_path, issues)


def _validate_branch_claims(
    item: dict[str, Any], branch_path: str, issues: list[Issue]
) -> None:
    """An executed branch owes a verdict; a fenced branch owes probe evidence."""
    status = item.get("status")
    verdict = item.get("verdict")
    evidence = item.get("probe_evidence")
    if status == "UNAVAILABLE_FENCED":
        if verdict is not None:
            issues.append(
                Issue(
                    f"{branch_path}.verdict",
                    "a fenced branch may not claim a verdict (the fence is a "
                    "boundary, not a result)",
                )
            )
        if not isinstance(evidence, str) or not evidence.strip():
            issues.append(
                Issue(
                    f"{branch_path}.probe_evidence",
                    "a fenced branch must carry probe evidence of the fence "
                    "(the observed failure that blocked execution)",
                )
            )
        return
    if status == "EXECUTED":
        if verdict not in DECLARED_BRANCH_VERDICTS:
            issues.append(
                Issue(
                    f"{branch_path}.verdict",
                    "an EXECUTED branch must record the verdict it earned "
                    "(MATCH / DRIFT / UNVERIFIABLE)",
                )
            )
        if evidence is not None and (
            not isinstance(evidence, str) or not evidence.strip()
        ):
            issues.append(
                Issue(
                    f"{branch_path}.probe_evidence",
                    "expected non-empty string or null",
                )
            )


def fenced_branch_ids(value: Any) -> list[str]:
    """The branch_ids declared UNAVAILABLE_FENCED (empty if the field is absent)."""
    if not isinstance(value, list):
        return []
    return [
        item["branch_id"]
        for item in value
        if isinstance(item, dict)
        and item.get("status") == "UNAVAILABLE_FENCED"
        and isinstance(item.get("branch_id"), str)
        and item["branch_id"].strip()
    ]


def promotion_summary_surfaces(data: dict[str, Any]) -> list[tuple[str, Any]]:
    """The packet surfaces where citing a fenced branch is an overclaim.

    The claim and the decision reason assert support; uncertainty,
    missing_evidence, and next_action remain free for honest disclosure of the
    fence itself.
    """
    summary = data.get("decision_summary")
    reason = summary.get("reason") if isinstance(summary, dict) else None
    return [
        ("$.claim", data.get("claim")),
        ("$.decision_summary.reason", reason),
    ]


def reject_fenced_branch_citations(
    value: Any, citations: list[tuple[str, Any]], issues: list[Issue]
) -> None:
    """Reject a promotion/summary surface that cites a fenced branch_id."""
    fenced = fenced_branch_ids(value)
    if not fenced:
        return
    for path, text in citations:
        if not isinstance(text, str):
            continue
        for branch_id in fenced:
            # An id token continues through word chars and hyphens, so
            # "or-tools" does not fire inside "or-tools-free".
            if re.search(rf"(?<![\w-]){re.escape(branch_id)}(?![\w-])", text):
                issues.append(
                    Issue(
                        path,
                        f"cites fenced branch {branch_id!r} as support -- a "
                        "branch that did not execute is not evidence",
                    )
                )
