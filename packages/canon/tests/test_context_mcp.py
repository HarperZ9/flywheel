from __future__ import annotations

import hashlib
import io
import json
import sqlite3
from pathlib import Path

from canon import context_mcp
from canon.context_mcp import ENV_CONTEXT_DB, handle, serve


def _payload(result: dict) -> dict:
    return json.loads(result["content"][0]["text"])


def _call(name: str, arguments: dict | None = None) -> dict:
    req = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
           "params": {"name": name, "arguments": arguments or {}}}
    return handle(req)["result"]


def _tool(name: str, arguments: dict | None = None) -> dict:
    return _payload(_call(name, arguments))


def _ingest_args() -> dict:
    return {
        "workspace_id": "cdev",
        "project_id": "canon",
        "event": {
            "event_id": "turn-1",
            "source_app": "codex",
            "message_text": "Remember the shared-context MCP facade.",
            "attachments": [{"ref": "C:/private/image.png", "caption": "diagram"}],
            "extractions": [{
                "source_id": "message",
                "text": "Remember the shared-context MCP facade.",
                "claim_state": "reported_by_source",
            }],
        },
    }


def _insert_hash_consistent_bad_record(db) -> None:
    key = "workspace/context-event-corrupt"
    envelope = json.dumps({
        "canon_schema": "API_SECRET_ABC123",
        "kind": "episodic-memory",
        "id": "context-event-corrupt",
        "scope": "workspace",
        "data": {"workspace_id": "cdev", "project_id": "canon",
                 "event_record_id": "context-event-corrupt",
                 "text": "corrupt secret payload"},
        "provenance": {"harness": "codex", "source_hash": "a" * 64},
    }, sort_keys=True)
    digest = hashlib.sha256(envelope.encode()).hexdigest()
    chain = hashlib.sha256(("0" * 64 + key + digest).encode()).hexdigest()
    con = sqlite3.connect(str(db))
    con.execute(
        "INSERT INTO records(key,scope,id,kind,envelope,sha256)"
        " VALUES(?,?,?,?,?,?)",
        (key, "workspace", "context-event-corrupt", "episodic-memory",
         envelope, digest),
    )
    con.execute(
        "INSERT INTO audit(key,sha256,prev_hash,chain_hash) VALUES(?,?,?,?)",
        (key, digest, "0" * 64, chain),
    )
    con.commit()
    con.close()


def test_context_mcp_lists_only_the_context_tools() -> None:
    listed = handle({"id": 1, "method": "tools/list"})["result"]["tools"]
    assert [tool["name"] for tool in listed] == [
        "canon.context.health",
        "canon.context.ingest",
        "canon.context.query",
        "canon.context.get",
        "canon.context.purge",
    ]


