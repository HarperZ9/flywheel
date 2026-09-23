"""Read Control Tower monitor scores out of an Inspect log, by declared variant.

`harness.inspect_evidence` is the ingestion layer and is not changed by this
module. It was measured against the three documented Control Tower monitor
shapes on 2026-09-23 at source revision 91dfd406d, and it does not carry them:

- eval2: the mapping-valued `monitor` score survives, because `_score_value`
  accepts a flat dict. The per-action detail in `metadata.scores`, carrying
  `action`, `message_id`, `monitor`, `draw` and `value`, is dropped. Score
  metadata is listed in `redacted_fields` rather than preserved.
- current eval1: rejected outright with "score value has unsupported structure",
  because a skipped monitor score is `null` and `_score_value` does not accept
  `None` at the top level.
- legacy eval1: folded `monitor_<name>` values survive, but arrive as ordinary
  scorers. Nothing marks one as a monitor rather than a task grader.

So the monitor side is read here, from the same bytes the importer hashed, and
kept beside the importer's output rather than inside it.

Every adapter is explicit about its variant. An unrecognised shape is reported
as unsupported and never guessed at, because guessing between eval1 and eval2
would silently change what a score means.
"""
from __future__ import annotations

from typing import Any

# A monitor observation is in exactly one of these states. None of them is a
# number, and none of them may be compared against a threshold. "unscored" is
# Control Tower's own string for an action it declined to score; it is preserved
# as that string rather than mapped to null, so a reader can tell a declined
# score from an absent one.
SCORED = "scored"
UNSCORED = "unscored"
ABSENT = "absent"
UNSUPPORTED = "unsupported"

ADAPTERS = ("eval2", "eval1", "eval1-legacy")


class MonitorAdapterError(ValueError):
    """The log does not match the declared adapter."""


def _pointer(sample_index: int, *rest: object) -> str:
    tail = "".join(f"/{part}" for part in rest)
    return f"/samples/{sample_index}/scores{tail}"


def _action_entry(raw: object, pointer: str) -> dict[str, Any]:
    """One per-action monitor observation, with its source value untouched."""
    if type(raw) is not dict:
        raise MonitorAdapterError(f"{pointer}: action score entries must be objects")
    value = raw.get("value", None)
    if value is None:
        status = ABSENT
    elif value == UNSCORED:
        status = UNSCORED
    elif type(value) in (int, float):
        status = SCORED
    else:
        status = UNSUPPORTED
    return {
        "action": raw.get("action"),
        "message_id": raw.get("message_id"),
        "monitor": raw.get("monitor"),
        "draw": raw.get("draw"),
        "status": status,
        # The source value verbatim. A reader that wants a number must check
        # status first; there is deliberately no normalised numeric field.
        "source_value": value,
        "source_pointer": pointer,
    }


def _eval2(scores: dict, index: int, monitor_scorer: str) -> dict[str, Any]:
    entry = scores.get(monitor_scorer)
    if entry is None:
        return {"status": ABSENT, "summary_value": None, "actions": [],
                "source_pointer": _pointer(index, monitor_scorer)}
    if type(entry) is not dict:
        raise MonitorAdapterError(f"sample {index}: monitor score must be an object")
    summary = entry.get("value", None)
    metadata = entry.get("metadata")
    actions: list[dict[str, Any]] = []
    if type(metadata) is dict:
        raw_actions = metadata.get("scores")
        if raw_actions is not None:
            if type(raw_actions) is not list:
                raise MonitorAdapterError(
                    f"sample {index}: eval2 metadata.scores must be an array")
            actions = [
                _action_entry(item, _pointer(index, monitor_scorer, "metadata", "scores", i))
                for i, item in enumerate(raw_actions)
            ]
    elif metadata is not None:
        raise MonitorAdapterError(f"sample {index}: monitor metadata must be an object")
    status = SCORED if summary is not None else (ABSENT if not actions else SCORED)
    return {"status": status, "summary_value": summary, "actions": actions,
            "source_pointer": _pointer(index, monitor_scorer)}


