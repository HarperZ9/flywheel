"""Retention runs canon's retention planner against the context store.

A policy file names captured events and one planner action each. tombstone and
purge-all remove the event and its derived records, and, as a purge does, the
paired answer unless the file keeps responses. purge-derived removes only the
derived records and keeps the event. retain keeps everything. Each tombstone
names the rule that removed its record. A policy asking a tombstone to keep a
content hash is refused, because a context tombstone holds none.
"""
from __future__ import annotations

import json

import pytest

from canon.context_purge import ContextPurgeError
from canon.context_retention import POLICY_SCHEMA, policy_selection
from canon.context_store import ContextStore

from ._context_fixtures import (
    PROJECT, WORKSPACE, answer_payload, counts, prompt_payload, record_keys, rows,
)


def _policy(*entries, keep_responses=False, retain_hash=False, stores=("sqlite",)):
    return {"schema": POLICY_SCHEMA, "keep_responses": keep_responses,
            "policies": [{"subject_id": subject, "action": action,
                          "retain_content_hash": retain_hash, "derived_stores": list(stores)}
                         for subject, action in entries]}


def _apply(store, policy):
    selection = policy_selection(policy)
    plan = store.purge_plan(WORKSPACE, PROJECT, selection)
    return plan, store.purge(WORKSPACE, PROJECT, selection, confirm_plan_sha256=plan["plan_sha256"])


def _store(tmp_path):
    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    first = store.ingest(prompt_payload("turn-1", "First prompt about sailing"))["event_record_id"]
    answer = store.ingest(answer_payload(first, "turn-1", "An answer about sailing"))
    second = store.ingest(prompt_payload("turn-2", "Second prompt about rowing"))["event_record_id"]
    return db, store, first, answer["event_record_id"], second


def _reasons(db):
    return sorted(json.loads(text)["reason_code"]
                  for (text,) in rows(db, "SELECT tombstone FROM context_tombstones"))


def test_purge_all_and_tombstone_remove_the_event_its_derived_records_and_its_answer(
        tmp_path) -> None:
    db, store, first, answer, second = _store(tmp_path)

    plan, report = _apply(store, _policy((first, "purge-all"), (second, "tombstone")))

    assert plan["counts"] == {"events": 2, "responses": 1, "derived": 4, "records": 7}
    assert report["records_purged"] == 7
    assert record_keys(db) == set()
    assert _reasons(db) == ["retention_purge_all"] * 4 + ["retention_tombstone"] * 3
    assert store.verify_chain()["ok"] is True


def test_purge_derived_removes_derived_records_and_keeps_the_event(tmp_path) -> None:
    db, store, first, answer, _ = _store(tmp_path)

    plan, _ = _apply(store, _policy((first, "purge-derived")))

    assert plan["counts"] == {"events": 0, "responses": 0, "derived": 2, "records": 2}
    keys = record_keys(db)
    assert f"workspace/{first}" in keys and f"workspace/{answer}" in keys
    assert not any(key.startswith(f"workspace/{first}-") for key in keys)
    assert _reasons(db) == ["retention_purge_derived"] * 2
    again = store.ingest(prompt_payload("turn-1", "First prompt about sailing"))
    assert again["status"] == "already_present"
    assert not any(key.startswith(f"workspace/{first}-") for key in record_keys(db))


def test_retain_keeps_everything_and_writes_nothing(tmp_path) -> None:
    db, store, first, _, second = _store(tmp_path)
    before = counts(db)

    plan, report = _apply(store, _policy((first, "retain"), (second, "retain")))

    assert plan["counts"]["records"] == 0
    assert report["status"] == "nothing_to_purge"
    assert counts(db) == before


def test_keep_responses_in_the_policy_keeps_the_answer(tmp_path) -> None:
    db, store, first, answer, _ = _store(tmp_path)

    _apply(store, _policy((first, "purge-all"), keep_responses=True))

    assert f"workspace/{answer}" in record_keys(db)
    assert f"workspace/{first}" not in record_keys(db)


def test_a_policy_that_keeps_a_content_hash_is_refused(tmp_path) -> None:
    db, store, first, _, _ = _store(tmp_path)
    before = counts(db)

    with pytest.raises(ContextPurgeError, match="content hash"):
        store.purge_plan(WORKSPACE, PROJECT,
                         policy_selection(_policy((first, "purge-all"), retain_hash=True)))

    assert counts(db) == before


@pytest.mark.parametrize("change", [
    lambda policy: policy.update(schema="canon.context-retention-policy/v9"),
    lambda policy: policy["policies"][0].update(action="erase"),
    lambda policy: policy["policies"][0].update(subject_id="context-event-" + "0" * 64),
    lambda policy: policy["policies"].append(dict(policy["policies"][0])),
    lambda policy: policy["policies"][0].update(action="purge-derived", derived_stores=["files"]),
    lambda policy: policy.update(policies=[]),
])
def test_an_unknown_subject_or_invalid_policy_is_refused_before_any_delete(
        tmp_path, change) -> None:
    db, store, first, _, _ = _store(tmp_path)
    policy = _policy((first, "purge-all"))
    change(policy)
    before = counts(db)

    with pytest.raises(ContextPurgeError):
        selection = policy_selection(policy)
        plan = store.purge_plan(WORKSPACE, PROJECT, selection)
        store.purge(WORKSPACE, PROJECT, selection, confirm_plan_sha256=plan["plan_sha256"])

    assert counts(db) == before
