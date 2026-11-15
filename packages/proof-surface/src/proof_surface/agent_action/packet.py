"""Unified agent-action proof packet -- contract v0.

The 10-field "proof packet anatomy" in one validated object: claim, scope,
sources, context, actions, admission, side_effects, outputs, verdicts,
uncertainty. What makes it a *receipt* rather than a trace: every material
action must carry exactly one admission decision and one side-effect
classification, digests are re-derivable 64-hex, and the whole object inherits
the proof-surface family's two neutrality guards (no authorization-suppression
field names, no authority-shaped language) reused verbatim from siblings.

Stdlib-only, zero third-party dependencies.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .._decision import validate_decision_summary
from .._failure import validate_failure_labels
from .._validate import Issue, reject_unknown, require_const, require_enum, require_text

# Reuse the family's two neutrality guards verbatim -- one source of truth, so
# the new packet cannot regress the invariant the sibling contracts enforce.
from ..authorization_receipt import _reject_forbidden
from ..witness_receipt import _reject_authority_language
from .._compute_lease import validate_compute_lease
from ._consistency import validate_consistency
from ._evidence import validate_evidence_refs

PACKET_VERSION = "agent-action-proof-packet/v0"

OVERALL_VERDICTS = {"MATCH", "DRIFT", "UNVERIFIABLE"}
ADMISSION_DECISIONS = {"allow", "deny", "needs-human"}
SIDE_EFFECT_CLASSES = {"read", "write", "external", "irreversible"}

ROOT_FIELDS = {
    "version",
    "packet_id",
    "claim",
    "scope",
    "sources",
    "context",
    "actions",
    "admission",
    "side_effects",
    "outputs",
    "evidence_refs",
    "failure_labels",
    "verdicts",
    "uncertainty",
    "decision_summary",
}
SOURCE_FIELDS = {"ref", "sha256"}
ACTION_FIELDS = {
    "action_id",
    "actor",
    "agent",
    "model",
    "tool",
    "action_kind",
    "target",
    "cost",
    "span_digest",
}
COST_FIELDS = {"tokens", "wall_ms"}
ADMISSION_FIELDS = {"action_id", "decision", "reasons", "authorization_ref"}
SIDE_EFFECT_FIELDS = {
    "action_id",
    "class",
    "idempotency_key",
    "compensation",
    "before_digest",
    "after_digest",
    "compute_lease",
}
COMPENSATION_FIELDS = {"reversible", "rollback_ref"}
OUTPUT_FIELDS = {"name", "sha256"}
VERDICTS_FIELDS = {"overall", "per_action"}
PER_ACTION_FIELDS = {"action_id", "status"}

_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def load_packet(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def validate_agent_action_packet(data: dict[str, Any]) -> list[Issue]:
    """Validate an agent-action proof packet. Returns [] iff valid."""
    issues: list[Issue] = []
    _reject_forbidden(data, "$", issues)
    _reject_authority_language(data, "$", issues)
    reject_unknown(data, "$", ROOT_FIELDS, issues)
    require_const(data, "version", PACKET_VERSION, issues)
    require_text(data, "packet_id", issues)
    require_text(data, "claim", issues)
    require_text(data, "scope", issues)
    _validate_sources(data.get("sources"), issues)
    _validate_context(data.get("context"), issues)
    _validate_actions(data.get("actions"), issues)
    _validate_admission(data.get("admission"), issues)
    _validate_side_effects(data.get("side_effects"), issues)
    _validate_outputs(data.get("outputs"), issues)
    validate_evidence_refs(data.get("evidence_refs"), issues)
    validate_failure_labels(data.get("failure_labels"), issues)
    _validate_verdicts(data.get("verdicts"), issues)
    _validate_uncertainty(data.get("uncertainty"), issues)
    validate_consistency(data, issues)
    validate_decision_summary(
        data.get("decision_summary"), issues, "$.decision_summary"
    )
    return issues


def validate_agent_action_packet_file(path: Path) -> list[Issue]:
    try:
        return validate_agent_action_packet(load_packet(path))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        return [Issue("$", str(exc))]


# ---------------------------------------------------------------------------
# Field helpers
# ---------------------------------------------------------------------------


def _require_hex64(value: Any, path: str, issues: list[Issue]) -> None:
    if not isinstance(value, str) or not _HEX64.fullmatch(value):
        issues.append(Issue(path, "expected 64-char lowercase hex digest"))


def _require_opt_hex64(value: Any, path: str, issues: list[Issue]) -> None:
    """A digest that may be null (e.g. an external call has no state snapshot),
    but must be 64-hex when present."""
    if value is None:
        return
    _require_hex64(value, path, issues)


def _require_opt_text(value: Any, path: str, issues: list[Issue]) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        issues.append(Issue(path, "expected non-empty string or null"))


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
        _require_hex64(item.get("sha256"), f"{path}.sha256", issues)


def _validate_context(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(
            Issue("$.context", "expected object (workspace/tool-authority summary)")
        )


def _validate_cost(value: Any, path: str, issues: list[Issue]) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        issues.append(Issue(path, "expected object or null"))
        return
    reject_unknown(value, path, COST_FIELDS, issues)
    for field in COST_FIELDS:
        v = value.get(field)
        if v is not None and (isinstance(v, bool) or not isinstance(v, int)):
            issues.append(Issue(f"{path}.{field}", "expected integer or null"))


def _validate_actions(value: Any, issues: list[Issue]) -> None:
    for index, item in enumerate(_as_list(value, "$.actions", issues)):
        path = f"$.actions[{index}]"
        if not isinstance(item, dict):
            issues.append(Issue(path, "expected object"))
            continue
        reject_unknown(item, path, ACTION_FIELDS, issues)
        require_text(item, "action_id", issues, f"{path}.action_id")
        require_text(item, "tool", issues, f"{path}.tool")
        require_text(item, "action_kind", issues, f"{path}.action_kind")
        require_text(item, "target", issues, f"{path}.target")
        for field in ("actor", "agent", "model"):
            _require_opt_text(item.get(field), f"{path}.{field}", issues)
        _validate_cost(item.get("cost"), f"{path}.cost", issues)
        _require_hex64(item.get("span_digest"), f"{path}.span_digest", issues)


def _validate_admission(value: Any, issues: list[Issue]) -> None:
    for index, item in enumerate(_as_list(value, "$.admission", issues)):
        path = f"$.admission[{index}]"
        if not isinstance(item, dict):
            issues.append(Issue(path, "expected object"))
            continue
        reject_unknown(item, path, ADMISSION_FIELDS, issues)
        require_text(item, "action_id", issues, f"{path}.action_id")
        require_enum(item, "decision", ADMISSION_DECISIONS, issues, f"{path}.decision")
        _validate_str_list(item.get("reasons"), f"{path}.reasons", issues)
        require_text(item, "authorization_ref", issues, f"{path}.authorization_ref")


def _validate_side_effects(value: Any, issues: list[Issue]) -> None:
    for index, item in enumerate(_as_list(value, "$.side_effects", issues)):
        path = f"$.side_effects[{index}]"
        if not isinstance(item, dict):
            issues.append(Issue(path, "expected object"))
            continue
        reject_unknown(item, path, SIDE_EFFECT_FIELDS, issues)
        require_text(item, "action_id", issues, f"{path}.action_id")
        require_enum(item, "class", SIDE_EFFECT_CLASSES, issues, f"{path}.class")
        _require_hex64(item.get("idempotency_key"), f"{path}.idempotency_key", issues)
        _require_opt_hex64(item.get("before_digest"), f"{path}.before_digest", issues)
        _require_opt_hex64(item.get("after_digest"), f"{path}.after_digest", issues)
        _validate_compensation(item.get("compensation"), f"{path}.compensation", issues)
        validate_compute_lease(
            item.get("compute_lease"),
            item.get("class"),
            f"{path}.compute_lease",
            issues,
        )


def _validate_compensation(value: Any, path: str, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue(path, "expected object"))
        return
    reject_unknown(value, path, COMPENSATION_FIELDS, issues)
    if not isinstance(value.get("reversible"), bool):
        issues.append(Issue(f"{path}.reversible", "expected boolean"))
    _require_opt_text(value.get("rollback_ref"), f"{path}.rollback_ref", issues)


def _validate_outputs(value: Any, issues: list[Issue]) -> None:
    for index, item in enumerate(_as_list(value, "$.outputs", issues)):
        path = f"$.outputs[{index}]"
        if not isinstance(item, dict):
            issues.append(Issue(path, "expected object"))
            continue
        reject_unknown(item, path, OUTPUT_FIELDS, issues)
        require_text(item, "name", issues, f"{path}.name")
        _require_hex64(item.get("sha256"), f"{path}.sha256", issues)


def _validate_verdicts(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.verdicts", "expected object"))
        return
    reject_unknown(value, "$.verdicts", VERDICTS_FIELDS, issues)
    require_enum(value, "overall", OVERALL_VERDICTS, issues, "$.verdicts.overall")
    for index, item in enumerate(
        _as_list(value.get("per_action"), "$.verdicts.per_action", issues)
    ):
        path = f"$.verdicts.per_action[{index}]"
        if not isinstance(item, dict):
            issues.append(Issue(path, "expected object"))
            continue
        reject_unknown(item, path, PER_ACTION_FIELDS, issues)
        require_text(item, "action_id", issues, f"{path}.action_id")
        require_enum(item, "status", OVERALL_VERDICTS, issues, f"{path}.status")


def _validate_uncertainty(value: Any, issues: list[Issue]) -> None:
    _validate_str_list(value, "$.uncertainty", issues)


def _validate_str_list(value: Any, path: str, issues: list[Issue]) -> None:
    for index, item in enumerate(_as_list(value, path, issues)):
        if not isinstance(item, str) or not item.strip():
            issues.append(Issue(f"{path}[{index}]", "expected non-empty string"))
