"""Read Control Tower eval1 monitor scores, current and legacy.

Shapes from control_tower/eval_logs/monitor_scores.py and
control_tower/trajectories/monitor_score.py at the revision in
`SOURCE_REVISION`. Both eval1 shapes use the score key `monitor_<name>` (bare
"monitor" only when the name is empty), so the key alone cannot tell them
apart. Control Tower tells them apart by value shape, and so does this:

- current: an action monitor's value maps action index to a number or null,
  and metadata.action_scores holds one Inspect Score dump per action, or null
  where no result exists. A failed or skipped-by-design score is a dump whose
  value is NOANSWER ("N") with metadata.error or skipped_by_design. A
  trajectory monitor's value is a number or "N", with no action_scores.
- legacy: a fold mapping {max, action_<i>, trajectory}. A mapping with any
  non-digit key is legacy (Control Tower's own is_legacy_score test).

Control Tower's sus_score also treats a numeric value as no score when
metadata.error is set or the value is negative. This reads it the same way.
"""
from __future__ import annotations

import re
from typing import Any

from .monitor_outcome_states import (
    ABSENT,
    NOANSWER,
    SCORED,
    UNSCORED,
    UNSUPPORTED,
    MonitorAdapterError,
    action,
    fold_status,
    is_number,
    pointer,
)

LEGACY_ACTION = re.compile(r"action_(\d+)")


def shape_of(entry: object) -> str | None:
    """"eval1", "eval1-legacy" or None, from a monitor score's value alone."""
    if type(entry) is not dict:
        return None
    value = entry.get("value")
    if type(value) is dict:
        return "eval1" if all(type(k) is str and k.isdigit() for k in value) else "eval1-legacy"
    if is_number(value) or value == NOANSWER:
        return "eval1"
    return None


def _dump_status(dump: dict) -> tuple[str, str | None]:
    value = dump.get("value")
    metadata = dump.get("metadata") if type(dump.get("metadata")) is dict else {}
    error = metadata.get("error")
    if value == NOANSWER:
        why = error or ("skipped by design" if metadata.get("skipped_by_design") else "no answer")
        return UNSCORED, str(why)
    if is_number(value):
        if error:
            return UNSCORED, str(error)
        if value < 0:
            return UNSCORED, "negative score, which Control Tower treats as no score"
        return SCORED, None
    return UNSUPPORTED, "action score value is neither a number nor NOANSWER"


def _action_monitor(value: dict, metadata: dict, index: int, key: str) -> list[dict]:
    dumps = metadata.get("action_scores")
    if dumps is not None and type(dumps) is not list:
        raise MonitorAdapterError(f"sample {index}: {key} metadata.action_scores must be an array")
    positions = sorted({int(k) for k in value} | set(range(len(dumps or []))))
    name = key[len("monitor_"):] if key.startswith("monitor_") else ""
    found = []
    for i in positions:
        mapped = value.get(str(i))
        dump = dumps[i] if dumps is not None and i < len(dumps) else None
        common = dict(index=i, kind="action", monitor=name)
        if dumps is None or i >= len(dumps):
            # Only the value mapping exists. Its null covers both "no result"
            # and "ran but no usable score", and nothing here tells them apart.
            status = SCORED if is_number(mapped) else UNSCORED
            reason = None if status == SCORED else "null in the value mapping with no action_scores entry"
            found.append(action(status=status, reason=reason, source_value=mapped,
                                source_pointer=pointer(index, key, "value", i), **common))
            continue
        where = pointer(index, key, "metadata", "action_scores", i)
        if dump is None:
            found.append(action(status=ABSENT, reason="no result recorded", source_value=None,
                                source_pointer=where, **common))
            continue
        if type(dump) is not dict:
            raise MonitorAdapterError(f"{where}: an action score must be an object or null")
        status, reason = _dump_status(dump)
        if status == SCORED and mapped != dump.get("value"):
            status, reason = UNSUPPORTED, "value mapping and action_scores disagree"
        dump_metadata = dump.get("metadata") if type(dump.get("metadata")) is dict else {}
        common["monitor"] = dump_metadata.get("monitor_name", name)
        found.append(action(status=status, reason=reason, source_value=dump.get("value"),
                            source_pointer=where, detail=dump_metadata, **common))
    return found


def read_eval1(scores: dict, index: int, key: str) -> dict[str, Any]:
    entry = scores.get(key)
    if entry is None:
        return {"status": ABSENT, "summary_value": None, "actions": [],
                "source_pointer": pointer(index, key)}
    if type(entry) is not dict:
        raise MonitorAdapterError(f"sample {index}: {key} must be an object")
    value = entry.get("value")
    metadata = entry.get("metadata") if type(entry.get("metadata")) is dict else {}
    if shape_of(entry) == "eval1-legacy":
        raise MonitorAdapterError(
            f"sample {index}: {key} is a legacy fold; declare adapter 'eval1-legacy'")
    if type(value) is dict:
        found = _action_monitor(value, metadata, index, key)
        status = fold_status([a["status"] for a in found]) if found else UNSCORED
    elif shape_of(entry) == "eval1":
        status, reason = _dump_status({"value": value, "metadata": metadata})
        found = [action(index=None, kind="trajectory", monitor=key[len("monitor_"):],
                        status=status, reason=reason, source_value=value,
                        source_pointer=pointer(index, key, "value"))]
    else:
        # Inspect admits None only inside a mapping, so Control Tower never
        # writes a top-level null or any other scalar here.
        status, found = UNSUPPORTED, []
    return {"status": status, "summary_value": value, "actions": found,
            "source_pointer": pointer(index, key)}


def read_eval1_legacy(scores: dict, index: int, key: str) -> dict[str, Any]:
    """A fold. Some folds indexed only monitor-visible actions, so the index
    here is the fold's own and may not be the executed-action index."""
    entry = scores.get(key)
    if entry is None:
        return {"status": ABSENT, "summary_value": None, "actions": [],
                "source_pointer": pointer(index, key)}
    if shape_of(entry) != "eval1-legacy":
        raise MonitorAdapterError(
            f"sample {index}: {key} is not a legacy fold; declare adapter 'eval1'")
    value = entry["value"]
    found = []
    for member in sorted(value, key=str):
        if member == "max":
            continue
        match = LEGACY_ACTION.fullmatch(str(member))
        raw = value[member]
        status = SCORED if is_number(raw) else (UNSCORED if raw is None else UNSUPPORTED)
        reason = None
        if not match and member != "trajectory":
            status, reason = UNSUPPORTED, "fold key outside {max, action_<i>, trajectory}"
        found.append(action(
            index=int(match.group(1)) if match else None,
            kind="action" if match else "trajectory", monitor=key[len("monitor_"):],
            status=status, reason=reason, source_value=raw,
            source_pointer=pointer(index, key, "value", member),
            detail={"index_basis": "fold"}))
    statuses = [a["status"] for a in found] + ([SCORED] if is_number(value.get("max")) else [])
    return {"status": fold_status(statuses), "summary_value": value, "actions": found,
            "source_pointer": pointer(index, key)}
