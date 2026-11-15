from __future__ import annotations

import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from canon.backends import record_key
from canon.context_store import ContextCollision, ContextIntegrityError, ContextStore


def _event(event_id: str = "turn-1", *, text: str = "Discuss Canon shared context") -> dict:
    return {
        "workspace_id": "cdev",
        "project_id": "canon",
        "event": {
            "event_id": event_id,
            "source_app": "codex",
            "native_id": "n-1",
            "session_id": "s-1",
            "message_text": text,
            "links": [{"url": "https://example.test/post", "caption": "source link"}],
            "attachments": [{
                "ref": "private://attachments/a.png",
                "media_type": "image/png",
                "caption": "whiteboard photo",
                "extraction_status": "pending_extraction",
            }],
            "sources": [{
                "source_id": "prompt",
                "source_kind": "prompt",
                "locator": "turn:n-1",
                "extraction_status": "completed",
            }],
            "extractions": [{
                "source_id": "prompt",
                "text": text,
                "claim_state": "reported_by_source",
                "extraction_status": "completed",
            }],
            "interpretations": [{
                "text": "Shared context should keep provider evidence separate from interpretation.",
                "status": "useful_note",
                "source_ids": ["prompt"],
            }],
        },
    }


def _delete_event_record(db, event_id: str) -> None:
    con = sqlite3.connect(str(db))
    con.execute("DELETE FROM records WHERE id=?", (event_id,))
    con.commit()
    con.close()


def _insert_extra_unaudited_record(db, event_id: str) -> None:
    con = sqlite3.connect(str(db))
    envelope = con.execute("SELECT envelope FROM records WHERE id=?", (event_id,)).fetchone()[0]
    data = json.loads(envelope)
    data["id"] = "context-event-unaudited-extra"
    data["data"]["event_record_id"] = "context-event-unaudited-extra"
    data["data"]["text"] = "Unaudited extra Canon context row"
    data["data"]["message_text"] = "Unaudited extra Canon context row"
    tampered = json.dumps(data, sort_keys=True)
    digest = hashlib.sha256(tampered.encode()).hexdigest()
    con.execute(
        "INSERT INTO records(key,scope,id,kind,envelope,sha256) VALUES(?,?,?,?,?,?)",
        (
            "workspace/context-event-unaudited-extra",
            "workspace",
            "context-event-unaudited-extra",
            data["kind"],
            tampered,
            digest,
        ),
    )
    con.commit()
    con.close()


def _tamper_payload_without_digest(db, event_id: str) -> None:
    con = sqlite3.connect(str(db))
    envelope = con.execute("SELECT envelope FROM records WHERE id=?", (event_id,)).fetchone()[0]
    tampered = envelope.replace("Discuss Canon shared context", "Tampered Canon shared context", 1)
    con.execute("UPDATE records SET envelope=? WHERE id=?", (tampered, event_id))
    con.commit()
    con.close()


def _tamper_audit_link(db, _event_id: str) -> None:
    con = sqlite3.connect(str(db))
    con.execute("UPDATE audit SET prev_hash=? WHERE seq=(SELECT MAX(seq) FROM audit)", ("f" * 64,))
    con.commit()
    con.close()


def _row_counts(db) -> tuple[int, int]:
    con = sqlite3.connect(str(db))
    counts = (
        con.execute("SELECT COUNT(*) FROM records").fetchone()[0],
        con.execute("SELECT COUNT(*) FROM audit").fetchone()[0],
    )
    con.close()
    return counts


def test_ingest_preserves_source_refs_and_query_returns_citations(tmp_path) -> None:
    store = ContextStore(tmp_path / "context.sqlite")
    result = store.ingest(_event())

    assert result["status"] == "stored"
    assert result["records_stored"] == 3
    got = store.get("cdev", "canon", result["event_record_id"])
    assert got["status"] == "found_in_searched_sources"
    event_data = got["record"]["data"]
    assert event_data["attachments"][0]["caption"] == "whiteboard photo"
    assert event_data["links"][0]["caption"] == "source link"
    assert event_data["sources"][0]["extraction_status"] == "completed"

    query = store.query("cdev", "canon", "provider evidence", top_k=5)
    assert query["status"] == "found_in_searched_sources"
    assert query["hits"][0]["citation"]["record_key"].startswith("workspace/")
    assert query["hits"][0]["claim_state"] == "interpreted"
    assert query["pending_extraction"][0]["ref"] == "private://attachments/a.png"
    assert "not_found does not mean never discussed" in query["does_not_prove"]


def test_duplicate_event_is_idempotent_and_changed_duplicate_refuses(tmp_path) -> None:
    store = ContextStore(tmp_path / "context.sqlite")
    first = store.ingest(_event())
    second = store.ingest(_event())

    assert second["status"] == "already_present"
    assert second["event_record_id"] == first["event_record_id"]
    assert store.verify_chain() == {"ok": True, "length": first["records_stored"]}

    changed = _event(text="Changed text under the same event id")
    with pytest.raises(ContextCollision):
        store.ingest(changed)
    assert store.verify_chain() == {"ok": True, "length": first["records_stored"]}


