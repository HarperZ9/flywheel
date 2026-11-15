"""A context database edited by something other than canon fails closed.

A writer with direct access to the file can rewrite the whole audit chain, so
the chain alone cannot refuse what it wrote. What canon can promise is that a
row it did not write is refused as an integrity failure rather than crashing a
reader, and that nothing read from such a row can drive the terminal.
"""
from __future__ import annotations

import io
import json
import sqlite3

import pytest

from canon.cli import run_cli
from canon.context_audit import insert_record
from canon.context_migrate import prepare_write
from canon.context_purge import select
from canon.context_store import ContextIntegrityError, ContextStore
from canon.schema import KIND_EPISODIC_MEMORY, Provenance, Record

from ._context_fixtures import (
    PROJECT, WORKSPACE, prompt_payload, rewrite_tombstone, rows,
)


def _purged_store(tmp_path):
    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    prompt = store.ingest(prompt_payload("turn-1", "A prompt to purge"))["event_record_id"]
    store.ingest(prompt_payload("turn-2", "A prompt to keep about the tide"))
    plan = store.purge_plan(WORKSPACE, PROJECT, select(event_id=prompt))
    store.purge(WORKSPACE, PROJECT, select(event_id=prompt),
                confirm_plan_sha256=plan["plan_sha256"])
    seq, text = rows(db, "SELECT seq, tombstone FROM context_tombstones ORDER BY seq")[0]
    return db, store, seq, json.loads(text)


def _refused(store) -> None:
    assert store.verify_chain()["ok"] is False
    with pytest.raises(ContextIntegrityError):
        store.query(WORKSPACE, PROJECT, "tide")


def test_a_tombstone_that_is_not_an_object_fails_integrity(tmp_path) -> None:
    db, store, seq, _ = _purged_store(tmp_path)

    rewrite_tombstone(db, seq, json.dumps(["canon.context-tombstone/v1"]))

    _refused(store)


def test_a_tombstone_carrying_an_extra_field_fails_integrity(tmp_path) -> None:
    db, store, seq, body = _purged_store(tmp_path)
    body["content_sha256"] = "0" * 64

    rewrite_tombstone(db, seq, json.dumps(body, sort_keys=True, separators=(",", ":")))

    _refused(store)


def test_a_tombstone_nested_past_the_parser_limit_fails_integrity(tmp_path) -> None:
    db, store, seq, _ = _purged_store(tmp_path)

    rewrite_tombstone(db, seq, "[" * 100_000 + "]" * 100_000)

    _refused(store)


def test_a_tombstone_in_another_layout_fails_integrity(tmp_path) -> None:
    db, store, seq, body = _purged_store(tmp_path)

    rewrite_tombstone(db, seq, json.dumps(body, indent=2))

    _refused(store)


def test_a_table_another_tool_added_is_refused_even_when_its_name_needs_quoting(
        tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    prompt = store.ingest(prompt_payload("turn-1", "A prompt to purge"))["event_record_id"]
    con = sqlite3.connect(str(db))
    con.execute('CREATE TABLE "notes""extra"(body TEXT)')
    con.execute('INSERT INTO "notes""extra" VALUES(?)', ("a note another tool keeps here",))
    con.commit()
    con.close()

    with pytest.raises(ContextIntegrityError, match="schema"):
        store.purge_plan(WORKSPACE, PROJECT, select(event_id=prompt))
    assert store.verify_chain()["ok"] is False


def test_an_event_id_with_control_characters_prints_escaped(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    store.identity()
    hostile = "context-event-\x1b[2J\x1b]0;owned\x07"
    record = Record(KIND_EPISODIC_MEMORY, hostile, "workspace", {
        "workspace_id": WORKSPACE, "project_id": PROJECT, "event_record_id": hostile,
        "record_role": "event", "text": "planted", "message_text": "planted", "sources": [],
    }, Provenance("codex", "0" * 64))
    con = sqlite3.connect(str(db))
    con.execute("BEGIN IMMEDIATE")
    prepare_write(con)
    insert_record(con, record)
    con.commit()
    con.close()
    out = io.StringIO()

    code = run_cli(["context", "purge", "--db", str(db), "--workspace-id", WORKSPACE,
                    "--project-id", PROJECT, "--all", "--dry-run"],
                   stdin=io.StringIO(""), stdout=out, stderr=io.StringIO(), environ={})

    assert code == 0
    assert "\x1b" not in out.getvalue() and "\x07" not in out.getvalue()
    assert "context-event-\\x1b[2J\\x1b]0;owned\\x07" in out.getvalue()
