"""Work-record receipt: a verifiable record of agent work that flows OUTWARD.

The structural inverse of an authorization-suppression "prefire" capsule. A work
record describes intent, inputs, actions, evidence, outcome, and cost as a
reviewer-facing artifact. It is hard-pinned so it can never drift into a prefire:

  * additionalProperties:false at every object level (via reject_unknown).
  * an explicit forbidden-field-NAME guard, applied recursively, rejecting the
    prefire capsule/meta keys by name (none contains a token the lexical authority
    denylist matches, so they must be blocked structurally).
  * decision-bearing fields are closed enums.
  * a required direction:"output-only" marker -- emitted outward, never read back
    in as model/session bootstrap state.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ._validate import Issue, reject_unknown, require_const, require_enum, require_text

WORK_RECORD_VERSION = "0.1"
RECORD_DIRECTION = "output-only"

OUTCOMES = {"completed", "partial", "abandoned", "blocked"}
EVIDENCE_VERDICTS = {"MATCH", "DRIFT", "UNVERIFIABLE"}

ROOT_FIELDS = {
    "work_record_version",
    "record_id",
    "direction",
    "intent",
    "inputs",
    "actions",
    "evidence",
    "outcome",
    "cost",
    "notes",
}
INPUT_FIELDS = {"name", "sha256"}
EVIDENCE_FIELDS = {"source", "verdict", "detail"}
COST_FIELDS = {"tokens", "wall_ms"}

# Field NAMES lifted verbatim from the excluded warden-prefire capsule/meta. None
# contains a token the lexical authority denylist matches, so they are blocked
# here by name, at every object level, as a permanent fail-closed guard.
FORBIDDEN_FIELDS = {
    "federal_appointment",
    "oversight_principals",
    "operator_role",
    "judgment_owner",
    "proof_policy",
    "policy_boundary",
    "authorization_context_mode",
    "model_authorization_behavior",
    "guardrail_posture",
    "consume_verified_native_state",
    "lossy_neutral_embedded_state",
    "sovereignty_capsule",
    "self_applicable",
    "recursion_depth",
    "prefire",
    "run_state",
}

_SHA256_RE = re.compile(r"[0-9a-f]{64}")


def load_record(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def validate_work_record(data: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    _reject_forbidden(data, "$", issues)
    reject_unknown(data, "$", ROOT_FIELDS, issues)
    require_const(data, "work_record_version", WORK_RECORD_VERSION, issues)
    require_const(data, "direction", RECORD_DIRECTION, issues)
    require_text(data, "record_id", issues)
    require_text(data, "intent", issues)
    require_enum(data, "outcome", OUTCOMES, issues)
    _validate_inputs(data.get("inputs"), issues)
    _validate_actions(data.get("actions"), issues)
    _validate_evidence(data.get("evidence"), issues)
    _validate_cost(data.get("cost"), issues)
    _validate_notes(data.get("notes"), issues)
    return issues


def validate_work_record_file(path: Path) -> list[Issue]:
    try:
        return validate_work_record(load_record(path))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        return [Issue("$", str(exc))]


def _reject_forbidden(node: Any, path: str, issues: list[Issue]) -> None:
    if isinstance(node, dict):
        for key in sorted(node):
            child = f"{path}.{key}"
            if key in FORBIDDEN_FIELDS:
                issues.append(Issue(child, "forbidden authorization-suppression field"))
            _reject_forbidden(node[key], child, issues)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _reject_forbidden(item, f"{path}[{index}]", issues)


def _validate_inputs(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, list):
        issues.append(Issue("$.inputs", "expected array"))
        return
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            issues.append(Issue(f"$.inputs[{index}]", "expected object"))
            continue
        reject_unknown(item, f"$.inputs[{index}]", INPUT_FIELDS, issues)
        require_text(item, "name", issues, f"$.inputs[{index}].name")
        sha = item.get("sha256")
        if not isinstance(sha, str) or not _SHA256_RE.fullmatch(sha):
            issues.append(
                Issue(
                    f"$.inputs[{index}].sha256", "expected 64-char lowercase hex sha256"
                )
            )


def _validate_actions(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, list):
        issues.append(Issue("$.actions", "expected array"))
        return
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            issues.append(Issue(f"$.actions[{index}]", "expected non-empty string"))


def _validate_evidence(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, list):
        issues.append(Issue("$.evidence", "expected array"))
        return
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            issues.append(Issue(f"$.evidence[{index}]", "expected object"))
            continue
        reject_unknown(item, f"$.evidence[{index}]", EVIDENCE_FIELDS, issues)
        require_text(item, "source", issues, f"$.evidence[{index}].source")
        require_enum(
            item, "verdict", EVIDENCE_VERDICTS, issues, f"$.evidence[{index}].verdict"
        )


def _validate_cost(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.cost", "expected object"))
        return
    reject_unknown(value, "$.cost", COST_FIELDS, issues)
    for field in ("tokens", "wall_ms"):
        if field in value:
            v = value[field]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
                issues.append(Issue(f"$.cost.{field}", "expected non-negative number"))


def _validate_notes(value: Any, issues: list[Issue]) -> None:
    if value is not None and not isinstance(value, str):
        issues.append(Issue("$.notes", "expected string"))
