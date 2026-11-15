"""Cross-field consistency for the agent-action packet.

This is the invariant that makes the packet a *receipt* rather than a trace:
every material action must carry exactly one admission decision and one
side-effect classification, and no admission / side-effect / verdict entry may
reference an action that is not present.
"""

from __future__ import annotations

from typing import Any

from .._validate import Issue


def _action_ids(data: dict[str, Any]) -> set[str]:
    actions = data.get("actions")
    if not isinstance(actions, list):
        return set()
    return {
        a["action_id"]
        for a in actions
        if isinstance(a, dict) and isinstance(a.get("action_id"), str)
    }


def _entry_ids(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    return [e.get("action_id") for e in value if isinstance(e, dict)]


def validate_consistency(data: dict[str, Any], issues: list[Issue]) -> None:
    action_ids = _action_ids(data)
    admission_ids = _entry_ids(data.get("admission"))
    side_ids = _entry_ids(data.get("side_effects"))

    for aid in sorted(action_ids):
        _require_exactly_one(admission_ids, aid, "$.admission", "admission", issues)
        _require_exactly_one(side_ids, aid, "$.side_effects", "side-effect", issues)

    _reject_dangling(data.get("admission"), action_ids, "$.admission", issues)
    _reject_dangling(data.get("side_effects"), action_ids, "$.side_effects", issues)
    _reject_dangling(
        (data.get("verdicts") or {}).get("per_action")
        if isinstance(data.get("verdicts"), dict)
        else None,
        action_ids,
        "$.verdicts.per_action",
        issues,
    )
    _reject_identity_substitution(data, issues)


def _reject_identity_substitution(data: dict[str, Any], issues: list[Issue]) -> None:
    """A receipt is not a trace: packet_id may not be a span id or the trace id."""
    packet_id = data.get("packet_id")
    if not isinstance(packet_id, str) or not packet_id:
        return
    actions = data.get("actions")
    if isinstance(actions, list) and any(
        isinstance(a, dict) and a.get("action_id") == packet_id for a in actions
    ):
        issues.append(
            Issue(
                "$.packet_id",
                "receipt identity must not equal a span/action id (evidence is not a receipt)",
            )
        )
    sources = data.get("sources")
    if isinstance(sources, list) and any(
        isinstance(s, dict) and s.get("ref") == f"trace:{packet_id}" for s in sources
    ):
        issues.append(
            Issue(
                "$.packet_id",
                "receipt identity must not equal the trace id (a trace is evidence, not a receipt)",
            )
        )


def _require_exactly_one(
    ids: list[Any], aid: str, path: str, label: str, issues: list[Issue]
) -> None:
    count = ids.count(aid)
    if count == 0:
        issues.append(Issue(path, f"no {label} entry for action {aid!r}"))
    elif count > 1:
        issues.append(Issue(path, f"multiple {label} entries for action {aid!r}"))


def _reject_dangling(
    entries: Any, action_ids: set[str], path: str, issues: list[Issue]
) -> None:
    if not isinstance(entries, list):
        return
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        aid = entry.get("action_id")
        if aid is not None and aid not in action_ids:
            issues.append(
                Issue(
                    f"{path}[{index}].action_id", f"references unknown action {aid!r}"
                )
            )