def _eval1(scores: dict, index: int, monitor_scorer: str) -> dict[str, Any]:
    entry = scores.get(monitor_scorer)
    if entry is None:
        return {"status": ABSENT, "summary_value": None, "actions": [],
                "source_pointer": _pointer(index, monitor_scorer)}
    if type(entry) is not dict:
        raise MonitorAdapterError(f"sample {index}: monitor score must be an object")
    summary = entry.get("value", None)
    metadata = entry.get("metadata")
    actions: list[dict[str, Any]] = []
    if type(metadata) is dict:
        raw_actions = metadata.get("action_scores")
        if raw_actions is not None:
            if type(raw_actions) is not list:
                raise MonitorAdapterError(
                    f"sample {index}: eval1 metadata.action_scores must be an array")
            for i, item in enumerate(raw_actions):
                pointer = _pointer(index, monitor_scorer, "metadata", "action_scores", i)
                # Current eval1 writes a bare None for a skipped or failed score,
                # not an object and not a zero.
                if item is None:
                    actions.append({"action": i, "message_id": None, "monitor": None,
                                    "draw": None, "status": ABSENT,
                                    "source_value": None, "source_pointer": pointer})
                elif type(item) in (int, float):
                    actions.append({"action": i, "message_id": None, "monitor": None,
                                    "draw": None, "status": SCORED,
                                    "source_value": item, "source_pointer": pointer})
                else:
                    actions.append(_action_entry(item, pointer))
    elif metadata is not None:
        raise MonitorAdapterError(f"sample {index}: monitor metadata must be an object")
    if summary is None and not actions:
        status = ABSENT
    elif summary is None:
        # The monitor ran per action but reported no sample-level summary. That
        # is not a zero and not an absence.
        status = UNSCORED
    else:
        status = SCORED
    return {"status": status, "summary_value": summary, "actions": actions,
            "source_pointer": _pointer(index, monitor_scorer)}


def _eval1_legacy(scores: dict, index: int, monitor_scorer: str) -> dict[str, Any]:
    """Folded `monitor_<name>` keys, one scorer per monitor."""
    folded = {
        name: entry for name, entry in scores.items()
        if type(name) is str and name.startswith("monitor_")
    }
    if not folded:
        return {"status": ABSENT, "summary_value": None, "actions": [],
                "source_pointer": _pointer(index)}
    actions = []
    for name in sorted(folded):
        entry = folded[name]
        pointer = _pointer(index, name, "value")
        if type(entry) is not dict:
            raise MonitorAdapterError(f"sample {index}: {name} must be an object")
        value = entry.get("value", None)
        if value is None:
            status = ABSENT
        elif type(value) in (int, float):
            status = SCORED
        else:
            status = UNSUPPORTED
        actions.append({"action": None, "message_id": None,
                        "monitor": name[len("monitor_"):], "draw": None,
                        "status": status, "source_value": value,
                        "source_pointer": pointer})
    scored = [a for a in actions if a["status"] == SCORED]
    return {
        # A folded log carries no sample-level summary. Reporting one would
        # invent an aggregation the source never performed.
        "status": SCORED if scored else ABSENT,
        "summary_value": None,
        "actions": actions,
        "source_pointer": _pointer(index),
    }


_DISPATCH = {"eval2": _eval2, "eval1": _eval1, "eval1-legacy": _eval1_legacy}


def read_monitor(scores: object, index: int, *, adapter: str,
                 monitor_scorer: str = "monitor") -> dict[str, Any]:
    """Read one sample's monitor observation under the declared adapter."""
    if adapter not in _DISPATCH:
        raise MonitorAdapterError(
            f"unsupported adapter {adapter!r}; declared adapters are {ADAPTERS}")
    if scores is None:
        return {"status": ABSENT, "summary_value": None, "actions": [],
                "source_pointer": _pointer(index)}
    if type(scores) is not dict:
        raise MonitorAdapterError(f"sample {index}: scores must be an object")
    return _DISPATCH[adapter](scores, index, monitor_scorer)
