"""Launch grants and persistent evidence across independent MCP clients."""
import io
import json
import sqlite3

import pytest

from canon.client_mcp import ClientServer, main, parse_config, serve
from canon.context_store import ContextStore


def config(db, *extra):
    return parse_config(["--context-db", str(db), "--workspace-id", "workspace-a",
                         "--project-id", "project-a", *extra])


def event():
    return {"event_id": "turn-1", "source_app": "synthetic-client",
            "session_id": "synthetic-session", "native_id": "source-turn-1",
            "message_text": "Persist the azure telescope decision.",
            "extractions": [{"text": "azure telescope", "source_id": "message"}]}


def call(server, operation, **args):
    response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                              "params": {"name": "canon.context." + operation,
                                         "arguments": args}})["result"]
    return response, json.loads(response["content"][0]["text"])


def snapshot(directory):
    return {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}


def test_restart_persists_provenance_and_read_only_bytes(tmp_path):
    db = tmp_path / "context.sqlite"
    writer = ClientServer(config(db, "--context-write=true"))
    response, stored = call(writer, "ingest", event=event())
    assert response["isError"] is False
    assert stored["status"] == "stored"
    before = snapshot(tmp_path)
    reader = ClientServer(config(db, "--context-write=false"))
    response, found = call(reader, "query", query="azure telescope")
    assert response["isError"] is False
    assert found["hits"] and found["store_id"] == stored["store_id"]
    _, got = call(reader, "get", record_id=stored["event_record_id"])
    assert got["record"]["provenance"]["native_id"] == "source-turn-1"
    assert got["record"]["provenance"]["source_hash"] == stored["source_hash"]
    assert got["record"]["data"]["content_trust"] == "untrusted_source_evidence"
    assert got["does_not_prove"]
    assert call(reader, "health")[1]["ok"] is True
    assert snapshot(tmp_path) == before


def test_environment_cannot_grant_writes_or_purge(tmp_path, monkeypatch):
    db = tmp_path / "context.sqlite"
    ClientServer(config(db, "--allow-context-write"))
    for name in ("CANON_CONTEXT_MCP_PURGE", "CANON_CONTEXT_WRITE",
                 "CANON_ALLOW_CONTEXT_WRITE", "CANON_CONTEXT_MCP_WRITE"):
        monkeypatch.setenv(name, "apply")
    reader = ClientServer(config(db))
    before = snapshot(tmp_path)
    names = {t["name"] for t in reader.tools()}
    assert names == {"canon.context.health", "canon.context.query", "canon.context.get"}
    for operation in ("ingest", "purge", "export", "capture", "reconcile"):
        assert call(reader, operation, event=event())[0]["isError"] is True
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("args", [
    {"workspace_id": "other"}, {"project_id": "other"}, {"context_db": "elsewhere"},
    {"allow_context_write": True}, {"unknown": 1}, {"top_k": True},
])
def test_scope_and_unknown_arguments_refused(tmp_path, args):
    server = ClientServer(config(tmp_path / "ctx.db", "--allow-context-write"))
    assert call(server, "query", query="azure", **args)[0]["isError"] is True


def test_foreign_records_are_not_returned(tmp_path):
    db = tmp_path / "ctx.db"
    stored = ContextStore(db).ingest({"workspace_id": "foreign", "project_id": "project-a",
                                     "event": event()})
    server = ClientServer(config(db))
    assert call(server, "query", query="azure")[1]["hits"] == []
    assert call(server, "get", record_id=stored["event_record_id"])[1]["status"] == \
        "not_found_in_searched_sources"


def test_existing_042_store_reads_without_maintenance(tmp_path):
    # These ContextStore/schema/audit implementations are unchanged from v0.4.2.
    db = tmp_path / "existing-042.db"
    stored = ContextStore(db).ingest({"workspace_id": "workspace-a", "project_id": "project-a",
                                     "event": event()})
    before = snapshot(tmp_path)
    server = ClientServer(config(db))
    assert call(server, "health")[1]["ok"] is True
    assert call(server, "query", query="azure")[1]["hits"]
    _, got = call(server, "get", record_id=stored["event_record_id"])
    assert got["record"]["provenance"]["source_hash"] == stored["source_hash"]
    assert snapshot(tmp_path) == before


