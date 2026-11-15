"""Read snapshots refresh, refuse concurrent changes, and never open live SQLite."""
import sqlite3

import pytest

from canon import client_mcp_store
from canon.client_mcp import ClientServer
from .test_client_mcp import call, config, event, snapshot


def test_long_running_reader_observes_later_authorized_ingest(tmp_path):
    db = tmp_path / "ctx.db"
    writer = ClientServer(config(db, "--allow-context-write"))
    reader = ClientServer(config(db))
    assert call(reader, "query", query="azure")[1]["hits"] == []
    stored = call(writer, "ingest", event=event())[1]
    assert call(reader, "query", query="azure")[1]["hits"]
    assert call(reader, "get", record_id=stored["event_record_id"])[1]["record"]


def test_wal_toggle_after_snapshot_does_not_create_reader_sidecars(tmp_path, monkeypatch):
    db = tmp_path / "ctx.db"
    ClientServer(config(db, "--allow-context-write"))
    reader = ClientServer(config(db))
    original = sqlite3.connect

    def toggle_before_memory_connect(path, *args, **kwargs):
        assert path == ":memory:"
        external = original(db)
        external.execute("PRAGMA journal_mode=WAL")
        external.close()
        return original(path, *args, **kwargs)

    monkeypatch.setattr(client_mcp_store.sqlite3, "connect", toggle_before_memory_connect)
    assert call(reader, "query", query="azure")[0]["isError"] is False
    assert set(snapshot(tmp_path)) == {"ctx.db"}
    # The store is now in WAL mode; the reader keeps working and adds no file.
    assert call(reader, "health")[0]["isError"] is False
    assert set(snapshot(tmp_path)) == {"ctx.db"}


def test_snapshot_size_limit_is_a_refusal(tmp_path, monkeypatch):
    db = tmp_path / "ctx.db"
    ClientServer(config(db, "--allow-context-write"))
    before = snapshot(tmp_path)
    monkeypatch.setattr(client_mcp_store, "MAX_SNAPSHOT_BYTES", 1)
    with pytest.raises(ValueError, match="at most 256 MiB"):
        ClientServer(config(db))
    assert snapshot(tmp_path) == before


def test_hot_journal_refused_as_busy_without_modification(tmp_path, monkeypatch):
    db = tmp_path / "ctx.db"
    ClientServer(config(db, "--allow-context-write"))
    (tmp_path / "ctx.db-journal").write_bytes(b"synthetic external activity")
    before = snapshot(tmp_path)
    monkeypatch.setattr(client_mcp_store, "SNAPSHOT_RETRY_SECONDS", 0.1)
    with pytest.raises(client_mcp_store.SnapshotBusy, match="busy"):
        ClientServer(config(db))
    assert snapshot(tmp_path) == before


def _mutate_on(db, attempts):
    """Append to the database during the snapshot read of the chosen attempts."""
    original, seen = client_mcp_store._hot_journal, []

    def hook(path):
        seen.append(path)
        if len(seen) % 2 == 0 and len(seen) // 2 in attempts:
            with db.open("ab") as stream:
                stream.write(b"external concurrent mutation")
        return original(path)
    return hook, seen


def test_mutation_during_snapshot_is_retried(tmp_path, monkeypatch):
    db = tmp_path / "ctx.db"
    writer = ClientServer(config(db, "--allow-context-write"))
    hook, seen = _mutate_on(db, attempts={1})
    monkeypatch.setattr(client_mcp_store, "_hot_journal", hook)
    reader = ClientServer(config(db))
    assert len(seen) >= 4  # the first attempt was retried
    monkeypatch.undo()
    assert call(reader, "health")[1]["ok"] is True
    assert writer


def test_mutation_on_every_attempt_is_refused_as_busy(tmp_path, monkeypatch):
    db = tmp_path / "ctx.db"
    ClientServer(config(db, "--allow-context-write"))
    hook, _ = _mutate_on(db, attempts=range(1, 10_000))
    monkeypatch.setattr(client_mcp_store, "_hot_journal", hook)
    monkeypatch.setattr(client_mcp_store, "SNAPSHOT_RETRY_SECONDS", 0.1)
    with pytest.raises(client_mcp_store.SnapshotBusy, match="busy"):
        ClientServer(config(db))


def test_invalid_snapshot_image_refused_without_modification(tmp_path):
    db = tmp_path / "invalid.db"
    db.write_bytes(b"invalid image!!!!!!!" + b"\x01\x01" + b"x" * 100)
    before = snapshot(tmp_path)
    with pytest.raises((ValueError, sqlite3.Error)):
        ClientServer(config(db))
    assert snapshot(tmp_path) == before
