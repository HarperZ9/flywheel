"""How a purge selects, and how it behaves at the edges of SQLite.

An ordinal is the audit sequence number of an event's put. --before-ord and
--all stay inside one workspace and project. An empty selection writes nothing.
A purged event sent again is stored again under a fresh salt, since the latest
audit operation for a key decides. A database another tool switched to WAL is
checkpointed so neither file keeps the content, and a reader that holds the
WAL open is reported as residue rather than hidden.
"""
from __future__ import annotations

import sqlite3

import pytest

from canon.context_purge import ContextPurgeError, select
from canon.context_scrub import scrub_connection
from canon.context_store import ContextStore

from ._context_fixtures import (
    PROJECT, WORKSPACE, counts, db_files, long_canary, prompt_payload, record_keys, rows,
    window_hits,
)


def _plan_and_purge(store, selection, **options):
    plan = store.purge_plan(WORKSPACE, PROJECT, selection)
    return store.purge(WORKSPACE, PROJECT, selection, confirm_plan_sha256=plan["plan_sha256"],
                       **options)


def test_before_ord_selects_the_events_captured_earlier(tmp_path) -> None:
    store = ContextStore(tmp_path / "context.sqlite")
    ids = [store.ingest(prompt_payload(f"turn-{n}", f"Prompt number {n}"))["event_record_id"]
           for n in range(3)]
    plan = store.purge_plan(WORKSPACE, PROJECT, select(all_events=True))
    ordinals = {row["event_record_id"]: row["ordinal"] for row in plan["entries"]
                if row["role"] == "event"}
    assert ordinals[ids[0]] < ordinals[ids[1]] < ordinals[ids[2]]

    report = _plan_and_purge(store, select(before_ord=ordinals[ids[2]]))

    assert report["counts"]["events"] == 2
    assert store.get(WORKSPACE, PROJECT, ids[2])["status"] == "found_in_searched_sources"


def test_all_stays_inside_one_workspace_and_project(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    store.ingest(prompt_payload("turn-1", "Kept in canon"))
    other = prompt_payload("turn-1", "Kept in another project")
    other["project_id"] = "other"
    kept = store.ingest(other)["event_record_id"]

    _plan_and_purge(store, select(all_events=True))

    assert record_keys(db) == {f"workspace/{kept}", f"workspace/{kept}-extractions-0",
                               f"workspace/{kept}-interpretations-0"}


@pytest.mark.parametrize("options", [
    {}, {"event_id": "a", "all_events": True}, {"before_ord": 0}, {"before_ord": 1.5},
])
def test_select_needs_exactly_one_valid_selector(options) -> None:
    with pytest.raises(ContextPurgeError):
        select(**options)


def test_an_empty_selection_purges_nothing_and_writes_nothing(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    store.ingest(prompt_payload("turn-1", "Kept prompt"))
    before, raw = counts(db), db.read_bytes()

    report = _plan_and_purge(store, select(before_ord=1))

    assert report["status"] == "nothing_to_purge"
    assert counts(db) == before and db.read_bytes() == raw


def test_a_purged_event_sent_again_is_stored_again_under_a_fresh_salt(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    payload = prompt_payload("turn-1", "A prompt the client sends twice")
    first = store.ingest(payload)["event_record_id"]
    salt = rows(db, "SELECT salt FROM records WHERE id=?", (first,))[0][0]
    _plan_and_purge(store, select(event_id=first))

    again = store.ingest(payload)

    assert again["status"] == "stored_after_purge" and again["event_record_id"] == first
    assert rows(db, "SELECT salt FROM records WHERE id=?", (first,))[0][0] != salt
    assert store.verify_chain()["ok"] is True


def test_a_wal_database_keeps_no_canary_in_the_database_or_the_wal(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    con = sqlite3.connect(str(db))
    assert con.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    con.close()
    canary = long_canary()
    prompt = store.ingest(prompt_payload("turn-1", canary))["event_record_id"]
    store.ingest(prompt_payload("turn-2", "Kept prompt"))
    assert window_hits(db_files(db), canary) > 0

    report = _plan_and_purge(store, select(event_id=prompt))

    assert window_hits(db_files(db), canary) == 0
    assert report["scrub"]["journal_mode"] == "wal"
    assert report["status"] == "purged"


def test_a_reader_holding_the_wal_open_is_reported_as_residue(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    con = sqlite3.connect(str(db))
    con.execute("PRAGMA journal_mode=WAL")
    canary = long_canary()
    prompt = store.ingest(prompt_payload("turn-1", canary))["event_record_id"]
    reader = sqlite3.connect(str(db))
    reader.execute("BEGIN")
    reader.execute("SELECT COUNT(*) FROM records").fetchone()
    try:
        report = _plan_and_purge(store, select(event_id=prompt), busy_retry_seconds=0.2)
    finally:
        reader.close()
        con.close()

    assert report["status"] == "residue_found"
    assert report["scrub"]["wal_checkpoint"] == "busy"
    assert report["residual_scan"]["hits"] > 0
    assert store.get(WORKSPACE, PROJECT, prompt)["status"] == "not_found_in_searched_sources"


def test_the_scrub_connection_zeroes_deleted_content_and_keeps_temp_in_memory(tmp_path) -> None:
    con = scrub_connection(tmp_path / "context.sqlite")
    try:
        assert con.execute("PRAGMA secure_delete").fetchone()[0] == 1
        assert con.execute("PRAGMA temp_store").fetchone()[0] == 2
    finally:
        con.close()