def test_missing_and_unidentified_databases_are_not_initialized(tmp_path):
    db = tmp_path / "missing.db"
    with pytest.raises((ValueError, OSError, sqlite3.Error)):
        ClientServer(config(db))
    assert not db.exists()
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE untouched(value TEXT)")
    before = snapshot(tmp_path)
    with pytest.raises(ValueError):
        ClientServer(config(db))
    assert snapshot(tmp_path) == before


def test_replacement_identity_is_refused_without_writes(tmp_path):
    db = tmp_path / "ctx.db"
    server = ClientServer(config(db, "--allow-context-write"))
    db.unlink()
    other = ContextStore(db)
    other.identity()
    before = snapshot(tmp_path)
    for operation, args in [("ingest", {"event": event()}), ("query", {"query": "azure"}),
                            ("health", {})]:
        assert call(server, operation, **args)[0]["isError"] is True
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("extra", ["--unknown", "--context-write=maybe", "--context-purge=true",
                                 "--context-w=true"])
def test_unknown_launch_flags_refused(tmp_path, extra):
    with pytest.raises(SystemExit) as exc:
        config(tmp_path / "ctx.db", extra)
    assert exc.value.code == 2
    assert not list(tmp_path.iterdir())


def test_stdio_handles_malformed_params_without_exposing_values(tmp_path):
    server = ClientServer(config(tmp_path / "ctx.db", "--allow-context-write"))
    requests = [{"id": 1, "method": "initialize"}, {"method": "notifications/initialized"},
                {"id": 2, "method": "tools/call", "params": ["secret-value"]},
                {"id": 3, "method": "tools/list"}]
    output = io.StringIO()
    assert serve(server, io.StringIO("\n".join(map(json.dumps, requests))), output) == 0
    responses = [json.loads(line) for line in output.getvalue().splitlines()]
    assert len(responses) == 3
    assert responses[0]["result"]["serverInfo"]["name"] == "canon-client"
    assert responses[1]["result"]["isError"] is True
    assert "secret-value" not in output.getvalue()


