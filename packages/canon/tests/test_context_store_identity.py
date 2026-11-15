from __future__ import annotations

import shutil
import sqlite3
import hashlib
from concurrent.futures import ThreadPoolExecutor

import pytest

from canon.backends.base import record_key
from canon.backends.sqlite import SqliteBackend
from canon.context_records import make_records
from canon.context_store import ContextStore


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
            "attachments": [{
                "ref": "private://attachments/a.png",
                "extraction_status": "pending_extraction",
            }],
            "extractions": [{
                "source_id": "prompt",
                "text": text,
                "claim_state": "reported_by_source",
            }],
        },
    }


def _row_counts(db) -> tuple[int, int]:
    con = sqlite3.connect(str(db))
    counts = (
        con.execute("SELECT COUNT(*) FROM records").fetchone()[0],
        con.execute("SELECT COUNT(*) FROM audit").fetchone()[0],
    )
    con.close()
    return counts


def _identity_rows(db) -> list[tuple[str, str]]:
    con = sqlite3.connect(str(db))
    rows = con.execute(
        "SELECT key,value FROM context_store_meta ORDER BY key").fetchall()
    con.close()
    return rows


def _has_table(db, name: str) -> bool:
    con = sqlite3.connect(str(db))
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    con.close()
    return row is not None


def _legacy_write_without_identity(db) -> str:
    backend = SqliteBackend(db)
    records = make_records(_event())
    with backend._conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        for record in records:
            envelope = record.to_json()
            digest = hashlib.sha256(envelope.encode()).hexdigest()
            conn.execute(
                "INSERT INTO records(key,scope,id,kind,envelope,sha256)"
                " VALUES(?,?,?,?,?,?)",
                (record_key(record), record.scope, record.id, record.kind,
                 envelope, digest),
            )
            backend._append_audit(conn, record_key(record), digest)
    return records[0].id


def test_store_identity_is_persistent_and_stable_after_reconnect(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    first = ContextStore(db).identity()
    second = ContextStore(db).identity()

    assert first.startswith("ctxstore_")
    assert second == first
    assert _identity_rows(db) == [("store_id", first)]


def test_concurrent_first_identity_initialization_persists_one_value(tmp_path) -> None:
    db = tmp_path / "context.sqlite"

    with ThreadPoolExecutor(max_workers=6) as pool:
        identities = list(pool.map(lambda _: ContextStore(db).identity(), range(6)))

    assert len(set(identities)) == 1
    assert _identity_rows(db) == [("store_id", identities[0])]


def test_never_migrated_legacy_store_can_initialize_identity_once(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    _legacy_write_without_identity(db)
    assert not _has_table(db, "context_store_meta")
    assert not _has_table(db, "context_store_identity_version")

    store_id = ContextStore(db).identity()

    assert store_id.startswith("ctxstore_")
    assert _identity_rows(db) == [("store_id", store_id)]
    assert _has_table(db, "context_store_identity_version")


def test_established_identity_marker_refuses_missing_metadata_table(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    store_id = store.identity()
    store.ingest(_event(), expected_store_id=store_id)
    before = _row_counts(db)
    con = sqlite3.connect(str(db))
    con.execute("DROP TABLE context_store_meta")
    con.commit()
    con.close()

    with pytest.raises(ValueError, match="context store identity"):
        ContextStore(db).identity()

    assert _row_counts(db) == before
    assert not _has_table(db, "context_store_meta")
    assert _has_table(db, "context_store_identity_version")


def test_established_identity_refuses_missing_version_marker(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    original = ContextStore(db).identity()
    con = sqlite3.connect(str(db))
    con.execute("DROP TABLE context_store_identity_version")
    con.commit()
    con.close()

    with pytest.raises(ValueError, match="context store identity"):
        ContextStore(db).identity()

    assert _identity_rows(db) == [("store_id", original)]


def test_expected_store_id_matches_for_ingest_query_and_get(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    store_id = store.identity()
    captured = store.ingest(_event(), expected_store_id=store_id)

    assert captured["store_id"] == store_id
    assert store.query("cdev", "canon", "provider", expected_store_id=store_id)[
        "store_id"] == store_id
    assert store.get("cdev", "canon", captured["event_record_id"],
                     expected_store_id=store_id)["store_id"] == store_id


def test_mismatched_store_id_refuses_without_changing_records_or_identity(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    store_id = store.identity()
    store.ingest(_event(), expected_store_id=store_id)
    before = _row_counts(db)

    with pytest.raises(ValueError, match="context store identity"):
        store.ingest(_event("turn-2"), expected_store_id="ctxstore_" + "f" * 32)
    with pytest.raises(ValueError, match="context store identity"):
        store.query("cdev", "canon", "provider",
                    expected_store_id="ctxstore_" + "f" * 32)

    assert _row_counts(db) == before
    assert ContextStore(db).identity() == store_id


def test_same_path_replacement_with_new_store_id_refuses_bound_operation(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    original = ContextStore(db).identity()
    db.unlink()
    replacement = ContextStore(db)
    assert replacement.identity() != original

    with pytest.raises(ValueError, match="context store identity"):
        replacement.ingest(_event(), expected_store_id=original)
    assert _row_counts(db) == (0, 0)


def test_missing_or_tampered_identity_fails_closed_without_regeneration(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    original = ContextStore(db).identity()
    con = sqlite3.connect(str(db))
    con.execute("DELETE FROM context_store_meta WHERE key='store_id'")
    con.commit()
    con.close()

    with pytest.raises(ValueError, match="context store identity"):
        ContextStore(db).identity()

    con = sqlite3.connect(str(db))
    con.execute(
        "INSERT INTO context_store_meta(key,value) VALUES('store_id',?)",
        ("not-a-store-id",),
    )
    con.commit()
    con.close()
    with pytest.raises(ValueError, match="context store identity"):
        ContextStore(db).identity()
    assert ("store_id", original) not in _identity_rows(db)


def test_backup_clone_retains_logical_store_identity_boundary(tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    store = ContextStore(db)
    store_id = store.identity()
    store.ingest(_event(), expected_store_id=store_id)
    clone = tmp_path / "clone.sqlite"
    shutil.copyfile(db, clone)

    cloned = ContextStore(clone)
    assert cloned.identity() == store_id
    assert cloned.query("cdev", "canon", "Canon",
                        expected_store_id=store_id)["hits"]
