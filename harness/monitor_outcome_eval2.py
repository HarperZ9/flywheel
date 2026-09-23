"""Read Control Tower eval2 monitor scores.

Shapes from control_tower/protocols/eval2/monitoring/monitor.py and posthoc.py
at the revision in `SOURCE_REVISION`:

- The sample score is keyed "monitor". A second direct `inspect score --action
  append` pass lands at "monitor-1", and so on, so every such key is read as a
  separate pass rather than the first one only.
- Its value is always a mapping keyed "<monitor>/<action>",
  "<monitor>/<draw>/<action>" (only when the monitor drew more than once) or
  "<monitor>/trajectory". Each member is a number or the string "unscored". It
  can be empty, and it leaves out drafts the protocol scored but never ran.
- metadata.scores lists every entry: action (null for a trajectory score),
  message_id, monitor, draw (counted from 1), value, explanation (the error
  text when unscored), and prompt and model, or function, and model_role.

An entry the mapping leaves out is a DRAFT: scored, never executed. Counting it
as an action would overstate what the monitor saw of the agent's real run and
could put two entries at one action index.
"""
from __future__ import annotations

import re
from typing import Any

from .monitor_outcome_states import (
    ABSENT,
    DRAFT,
    SCORED,
    UNSCORED,
    UNSUPPORTED,
    MonitorAdapterError,
    action,
    fold_status,
    is_number,
    pointer,
)

PASS_KEY = re.compile(r"monitor(?:-(\d+))?")
_ENTRY_FIELDS = ("action", "message_id", "monitor", "draw", "value", "explanation")


def pass_keys(scores: dict, declared: str | None) -> list[str]:
    """The declared key, or "monitor" and every "monitor-<n>" pass in order."""
    if declared is not None:
        return [declared]
    found = [key for key in scores if type(key) is str and PASS_KEY.fullmatch(key)]
    return sorted(found, key=lambda key: int(PASS_KEY.fullmatch(key).group(1) or -1))


def _member_status(member: object) -> str:
    if is_number(member):
        return SCORED
    if member == UNSCORED:
        return UNSCORED
    return UNSUPPORTED


def _mapping_keys(monitor: object, draw: object, index: object) -> list[str]:
    target = "trajectory" if index is None else str(index)
    return [f"{monitor}/{target}", f"{monitor}/{draw}/{target}"]


def _parse_key(key: str) -> tuple[str, Any, Any]:
    """(monitor, draw, action) from a mapping key; action None is a trajectory."""
    parts = key.rsplit("/", 2)
    if len(parts) == 3 and parts[1].isdigit():
        monitor, draw, target = parts[0], int(parts[1]), parts[2]
    else:
        monitor, target = key.rsplit("/", 1) if "/" in key else (key, "")
        draw = None
    index = None if target == "trajectory" else (int(target) if target.isdigit() else target)
    return monitor, draw, index


def _entries(metadata: object, index: int, key: str) -> list[dict] | None:
    if metadata is None:
        return None
    if type(metadata) is not dict:
        raise MonitorAdapterError(f"sample {index}: {key} metadata must be an object")
    entries = metadata.get("scores")
    if entries is None:
        return None
    if type(entries) is not list or any(type(e) is not dict for e in entries):
        raise MonitorAdapterError(f"sample {index}: {key} metadata.scores must be an array of objects")
    return entries


