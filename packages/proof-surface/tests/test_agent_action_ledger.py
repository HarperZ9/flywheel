"""Append-only, hash-linked action-receipt ledger with a strict loader.

The durability primitive: events are appended (never mutated), each hash-linked to
the previous; the strict loader rejects duplicate keys and NaN/Infinity; tamper,
reorder, and delete are all detected on verify.
"""

from __future__ import annotations

import pytest

from proof_surface.agent_action import ledger


def _rec(action_id, **extra):
    return {
        "packet_id": "pkt-1",
        "action_id": action_id,
        "idempotency_key": "k-" + action_id,
        **extra,
    }


def test_append_then_read_verifies_clean(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger.append_event(path, _rec("s1"))
    ledger.append_event(path, _rec("s2"))
    ledger.append_event(path, _rec("s3", kind="correction"))
    events = ledger.read_events(path)
    assert [e["seq"] for e in events] == [0, 1, 2]
    assert ledger.verify_ledger(events) == []
    # genesis has empty prev; each links to the prior event hash
    assert events[0]["prev"] == ""
    assert events[1]["prev"] == events[0]["event_hash"]


def test_tampering_with_a_record_is_detected(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger.append_event(path, _rec("s1"))
    ledger.append_event(path, _rec("s2"))
    events = ledger.read_events(path)
    events[0]["record"]["action_id"] = "hacked"  # mutate in place
    issues = ledger.verify_ledger(events)
    assert issues  # hash no longer re-derives


def test_reorder_is_detected(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger.append_event(path, _rec("s1"))
    ledger.append_event(path, _rec("s2"))
    events = ledger.read_events(path)
    events[0], events[1] = events[1], events[0]  # reorder
    assert ledger.verify_ledger(events)


def test_delete_is_detected(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger.append_event(path, _rec("s1"))
    ledger.append_event(path, _rec("s2"))
    ledger.append_event(path, _rec("s3"))
    events = ledger.read_events(path)
    del events[1]  # drop the middle event
    assert ledger.verify_ledger(events)


def test_strict_loader_rejects_duplicate_keys(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"a": 1, "a": 2}\n', encoding="utf-8")
    with pytest.raises(ValueError):
        ledger.read_events(path)


def test_strict_loader_rejects_non_finite(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"x": NaN}\n', encoding="utf-8")
    with pytest.raises(ValueError):
        ledger.read_events(path)


def test_lookup_by_action_and_idempotency_key(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger.append_event(path, _rec("s1"))
    ledger.append_event(path, _rec("s2"))
    events = ledger.read_events(path)
    assert [
        e["record"]["action_id"] for e in ledger.lookup(events, action_id="s2")
    ] == ["s2"]
    assert len(ledger.lookup(events, idempotency_key="k-s1")) == 1
    assert len(ledger.lookup(events, packet_id="pkt-1")) == 2
