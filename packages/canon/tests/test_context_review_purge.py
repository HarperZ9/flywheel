"""Purge-side findings from the review of the purge and capture branch.

The residual scan reads a UTF-16 database in its own encoding. A report whose
scrub did not finish says so in its status, and its residue note says VACUUM
did not run. A plan speaks of the rewrite in the future tense. Every report
names residue and what canon cannot reach. `keep_responses` keeps every answer
under the bulk selectors, paired or not. A reader holding a rollback-journal
database leaves a dry run free to plan and makes an apply refuse cleanly. The
checkpoint before VACUUM is reported beside the one after it. A dry run on a
store with a scrub pending succeeds and says a confirmed run finishes it.
"""
from __future__ import annotations

import io
import json
import sqlite3

import canon.context_purge as context_purge
from canon.cli import run_cli
from canon.context_purge import select
from canon.context_store import ContextStore
from canon.exit_codes import EX_CONFLICT

from ._context_fixtures import (
    PROJECT, WORKSPACE, answer_payload, counts, db_files, long_canary, prompt_payload,
    window_hits,
)

_REAL_SCRUB = context_purge.scrub_database


def _busy_scrub(conn, budget):
    """The real scrub, reported as if another connection had kept VACUUM out."""
    return {**_REAL_SCRUB(conn, budget), "vacuum": "skipped_database_busy"}


def _apply(store, selection, **options):
    plan = store.purge_plan(WORKSPACE, PROJECT, selection)
    return store.purge(WORKSPACE, PROJECT, selection, confirm_plan_sha256=plan["plan_sha256"],
                       **options)


def _cli(db, *extra):
    out, err = io.StringIO(), io.StringIO()
    code = run_cli(["--json", "context", "purge", "--db", str(db), "--workspace-id", WORKSPACE,
                    "--project-id", PROJECT, *extra],
                   stdin=io.StringIO(""), stdout=out, stderr=err, environ={})
    return code, json.loads(out.getvalue())


def _freed_note(rows) -> str:
    return next(row["note"] for row in rows if row["class"] == "freed_clusters")


def _no_scrub(conn, budget):
    """A scrub that never ran: the WAL keeps the frames written at ingest."""
    return {"journal_mode": "wal", "vacuum": "skipped_database_busy",
            "wal_checkpoint_before": "busy", "wal_checkpoint": "busy"}


def test_a_utf16_database_is_scanned_in_its_own_encoding(tmp_path, monkeypatch) -> None:
    db = tmp_path / "context.sqlite"
    con = sqlite3.connect(str(db))
    con.execute("PRAGMA encoding='UTF-16le'")
    con.execute("CREATE TABLE made_by_another_tool(x)")
    con.execute("DROP TABLE made_by_another_tool")
    con.commit()
    assert con.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    assert con.execute("PRAGMA encoding").fetchone()[0] == "UTF-16le"
    store = ContextStore(db)
    canary = long_canary()
    prompt = store.ingest(prompt_payload("turn-1", canary))["event_record_id"]
    monkeypatch.setattr(context_purge, "scrub_database", _no_scrub)
    seen, real_scan = [], context_purge.residual_scan

    def scan_and_count(*args, **kwargs):
        # The WAL is checkpointed away when the purge's connection closes, so
        # the fixture's own count of what is there runs at scan time.
        seen.append(window_hits(db_files(db), canary))
        return real_scan(*args, **kwargs)

    monkeypatch.setattr(context_purge, "residual_scan", scan_and_count)
    try:
        report = _apply(store, select(event_id=prompt))
    finally:
        con.close()

    assert seen and seen[0] > 0
    assert report["residual_scan"]["encoding"] == "utf-16-le"
    assert report["status"] == "residue_found"
    assert report["residual_scan"]["hits"] > 0


def test_a_report_whose_scrub_did_not_finish_is_not_called_purged(tmp_path, monkeypatch) -> None:
    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    prompt = store.ingest(prompt_payload("turn-1", "The harbor ledger"))["event_record_id"]
    monkeypatch.setattr(context_purge, "scrub_database", _busy_scrub)

    report = _apply(store, select(event_id=prompt))

    assert report["status"] == "scrub_incomplete"
    assert "rewrote" not in _freed_note(report["residue"])
    assert "did not run" in _freed_note(report["residue"])