def _claims(entries: list[dict], mapping: dict,
            executed: set | None) -> tuple[dict[int, str | None], set[str]]:
    """Which mapping key each entry is the executed score for, if any.

    A resampled draft can carry the same monitor and action index as the step
    that ran, so a key match alone would count the draft. When several entries
    claim one key, the sample's transcript message ids decide; without them the
    tie is reported, never guessed. Returns each entry's claim and the set of
    contested keys, so a contested key is not also read as mapping-only.
    """
    by_key: dict[str, list[int]] = {}
    for position, raw in enumerate(entries):
        hits = [k for k in _mapping_keys(raw.get("monitor"), raw.get("draw"), raw.get("action"))
                if k in mapping]
        if hits:
            by_key.setdefault(hits[0], []).append(position)
    claims: dict[int, str | None] = {}
    contested: set[str] = set()
    for key, positions in by_key.items():
        if len(positions) == 1:
            claims[positions[0]] = key
            continue
        ran = [p for p in positions
               if executed is not None and entries[p].get("message_id") in executed]
        if len(ran) != 1:
            contested.add(key)
        for p in positions:
            claims[p] = key if ran == [p] else (None if len(ran) == 1 else "ambiguous")
    return claims, contested


def _read_pass(entry: object, index: int, key: str,
               executed: set | None) -> tuple[str, str | None, list]:
    if type(entry) is not dict:
        raise MonitorAdapterError(f"sample {index}: {key} must be an object")
    mapping = entry.get("value")
    if type(mapping) is not dict:
        # Control Tower always writes a mapping here, never a scalar or null.
        return UNSUPPORTED, "eval2 value is not a name/action mapping", []
    entries = _entries(entry.get("metadata"), index, key) or []
    claims, contested = _claims(entries, mapping, executed)
    actions, matched = [], set()
    for position, raw in enumerate(entries):
        claim = claims.get(position)
        detail = {k: v for k, v in raw.items() if k not in _ENTRY_FIELDS}
        common = dict(index=raw.get("action"), monitor=raw.get("monitor"),
                      kind="trajectory" if raw.get("action") is None else "action",
                      message_id=raw.get("message_id"), draw=raw.get("draw"),
                      source_value=raw.get("value"), detail=detail,
                      source_pointer=pointer(index, key, "metadata", "scores", position))
        if claim is None:
            actions.append(action(status=DRAFT, reason="scored but never executed; "
                                  "the summary mapping leaves it out", **common))
            continue
        if claim == "ambiguous":
            actions.append(action(status=UNSUPPORTED, reason="several entries claim one "
                                  "mapping key and the transcript cannot tell which ran",
                                  **common))
            continue
        matched.add(claim)
        member = mapping[claim]
        status = _member_status(member)
        reason = raw.get("explanation") if status == UNSCORED else None
        if status == SCORED and raw.get("value") != member:
            status, reason = UNSUPPORTED, "entry value and summary mapping disagree"
        actions.append(action(status=status, reason=reason, **common))
    matched.update(contested)
    for mapped in sorted(set(mapping) - matched):
        # An executed score with no entry beside it. Kept, never dropped.
        monitor, draw, target = _parse_key(mapped)
        actions.append(action(
            index=target, kind="trajectory" if target is None else "action",
            monitor=monitor, draw=draw, status=_member_status(mapping[mapped]),
            source_value=mapping[mapped], source_pointer=pointer(index, key, "value", mapped),
            reason="in the summary mapping with no metadata entry"))
    if not mapping:
        return UNSCORED, "empty mapping: no executed action was scored", actions
    ran_statuses = [a["status"] for a in actions if a["status"] != DRAFT]
    return fold_status(ran_statuses), None, actions


def read_eval2(scores: dict, index: int, declared: str | None,
               executed: set | None = None) -> dict[str, Any]:
    """`executed` is the set of message ids in the sample transcript, if any."""
    passes, actions, summary = [], [], {}
    for key in pass_keys(scores, declared):
        if key not in scores:
            passes.append({"key": key, "status": ABSENT, "reason": None})
            continue
        status, reason, found = _read_pass(scores[key], index, key, executed)
        for item in found:
            item["pass"] = key
        passes.append({"key": key, "status": status, "reason": reason})
        actions.extend(found)
        summary[key] = scores[key].get("value")
    return {
        "status": fold_status([p["status"] for p in passes]),
        "summary_value": summary or None,
        "passes": passes,
        "actions": actions,
        "source_pointer": pointer(index),
    }