def test_health_reports_missing_explicit_database_without_creating_cwd_file(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(ENV_CONTEXT_DB, raising=False)

    health = _tool("canon.context.health")
    assert health["ok"] is False
    assert health["configured"] is False
    assert not (tmp_path / "canon-context.sqlite").exists()


def test_ingest_query_and_get_use_the_configured_database(monkeypatch, tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    monkeypatch.setenv(ENV_CONTEXT_DB, str(db))

    ingest = _tool("canon.context.ingest", _ingest_args())
    assert ingest["status"] == "stored"
    query = _tool("canon.context.query", {
        "workspace_id": "cdev",
        "project_id": "canon",
        "query": "MCP facade",
    })
    assert query["status"] == "found_in_searched_sources"
    got = _tool("canon.context.get", {
        "workspace_id": "cdev",
        "project_id": "canon",
        "record_id": ingest["event_record_id"],
    })
    assert got["status"] == "found_in_searched_sources"
    assert got["record"]["data"]["attachments"][0]["ref"] == "C:/private/image.png"


def test_context_mcp_exposes_and_checks_store_identity(monkeypatch, tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    monkeypatch.setenv(ENV_CONTEXT_DB, str(db))
    health = _tool("canon.context.health")
    store_id = health["store_id"]

    ingest = _tool("canon.context.ingest", {
        **_ingest_args(),
        "expected_store_id": store_id,
    })
    query = _tool("canon.context.query", {
        "workspace_id": "cdev",
        "project_id": "canon",
        "query": "MCP facade",
        "expected_store_id": store_id,
    })
    got = _tool("canon.context.get", {
        "workspace_id": "cdev",
        "project_id": "canon",
        "record_id": ingest["event_record_id"],
        "expected_store_id": store_id,
    })

    assert store_id.startswith("ctxstore_")
    assert ingest["store_id"] == store_id
    assert query["store_id"] == store_id
    assert got["store_id"] == store_id


def test_context_mcp_store_identity_errors_are_sanitized(monkeypatch, tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    monkeypatch.setenv(ENV_CONTEXT_DB, str(db))
    _tool("canon.context.health")

    bad = _call("canon.context.ingest", {
        **_ingest_args(),
        "expected_store_id": "ctxstore_" + "f" * 32,
    })
    malformed = _call("canon.context.query", {
        "workspace_id": "cdev",
        "project_id": "canon",
        "query": "MCP facade",
        "expected_store_id": "../context.sqlite",
    })

    assert bad["isError"] is True
    assert bad["content"][0]["text"] == "context store identity mismatch"
    assert "ctxstore_" not in bad["content"][0]["text"]
    assert malformed["isError"] is True
    assert malformed["content"][0]["text"] == "expected_store_id is invalid"


def test_context_mcp_health_refuses_missing_established_identity(monkeypatch, tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    monkeypatch.setenv(ENV_CONTEXT_DB, str(db))
    store_id = _tool("canon.context.health")["store_id"]
    _tool("canon.context.ingest", {**_ingest_args(), "expected_store_id": store_id})
    con = sqlite3.connect(str(db))
    con.execute("DROP TABLE context_store_meta")
    con.commit()
    con.close()

    health = _tool("canon.context.health")

    assert health["ok"] is False
    assert health["configured"] is True
    assert health["reason"] == "context store identity invalid"
    assert "store_id" not in health


def test_context_mcp_sanitizes_corrupt_hash_consistent_records(monkeypatch, tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    monkeypatch.setenv(ENV_CONTEXT_DB, str(db))
    store_id = _tool("canon.context.health")["store_id"]
    _insert_hash_consistent_bad_record(db)
    health = _tool("canon.context.health")

    result = _call("canon.context.query", {
        "workspace_id": "cdev",
        "project_id": "canon",
        "query": "secret",
        "expected_store_id": store_id,
    })

    assert health["ok"] is False
    assert "API_SECRET_ABC123" not in json.dumps(health)
    assert result["isError"] is True
    assert result["content"][0]["text"] == "context store integrity failed"
    assert "API_SECRET_ABC123" not in result["content"][0]["text"]


def test_mcp_does_not_read_attachment_paths(monkeypatch, tmp_path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("do-not-read-this", encoding="utf-8")
    db = tmp_path / "context.sqlite"
    monkeypatch.setenv(ENV_CONTEXT_DB, str(db))
    args = _ingest_args()
    args["event"]["attachments"][0]["ref"] = str(secret)

    ingest = _tool("canon.context.ingest", args)
    got = _tool("canon.context.get", {
        "workspace_id": "cdev",
        "project_id": "canon",
        "record_id": ingest["event_record_id"],
    })
    assert "do-not-read-this" not in json.dumps(got)
    assert got["record"]["data"]["attachments"][0]["ref"] == str(secret)


def test_malformed_context_args_return_tool_errors(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(ENV_CONTEXT_DB, str(tmp_path / "context.sqlite"))

    result = _call("canon.context.query", {"workspace_id": "cdev", "query": "x"})
    assert result["isError"] is True
    assert "project_id" in result["content"][0]["text"]


def test_health_reports_configured_database_with_failed_integrity(monkeypatch, tmp_path) -> None:
    db = tmp_path / "context.sqlite"
    monkeypatch.setenv(ENV_CONTEXT_DB, str(db))
    ingest = _tool("canon.context.ingest", _ingest_args())
    con = sqlite3.connect(str(db))
    con.execute("DELETE FROM records WHERE id=?", (ingest["event_record_id"],))
    con.commit()
    con.close()

    health = _tool("canon.context.health")

    assert health["configured"] is True
    assert health["ok"] is False


def test_serve_round_trips_context_stdio(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(ENV_CONTEXT_DB, str(tmp_path / "context.sqlite"))
    lines = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": "canon.context.ingest", "arguments": _ingest_args()}}),
    ]
    out = io.StringIO()

    assert serve(io.StringIO("\n".join(lines) + "\n"), out) == 0
    replies = [json.loads(line) for line in out.getvalue().splitlines()]
    assert replies[0]["result"]["serverInfo"]["name"] == "canon-context"
    assert _payload(replies[1]["result"])["status"] == "stored"


def test_module_version_matches_packaged_version() -> None:
    pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml"
                 ).read_text(encoding="utf-8")
    declared = next(line.split("=", 1)[1].strip().strip('"')
                    for line in pyproject.splitlines()
                    if line.startswith("version"))
    assert context_mcp.__version__ == declared
