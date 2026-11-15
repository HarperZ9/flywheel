"""Proof-surface packet validator (contract v0.1).

A neutral evidence/index packet that producers emit and the proof-index consumes.
Consolidated single source of truth -- previously copy-pasted across
model-provenance-validator, public-surface-sweeper, and the proof-surface-report
adapter.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ._validate import Issue, reject_unknown, require_const, require_enum, require_text

PACKET_VERSION = "0.1"
PACKET_STATUSES = {"ready", "needs-polish", "blocked", "unknown"}
CHECK_STATUSES = {"pass", "warn", "fail", "unknown"}
ROOT_FIELDS = {
    "proof_surface_version",
    "packet_id",
    "surface",
    "status",
    "claims",
    "checks",
    "action_items",
}
CLAIM_FIELDS = {"claim", "evidence"}
CHECK_FIELDS = {"tool", "status", "summary"}


def load_packet(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def validate_packet(data: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    reject_unknown(data, "$", ROOT_FIELDS, issues)
    require_const(data, "proof_surface_version", PACKET_VERSION, issues)
    require_text(data, "packet_id", issues)
    require_text(data, "surface", issues)
    require_enum(data, "status", PACKET_STATUSES, issues)
    _validate_claims(data.get("claims"), issues)
    _validate_checks(data.get("checks"), issues)
    _validate_action_items(data.get("action_items"), issues)
    return issues


def validate_packet_file(path: Path) -> list[Issue]:
    try:
        return validate_packet(load_packet(path))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        return [Issue("$", str(exc))]


def format_validation(path: Path, issues: list[Issue]) -> str:
    if not issues:
        return f"{path}: valid"
    lines = [f"{path}: invalid"]
    lines.extend(f"  {issue.path}: {issue.message}" for issue in issues)
    return "\n".join(lines)


def _validate_claims(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, list):
        issues.append(Issue("$.claims", "expected array"))
        return
    if not value:
        issues.append(Issue("$.claims", "expected at least 1 item(s)"))
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            issues.append(Issue(f"$.claims[{index}]", "expected object"))
            continue
        reject_unknown(item, f"$.claims[{index}]", CLAIM_FIELDS, issues)
        require_text(item, "claim", issues, f"$.claims[{index}].claim")
        require_text(item, "evidence", issues, f"$.claims[{index}].evidence")


def _validate_checks(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, list):
        issues.append(Issue("$.checks", "expected array"))
        return
    if not value:
        issues.append(Issue("$.checks", "expected at least 1 item(s)"))
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            issues.append(Issue(f"$.checks[{index}]", "expected object"))
            continue
        reject_unknown(item, f"$.checks[{index}]", CHECK_FIELDS, issues)
        require_text(item, "tool", issues, f"$.checks[{index}].tool")
        require_enum(
            item, "status", CHECK_STATUSES, issues, f"$.checks[{index}].status"
        )
        require_text(item, "summary", issues, f"$.checks[{index}].summary")


def _validate_action_items(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, list):
        issues.append(Issue("$.action_items", "expected array"))
        return
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            issues.append(
                Issue(f"$.action_items[{index}]", "expected non-empty string")
            )
