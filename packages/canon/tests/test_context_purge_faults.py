"""A purge interrupted at any step ends where an uninterrupted one would.

Before its commit, a purge changes nothing. After its commit the rows are gone
but the file still needs VACUUM, so the purge leaves a scrub-pending mark in
the same transaction; the next confirmed purge, even one with nothing left to
remove, finishes the scrub and clears the mark. Running a purge or a retention
policy again after it applied reports the events as already purged instead of
failing, so the owner can rerun the command that was interrupted.
"""
from __future__ import annotations

import json

import pytest

import canon.context_purge as context_purge
from canon import context_mcp
from canon.context_purge import ContextPurgeNotFound, select
from canon.context_retention import POLICY_SCHEMA, policy_selection
from canon.context_store import ContextStore

from ._context_fixtures import (
    PROJECT, WORKSPACE, answer_payload, counts, db_files, long_canary, prompt_payload,
    record_keys, rows, window_hits,
)


def _store(tmp_path, text="Prompt about the tide tables"):
    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    for n in range(3):
        # ASCII filler: a kept random text in the canary's alphabet would share
        # low-entropy JSON-escaped windows with it and read as residue.
        store.ingest(prompt_payload(f"fill-{n}", f"filler record {n} " * 300))
    prompt = store.ingest(prompt_payload("turn-1", text))["event_record_id"]
    store.ingest(answer_payload(prompt, "turn-1", "The answer restates it: " + text))
    return db, store, prompt


def _apply(store, selection):
    plan = store.purge_plan(WORKSPACE, PROJECT, selection)
    return plan, store.purge(WORKSPACE, PROJECT, selection,
                             confirm_plan_sha256=plan["plan_sha256"])


def _health(monkeypatch, db):
    monkeypatch.setenv(context_mcp.ENV_CONTEXT_DB, str(db))
    return context_mcp.call("canon.context.health", {})


def test_a_fault_before_the_commit_changes_nothing(tmp_path, monkeypatch) -> None:
    db, store, prompt = _store(tmp_path)
    before, keys = counts(db), record_keys(db)
    real, calls = context_purge.append_purge, []

    def failing(conn, key, reason):
        calls.append(key)
        if len(calls) == 2:
            raise RuntimeError("injected fault")
        return real(conn, key, reason)

    monkeypatch.setattr(context_purge, "append_purge", failing)
    with pytest.raises(RuntimeError, match="injected fault"):
        _apply(store, select(event_id=prompt))
    monkeypatch.setattr(context_purge, "append_purge", real)

    assert (counts(db), record_keys(db)) == (before, keys)
    assert store.verify_chain()["ok"] is True
    assert _health(monkeypatch, db)["scrub_pending"] is False
    _, report = _apply(store, select(event_id=prompt))
    assert report["status"] == "purged"


def test_a_fault_after_the_commit_is_finished_by_the_next_apply(tmp_path, monkeypatch) -> None:
    canary = long_canary()
    db, store, prompt = _store(tmp_path, canary)
    real = context_purge.scrub_database

    def failing(conn, busy):
        raise RuntimeError("injected fault")

    monkeypatch.setattr(context_purge, "scrub_database", failing)
    with pytest.raises(RuntimeError, match="injected fault"):
        _apply(store, select(event_id=prompt))
    monkeypatch.setattr(context_purge, "scrub_database", real)

    assert store.get(WORKSPACE, PROJECT, prompt)["status"] == "not_found_in_searched_sources"
    assert store.verify_chain()["ok"] is True
    assert _health(monkeypatch, db)["scrub_pending"] is True

    plan, report = _apply(store, select(event_id=prompt))

    assert plan["entries"] == [] and plan["already_purged"] == [prompt]
    assert plan["scrub_pending"] is True
    assert report["status"] == "scrub_finished"
    assert report["scrub"]["vacuum"] == "done"
    assert report["residual_scan"]["status"] == "not_run"
    assert window_hits(db_files(db), canary) == 0
    assert _health(monkeypatch, db)["scrub_pending"] is False
    assert store.verify_chain()["ok"] is True


def test_an_uninterrupted_purge_leaves_no_scrub_pending(tmp_path, monkeypatch) -> None:
    db, store, prompt = _store(tmp_path)

    _, report = _apply(store, select(event_id=prompt))

    assert report["status"] == "purged" and report["scrub_pending"] is False
    assert _health(monkeypatch, db)["scrub_pending"] is False
    assert rows(db, "SELECT COUNT(*) FROM context_store_meta WHERE key='scrub_pending'") == [(0,)]


def test_a_purge_run_again_reports_the_event_as_already_purged(tmp_path) -> None:
    db, store, prompt = _store(tmp_path)
    _apply(store, select(event_id=prompt))
    before = counts(db)

    plan, report = _apply(store, select(event_id=prompt))

    assert plan["already_purged"] == [prompt] and plan["counts"]["records"] == 0
    assert report["status"] == "nothing_to_purge"
    assert counts(db) == before
    with pytest.raises(ContextPurgeNotFound):
        store.purge_plan(WORKSPACE, PROJECT, select(event_id="context-event-" + "0" * 64))


def test_a_retention_policy_runs_again_without_failing(tmp_path) -> None:
    db, store, prompt = _store(tmp_path)
    policy = {"schema": POLICY_SCHEMA, "policies": [
        {"subject_id": prompt, "action": "purge-all", "retain_content_hash": False,
         "derived_stores": ["sqlite"]}]}
    _apply(store, policy_selection(policy))
    before = counts(db)

    plan, report = _apply(store, policy_selection(json.loads(json.dumps(policy))))

    assert plan["already_purged"] == [prompt]
    assert report["status"] == "nothing_to_purge"
    assert counts(db) == before