def test_help_exits_without_stdin(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert "--context-write" in capsys.readouterr().out


def test_environment_does_not_supply_launch_bindings(tmp_path, monkeypatch):
    monkeypatch.setenv("CANON_CONTEXT_DB", str(tmp_path / "ambient.db"))
    monkeypatch.setenv("CANON_WORKSPACE_ID", "workspace-a")
    monkeypatch.setenv("CANON_PROJECT_ID", "project-a")
    with pytest.raises(SystemExit) as exc:
        parse_config([])
    assert exc.value.code == 2
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("value", ["${CANON_WORKSPACE_ID}", "${user_config.project_id}",
                                 "scope\nname", "scope\x00name", "scope\x7fname"])
def test_unresolved_or_control_scope_binding_refused(tmp_path, value):
    with pytest.raises(SystemExit) as exc:
        parse_config(["--context-db", str(tmp_path / "ctx.db"), "--workspace-id", value,
                      "--project-id", "project-a"])
    assert exc.value.code == 2
    assert not list(tmp_path.iterdir())


def test_v1_store_is_not_migrated_by_client(tmp_path):
    from canon.context_migrate import store_identity

    db = tmp_path / "legacy.db"
    with sqlite3.connect(db) as conn:
        conn.executescript("CREATE TABLE records(key TEXT PRIMARY KEY, scope TEXT, id TEXT,"
                           "kind TEXT, envelope TEXT, sha256 TEXT);"
                           "CREATE TABLE audit(seq INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT,"
                           "sha256 TEXT, prev_hash TEXT, chain_hash TEXT);")
        store_identity(conn, create=True)
    before = snapshot(tmp_path)
    server = ClientServer(config(db))
    assert call(server, "query", query="azure")[1]["hits"] == []
    assert call(server, "health")[1]["ok"] is True
    assert snapshot(tmp_path) == before


def test_wal_store_read_without_sidecar_creation(tmp_path):
    db = tmp_path / "wal.db"
    ClientServer(config(db, "--allow-context-write"))
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.close()
    before = snapshot(tmp_path)
    assert call(ClientServer(config(db)), "health")[1]["ok"] is True
    assert snapshot(tmp_path) == before


def test_corrupted_audit_is_not_healthy_or_queryable(tmp_path):
    db = tmp_path / "ctx.db"
    server = ClientServer(config(db, "--allow-context-write"))
    call(server, "ingest", event=event())
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE audit SET chain_hash='broken'")
    before = snapshot(tmp_path)
    assert call(server, "health")[0]["isError"] is True
    assert call(server, "query", query="azure")[0]["isError"] is True
    assert call(server, "ingest", event={**event(), "event_id": "second"})[0]["isError"] is True
    assert snapshot(tmp_path) == before


def test_empty_db_replacement_cannot_be_initialized_by_old_writer(tmp_path):
    db = tmp_path / "ctx.db"
    server = ClientServer(config(db, "--allow-context-write"))
    db.unlink()
    db.touch()
    before = snapshot(tmp_path)
    assert call(server, "ingest", event=event())[0]["isError"] is True
    assert snapshot(tmp_path) == before


def test_reparse_component_refused_before_creation(tmp_path, monkeypatch):
    from canon import client_mcp_store

    db = tmp_path / "ctx.db"
    monkeypatch.setattr(client_mcp_store, "is_reparse_point", lambda path: path == tmp_path)
    with pytest.raises(SystemExit):
        config(db, "--allow-context-write")
    assert not db.exists()


def test_reparse_component_rechecked_on_each_call(tmp_path, monkeypatch):
    from canon import client_mcp_store

    db = tmp_path / "ctx.db"
    server = ClientServer(config(db, "--allow-context-write"))
    before = snapshot(tmp_path)
    monkeypatch.setattr(client_mcp_store, "is_reparse_point", lambda path: path == tmp_path)
    assert call(server, "ingest", event=event())[0]["isError"] is True
    assert call(server, "health")[0]["isError"] is True
    assert snapshot(tmp_path) == before


def test_read_profile_never_opens_live_sqlite_path(tmp_path, monkeypatch):
    from canon import client_mcp_store

    db = tmp_path / "ctx.db"
    ClientServer(config(db, "--allow-context-write"))
    original = sqlite3.connect
    calls = []

    def checked_connect(path, *args, **kwargs):
        calls.append(path)
        assert path == ":memory:"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(client_mcp_store.sqlite3, "connect", checked_connect)
    server = ClientServer(config(db))
    assert call(server, "health")[1]["ok"] is True
    assert call(server, "query", query="azure")[1]["hits"] == []
    assert calls


def _code(server, operation, **args):
    response, body = call(server, operation, **args)
    assert response["isError"] is True
    assert set(body) == {"error", "hint"}, body
    return body["error"]


def test_refusals_carry_fixed_codes_without_argument_values(tmp_path):
    db = tmp_path / "ctx.db"
    writer = ClientServer(config(db, "--allow-context-write"))
    secret = "planted-secret-value"
    assert _code(writer, "query", query="azure", workspace_id=secret) == "SCOPE_MISMATCH"
    assert _code(writer, "query", query="azure", project_id=secret) == "SCOPE_MISMATCH"
    assert _code(writer, "query", query="azure", unknown=secret) == "ARGUMENT_REFUSED"
    assert _code(writer, "query", query=7) == "ARGUMENT_REFUSED"
    assert _code(writer, "query", query="azure", top_k=99) == "ARGUMENT_REFUSED"
    assert _code(writer, "query", query="azure", expected_store_id=secret) == "STORE_ID_MISMATCH"
    reader = ClientServer(config(db))
    assert _code(reader, "ingest", event=event()) == "WRITE_NOT_GRANTED"
    for server in (writer, reader):
        response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                  "params": {"name": "canon.context.nope", "arguments": {}}})
        assert json.loads(response["result"]["content"][0]["text"])["error"] == "ARGUMENT_REFUSED"
    texts = [call(writer, "query", query="azure", workspace_id=secret)[0]["content"][0]["text"],
             call(reader, "ingest", event={"message_text": secret})[0]["content"][0]["text"]]
    assert all(secret not in text for text in texts)


def test_busy_store_and_unknown_failures_map_to_fixed_text():
    from canon.client_mcp import refusal_payload
    from canon.client_mcp_store import SnapshotBusy
    assert refusal_payload(SnapshotBusy("x"))["error"] == "STORE_BUSY"
    assert refusal_payload(sqlite3.OperationalError("database is locked"))["error"] == "STORE_BUSY"
    leaked = refusal_payload(ValueError("stored text planted-secret-value"))
    assert leaked == {"error": "context request refused or store unavailable"}
    assert refusal_payload(sqlite3.OperationalError("no such table: planted")) == leaked