def test_a_plan_speaks_of_the_rewrite_as_still_to_come(tmp_path) -> None:
    store = ContextStore(tmp_path / "context.sqlite")
    prompt = store.ingest(prompt_payload("turn-1", "The harbor ledger"))["event_record_id"]

    plan = store.purge_plan(WORKSPACE, PROJECT, select(event_id=prompt))

    note = _freed_note(plan["residue_forecast"])
    assert "rewrote" not in note and "rewrites" in note


def test_a_report_that_removed_nothing_still_names_residue_and_reach(tmp_path) -> None:
    store = ContextStore(tmp_path / "context.sqlite")
    prompt = store.ingest(prompt_payload("turn-1", "The harbor ledger"))["event_record_id"]
    _apply(store, select(event_id=prompt))

    report = _apply(store, select(event_id=prompt))

    assert report["status"] == "nothing_to_purge"
    assert {row["class"] for row in report["residue"]} >= {"freed_clusters"}
    assert {row["class"] for row in report["out_of_reach"]} >= {"client_transcripts"}


def test_keep_responses_keeps_every_answer_under_a_bulk_selector(tmp_path, monkeypatch) -> None:
    store = ContextStore(tmp_path / "context.sqlite")
    prompt = store.ingest(prompt_payload("turn-1", "The harbor ledger"))["event_record_id"]
    unpaired = answer_payload(prompt, "turn-1", "An answer with no pairing field")
    del unpaired["event"]["responds_to"]
    unpaired["event"]["event_id"] = "turn-1-response-9"
    loose = store.ingest(unpaired)["event_record_id"]
    monkeypatch.setattr("canon.context_store._require_prompt", lambda *a: None)
    orphan = store.ingest(answer_payload("context-event-" + "1" * 64, "turn-0",
                                         "An answer whose prompt was never captured"))
    monkeypatch.undo()

    for selection in (select(all_events=True, keep_responses=True),
                      select(before_ord=10_000, keep_responses=True)):
        plan = store.purge_plan(WORKSPACE, PROJECT, selection)
        removed = {row["event_record_id"] for row in plan["entries"]}
        assert prompt in removed
        assert not removed & {loose, orphan["event_record_id"]}


def test_a_rollback_journal_reader_leaves_the_dry_run_free_and_the_apply_busy(
        tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    prompt = store.ingest(prompt_payload("turn-1", "The harbor ledger"))["event_record_id"]
    store.ingest(answer_payload(prompt, "turn-1", "In the harbor office"))
    before = counts(db)
    reader = sqlite3.connect(str(db))
    reader.execute("BEGIN")
    reader.execute("SELECT COUNT(*) FROM records").fetchone()
    try:
        dry_code, dry = _cli(db, "--event-id", prompt, "--dry-run")
        code, result = _cli(db, "--event-id", prompt, "--yes")
    finally:
        reader.close()

    assert (dry_code, dry["ok"]) == (0, True)
    assert (code, result["failure_code"]) == (EX_CONFLICT, "store_busy")
    assert counts(db) == before
    assert store.verify_chain()["ok"] is True


def test_the_checkpoint_before_vacuum_is_reported_beside_the_one_after(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    con = sqlite3.connect(str(db))
    con.execute("PRAGMA journal_mode=WAL")
    con.close()
    prompt = store.ingest(prompt_payload("turn-1", "The harbor ledger"))["event_record_id"]

    report = _apply(store, select(event_id=prompt))

    assert report["scrub"]["wal_checkpoint_before"] == "done"
    assert report["scrub"]["wal_checkpoint"] == "done"


def test_a_dry_run_on_a_store_with_a_scrub_pending_succeeds_and_says_so(
        tmp_path, monkeypatch) -> None:
    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    prompt = store.ingest(prompt_payload("turn-1", "The harbor ledger"))["event_record_id"]
    monkeypatch.setattr(context_purge, "scrub_database", _busy_scrub)
    _apply(store, select(event_id=prompt))
    monkeypatch.undo()

    code, result = _cli(db, "--event-id", prompt, "--dry-run")

    assert (code, result["ok"]) == (0, True)
    assert result["data"]["scrub_pending"] is True
    code, result = _cli(db, "--event-id", prompt, "--yes")
    assert (code, result["data"]["status"]) == (0, "scrub_finished")