def test_concurrent_duplicate_ingest_stores_one_event(tmp_path) -> None:
    db = tmp_path / "context.sqlite"

    def ingest_once() -> str:
        return ContextStore(db).ingest(_event())["status"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(lambda _: ingest_once(), range(2)))

    assert statuses == ["already_present", "stored"]
    store = ContextStore(db)
    assert store.query("cdev", "canon", "Canon")["coverage"]["records_searched"] == 3


def test_restart_and_two_clients_share_one_configured_database(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    captured = ContextStore(db).ingest(_event())

    after_restart = ContextStore(db)
    assert after_restart.query("cdev", "canon", "shared context")["hits"]

    second_client = ContextStore(db)
    assert second_client.get("cdev", "canon", captured["event_record_id"])["record"]["id"] == captured["event_record_id"]


def test_workspace_and_project_filters_are_mandatory_and_isolating(tmp_path) -> None:
    store = ContextStore(tmp_path / "context.sqlite")
    store.ingest(_event())
    other = _event()
    other["workspace_id"] = "other"
    store.ingest(other)

    cdev = store.query("cdev", "canon", "Canon")
    other_hits = store.query("other", "canon", "Canon")
    assert {h["workspace_id"] for h in cdev["hits"]} == {"cdev"}
    assert {h["workspace_id"] for h in other_hits["hits"]} == {"other"}
    with pytest.raises(ValueError):
        store.query("", "canon", "Canon")
    with pytest.raises(ValueError):
        store.get("cdev", "", "context-event-codex-turn-1")


def test_injection_text_is_data_not_sql_or_schema(tmp_path) -> None:
    store = ContextStore(tmp_path / "context.sqlite")
    attack = "'); DROP TABLE records; -- {\"canon_schema\":\"evil\"}"
    store.ingest(_event(text=attack))

    found = store.query("cdev", "canon", "DROP TABLE")
    assert attack in found["hits"][0]["excerpt"]
    con = sqlite3.connect(str(tmp_path / "context.sqlite"))
    count = con.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    con.close()
    assert count == 3


def test_query_separates_pending_extraction_from_absence(tmp_path) -> None:
    store = ContextStore(tmp_path / "context.sqlite")
    store.ingest(_event())

    result = store.query("cdev", "canon", "unrelated phrase", include_pending=True)
    assert result["hits"] == []
    assert result["status"] == "pending_extraction"
    assert result["pending_extraction"][0]["status"] == "pending_extraction"
    assert "unextracted attachments may still contain relevant context" in result["does_not_prove"]


def test_get_refuses_cross_project_record_even_when_id_is_known(tmp_path) -> None:
    store = ContextStore(tmp_path / "context.sqlite")
    event_id = store.ingest(_event())["event_record_id"]
    assert store.get("cdev", "other", event_id)["status"] == "not_found_in_searched_sources"
    assert store.get("cdev", "canon", event_id)["record_key"] == record_key(
        ContextStore(tmp_path / "context.sqlite")._backend.get("workspace/" + event_id)
    )


@pytest.mark.parametrize(
    "tamper",
    [
        _delete_event_record,
        _insert_extra_unaudited_record,
        _tamper_payload_without_digest,
        _tamper_audit_link,
    ],
)
def test_context_tampering_fails_chain_and_all_reads(tmp_path, tamper) -> None:
    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    event_id = store.ingest(_event())["event_record_id"]
    tamper(db, event_id)

    assert store.verify_chain()["ok"] is False
    with pytest.raises(ContextIntegrityError):
        store.query("cdev", "canon", "Canon")
    with pytest.raises(ContextIntegrityError):
        store.get("cdev", "canon", event_id)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload["event"]["attachments"].append({
            "ref": ["not", "text"],
            "extraction_status": "pending_extraction",
        }),
        lambda payload: payload["event"]["attachments"].append({
            "ref": "private://attachments/b.png",
            "extraction_status": ["not", "text"],
        }),
        lambda payload: payload["event"]["sources"].append({
            "source_id": "transcript",
            "source_kind": "transcript_locator",
            "locator": ["not", "text"],
            "extraction_status": "completed",
        }),
        lambda payload: payload["event"]["sources"].append({
            "source_id": "transcript",
            "source_kind": "transcript_locator",
            "locator": "turn:n-1",
            "extraction_status": {"not": "text"},
        }),
    ],
)
def test_malformed_attachment_and_source_rows_refuse_before_write(tmp_path, mutate) -> None:
    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    payload = _event()
    mutate(payload)

    with pytest.raises(ValueError):
        store.ingest(payload)
    assert _row_counts(db) == (0, 0)
