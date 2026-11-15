"""Append-only, hash-linked action-receipt ledger with a strict loader.

The durability primitive the primitive observability tools do not own: events are
appended (never mutated); each is hash-linked to the previous, so tamper, reorder,
and delete are all detected on verify. Corrections are appended, never edited in
place. The strict loader rejects duplicate keys and NaN/Infinity. Stdlib-only.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .._strict_json import strict_json_loads


def _canonical(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _event_hash(seq: int, prev: str, record: dict[str, Any]) -> str:
    return _hash(_canonical({"seq": seq, "prev": prev, "record": record}))


def read_events(path: str | Path) -> list[dict[str, Any]]:
    """Strict-load all events (rejects duplicate keys / NaN / Infinity)."""
    text = Path(path).read_text(encoding="utf-8") if Path(path).exists() else ""
    return [strict_json_loads(line) for line in text.splitlines() if line.strip()]


def append_event(path: str | Path, record: dict[str, Any]) -> str:
    """Append one hash-linked event; return its event_hash."""
    events = read_events(path)
    seq = len(events)
    prev = events[-1]["event_hash"] if events else ""
    event_hash = _event_hash(seq, prev, record)
    stored = {"seq": seq, "prev": prev, "record": record, "event_hash": event_hash}
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(_canonical(stored) + "\n")
    return event_hash


def verify_ledger(events: list[dict[str, Any]]) -> list[str]:
    """Return a list of integrity issues; empty means the chain is intact."""
    issues: list[str] = []
    prev = ""
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            issues.append(f"event[{index}] is not an object")
            continue
        if event.get("seq") != index:
            issues.append(
                f"event[{index}] seq {event.get('seq')!r} != position {index}"
            )
        if event.get("prev") != prev:
            issues.append(f"event[{index}] prev does not link to the previous event")
        expected = _event_hash(index, event.get("prev", ""), event.get("record", {}))
        if event.get("event_hash") != expected:
            issues.append(f"event[{index}] event_hash does not re-derive (tampered)")
        prev = event.get("event_hash", "")
    return issues


def lookup(events: list[dict[str, Any]], **filters: Any) -> list[dict[str, Any]]:
    """Filter events by record fields (action_id / packet_id / idempotency_key / ...)."""
    active = {k: v for k, v in filters.items() if v is not None}
    return [
        event
        for event in events
        if isinstance(event.get("record"), dict)
        and all(event["record"].get(k) == v for k, v in active.items())
    ]
