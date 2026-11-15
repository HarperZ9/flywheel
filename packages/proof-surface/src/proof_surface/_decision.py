"""Shared decision_summary contract for the proof-packet family.

Every packet must end in a decision the operator can act on today. The
decision_summary is derived from the overall MATCH/DRIFT/UNVERIFIABLE verdict and
validated with a closed vocabulary. Stdlib-only.
"""

from __future__ import annotations

from typing import Any

from ._validate import Issue, reject_unknown, require_enum, require_text

DECISION_OUTCOMES = {
    "approve",
    "block",
    "rerun",
    "escalate",
    "publish",
    "deploy",
    "archive",
}
CONFIDENCE = {"high", "moderate", "low"}
DECISION_SUMMARY_FIELDS = {
    "decision",
    "reason",
    "confidence",
    "missing_evidence",
    "next_action",
}

# overall verdict -> (decision, confidence, reason, next_action)
_DERIVED = {
    "MATCH": (
        "approve",
        "high",
        "the evidence matched every checked claim within tolerance",
        "proceed",
    ),
    "DRIFT": (
        "block",
        "high",
        "at least one checked claim drifted outside its tolerance",
        "investigate and remediate the drifted evidence before proceeding",
    ),
    "UNVERIFIABLE": (
        "escalate",
        "low",
        "at least one claim could not be verified from the available evidence",
        "supply the missing evidence, then re-verify",
    ),
}


def derive_decision_summary(
    overall: str, *, missing_evidence: list[str] | None = None
) -> dict[str, Any]:
    """Derive a decision_summary from the overall verdict (default-deny when unknown)."""
    decision, confidence, reason, next_action = _DERIVED.get(
        overall, _DERIVED["UNVERIFIABLE"]
    )
    return {
        "decision": decision,
        "reason": reason,
        "confidence": confidence,
        "missing_evidence": list(missing_evidence or []),
        "next_action": next_action,
    }


def render_decision_summary(ds: Any) -> list[str]:
    """Render a decision_summary as Markdown lines (shared across all reports)."""
    if not isinstance(ds, dict):
        return []
    lines = [
        "",
        "## Decision",
        "",
        f"**{str(ds.get('decision', '')).upper()}** "
        f"(confidence: {ds.get('confidence', '')}) -- {ds.get('reason', '')}",
        f"- **Next action:** {ds.get('next_action', '')}",
    ]
    missing = ds.get("missing_evidence") or []
    if missing:
        lines.append(f"- **Missing evidence:** {'; '.join(str(m) for m in missing)}")
    return lines


def validate_decision_summary(value: Any, issues: list[Issue], path: str) -> None:
    """Validate a decision_summary object, appending any issues."""
    if not isinstance(value, dict):
        issues.append(Issue(path, "expected object"))
        return
    reject_unknown(value, path, DECISION_SUMMARY_FIELDS, issues)
    require_enum(value, "decision", DECISION_OUTCOMES, issues, f"{path}.decision")
    require_text(value, "reason", issues, f"{path}.reason")
    require_enum(value, "confidence", CONFIDENCE, issues, f"{path}.confidence")
    require_text(value, "next_action", issues, f"{path}.next_action")
    missing = value.get("missing_evidence")
    if not isinstance(missing, list):
        issues.append(Issue(f"{path}.missing_evidence", "expected array"))
    else:
        for index, item in enumerate(missing):
            if not isinstance(item, str) or not item.strip():
                issues.append(
                    Issue(
                        f"{path}.missing_evidence[{index}]", "expected non-empty string"
                    )
                )
