"""Purge removes a captured event, the records derived from it at ingest and,
unless asked to keep it, the answer paired with it.

After a purge nothing reads the selection back, the database files hold no
window of it, the audit chain carries one tombstone per purged record with no
content hash in it, a record put back under a purged key fails integrity, and
canon 0.3.0 refuses the database as "identity invalid" instead of reporting
tampering.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from canon import context_mcp
from canon.context_purge import ContextPurgeStale, select
from canon.context_store import ContextIntegrityError, ContextStore

from ._context_fixtures import (
    PROJECT, WORKSPACE, answer_payload, citing_payload, counts, db_files, long_canary,
    prompt_payload, record_keys, rows, short_canary, window_hits,
)
from ._legacy_context_0_3_0 import create_legacy_store, legacy_health


def _store_with_pair(tmp_path, prompt_text="Prompt about the tide tables",
                     answer_text="Answer about the tide tables"):
    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    prompt = store.ingest(prompt_payload("turn-7", prompt_text))["event_record_id"]
    answer = store.ingest(answer_payload(prompt, "turn-7", answer_text))["event_record_id"]
    other = store.ingest(prompt_payload("turn-8", "An unrelated kept prompt about gardening"))
    return db, store, prompt, answer, other["event_record_id"]


def _purge(store, selection):
    plan = store.purge_plan(WORKSPACE, PROJECT, selection)
    report = store.purge(WORKSPACE, PROJECT, selection, confirm_plan_sha256=plan["plan_sha256"])
    return plan, report


def _columns(db, table):
    return {row[1] for row in rows(db, f"PRAGMA table_info({table})")}


def test_purge_removes_the_event_and_its_paired_answer_from_query_and_get(tmp_path) -> None:
    canary = short_canary()
    db, store, prompt, answer, other = _store_with_pair(
        tmp_path, f"Prompt {canary}", f"Answer repeating {canary}")
    assert len(store.query(WORKSPACE, PROJECT, canary)["hits"]) == 3

    plan, report = _purge(store, select(event_id=prompt))

    assert plan["counts"] == {"events": 1, "responses": 1, "derived": 2, "records": 4}
    assert report["status"] == "purged"
    assert report["records_purged"] == 4
    assert store.query(WORKSPACE, PROJECT, canary)["hits"] == []
    for record_id in (prompt, answer):
        assert store.get(WORKSPACE, PROJECT, record_id)["status"] == "not_found_in_searched_sources"
    assert store.get(WORKSPACE, PROJECT, other)["status"] == "found_in_searched_sources"


def test_keep_responses_keeps_the_paired_answer(tmp_path) -> None:
    db, store, prompt, answer, _ = _store_with_pair(tmp_path)

    plan, _ = _purge(store, select(event_id=prompt, keep_responses=True))

    assert plan["counts"]["responses"] == 0
    assert store.get(WORKSPACE, PROJECT, prompt)["status"] == "not_found_in_searched_sources"
    kept = store.get(WORKSPACE, PROJECT, answer)
    assert kept["status"] == "found_in_searched_sources"
    assert kept["record"]["data"]["message_text"] == "Answer about the tide tables"


def test_health_and_verify_chain_pass_after_purge(tmp_path, monkeypatch) -> None:
    db, store, prompt, _, _ = _store_with_pair(tmp_path)
    before = store.verify_chain()

    _, report = _purge(store, select(event_id=prompt))

    chain = store.verify_chain()
    assert before["ok"] is True
    assert chain == {"ok": True, "length": before["length"] + report["records_purged"]}
    assert report["audit"] == chain
    monkeypatch.setenv(context_mcp.ENV_CONTEXT_DB, str(db))
    health = context_mcp.call("canon.context.health", {})
    assert health["ok"] is True
    assert health["audit"] == chain


def test_database_bytes_are_free_of_the_canary_after_the_scrub(tmp_path, monkeypatch) -> None:
    temp = tmp_path / "temp"
    temp.mkdir()
    for name in ("TMP", "TEMP", "TMPDIR", "SQLITE_TMPDIR"):
        monkeypatch.setenv(name, str(temp))
    short, long = short_canary(), long_canary()
    db, store, prompt, _, _ = _store_with_pair(
        tmp_path, f"{short} {long}", f"The answer quotes {short} {long}")

    def scanned():
        return db_files(db) + sorted(temp.iterdir())

    assert window_hits(scanned(), long) > 1000  # the scan finds the canary while it is stored
    assert window_hits(scanned(), short) > 0

    _, report = _purge(store, select(event_id=prompt))

    assert window_hits(scanned(), long) == 0
    assert window_hits(scanned(), short) == 0
    assert [path.name for path in scanned()] == [db.name]
    assert report["residual_scan"]["hits"] == 0
    assert {"freed_clusters", "legacy_fingerprints"} <= {row["class"] for row in report["residue"]}


def test_the_tombstone_holds_no_content_hash(tmp_path) -> None:
    db, store, prompt, answer, _ = _store_with_pair(tmp_path, f"Prompt {short_canary()}")
    purged = {key: (envelope, digest) for key, envelope, digest in
              rows(db, "SELECT key, envelope, sha256 FROM records")
              if key.startswith((f"workspace/{prompt}", f"workspace/{answer}"))}
    content_hashes = set()
    for envelope, digest in purged.values():
        data = json.loads(envelope)["data"]
        content_hashes |= {hashlib.sha256(envelope.encode()).hexdigest(), digest,
                           data["capture_hash"]}

    _, report = _purge(store, select(event_id=prompt))

    tombstones = rows(db, "SELECT seq, tombstone FROM context_tombstones ORDER BY seq")
    purge_rows = rows(db, "SELECT seq, key, sha256 FROM audit WHERE op='purge' ORDER BY seq")
    assert len(tombstones) == len(purge_rows) == len(purged) == report["records_purged"]
    for (seq, text), (row_seq, key, digest) in zip(tombstones, purge_rows):
        assert json.loads(text) == {"schema": "canon.context-tombstone/v1", "key": key,
                                    "reason_code": "owner_request", "ordinal": seq}
        assert row_seq == seq
        assert digest == hashlib.sha256(text.encode()).hexdigest()
        assert not any(value in text or value == digest for value in content_hashes)


def test_a_row_under_a_purged_key_fails_integrity(tmp_path) -> None:
    db, store, prompt, _, _ = _store_with_pair(tmp_path)
    original = rows(db, "SELECT key, scope, id, kind, envelope, sha256, salt FROM records"
                        " WHERE id=?", (prompt,))[0]
    _purge(store, select(event_id=prompt))
    assert store.verify_chain()["ok"] is True

    con = sqlite3.connect(str(db))
    con.execute("INSERT INTO records(key,scope,id,kind,envelope,sha256,salt)"
                " VALUES(?,?,?,?,?,?,?)", original)
    con.commit()
    con.close()

    assert store.verify_chain()["ok"] is False
    with pytest.raises(ContextIntegrityError):
        store.query(WORKSPACE, PROJECT, "tide")
    with pytest.raises(ContextIntegrityError):
        store.get(WORKSPACE, PROJECT, prompt)


def test_a_legacy_database_without_op_migrates_through_alter_table_and_verifies(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    ids = create_legacy_store(db, [prompt_payload("turn-1", "Legacy prompt one"),
                                   prompt_payload("turn-2", "Legacy prompt two")])
    assert "op" not in _columns(db, "audit") and "salt" not in _columns(db, "records")
    store = ContextStore(db)

    assert store.verify_chain() == {"ok": True, "length": 6}
    assert store.query(WORKSPACE, PROJECT, "Legacy")["coverage"]["records_searched"] == 6
    assert "op" not in _columns(db, "audit")  # reading changes no schema

    _, report = _purge(store, select(event_id=ids[0]))

    assert {"op"} <= _columns(db, "audit") and {"salt"} <= _columns(db, "records")
    assert store.verify_chain() == {"ok": True, "length": 9}
    assert store.get(WORKSPACE, PROJECT, ids[1])["status"] == "found_in_searched_sources"
    legacy = next(row for row in report["residue"] if row["class"] == "legacy_fingerprints")
    assert legacy["count"] == 3


def test_after_the_first_purge_an_older_readers_check_reports_identity_invalid(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    ids = create_legacy_store(db, [prompt_payload("turn-1", "Legacy prompt one"),
                                   prompt_payload("turn-2", "Legacy prompt two")])
    assert legacy_health(db)["ok"] is True
    store = ContextStore(db)
    store.query(WORKSPACE, PROJECT, "Legacy")
    store.verify_chain()
    assert legacy_health(db)["ok"] is True  # reading with this version locks no reader out

    _purge(store, select(event_id=ids[0]))

    assert legacy_health(db) == {"ok": False, "configured": True,
                                 "reason": "context store identity invalid"}


def test_a_stale_plan_digest_is_refused(tmp_path) -> None:
    db, store, prompt, _, _ = _store_with_pair(tmp_path)
    plan = store.purge_plan(WORKSPACE, PROJECT, select(all_events=True))
    store.ingest(prompt_payload("turn-9", "A prompt captured after the plan was made"))
    before = counts(db)

    with pytest.raises(ContextPurgeStale):
        store.purge(WORKSPACE, PROJECT, select(all_events=True),
                    confirm_plan_sha256=plan["plan_sha256"])
    with pytest.raises(ContextPurgeStale):
        store.purge(WORKSPACE, PROJECT, select(event_id=prompt),
                    confirm_plan_sha256="sha256:" + "0" * 64)

    assert counts(db) == before


def test_derived_records_go_with_their_event(tmp_path) -> None:
    db, store, prompt, _, other = _store_with_pair(tmp_path)
    derived = {key for key in record_keys(db) if key.startswith(f"workspace/{prompt}-")}
    assert len(derived) == 2

    plan, _ = _purge(store, select(event_id=prompt))

    assert {row["key"] for row in plan["entries"] if row["role"] == "derived"} == derived
    assert not derived & record_keys(db)
    assert f"workspace/{other}-extractions-0" in record_keys(db)


def test_citing_events_keep_their_text_and_report_the_purge(tmp_path) -> None:
    db, store, prompt, answer, _ = _store_with_pair(tmp_path)
    envelope = rows(db, "SELECT envelope FROM records WHERE id=?", (prompt,))[0][0]
    capture_hash = json.loads(envelope)["data"]["capture_hash"]
    citing = store.ingest(citing_payload("turn-12", prompt, "Follow up on the harbour survey"))

    plan, _ = _purge(store, select(event_id=prompt, keep_responses=True))

    assert plan["citing_events_kept"] == 2  # the kept answer and the follow-up
    hit = store.query(WORKSPACE, PROJECT, "harbour survey")["hits"][0]
    assert hit["citation"]["event_record_id"] == citing["event_record_id"]
    assert hit["cited_events_purged"] == [prompt]
    got = store.get(WORKSPACE, PROJECT, citing["event_record_id"])
    assert got["record"]["data"]["message_text"] == "Follow up on the harbour survey"
    assert got["cited_events_purged"] == [prompt]
    assert store.get(WORKSPACE, PROJECT, answer)["cited_events_purged"] == [prompt]
    assert all(capture_hash not in text for (text,) in rows(db, "SELECT envelope FROM records"))
