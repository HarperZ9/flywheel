import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from harness.context_memory_bridge import (
    CAPTURE_SCHEMA,
    PREFLIGHT_SCHEMA,
    CanonContextMcpClient,
    ContextMemoryBridge,
    ContextMemoryConfig,
    ContextMemoryError,
)

OWNER = "owner_" + "a" * 32
OTHER = "owner_" + "b" * 32
CANON_SRC = Path("C:/dev/worktrees/canon-shared-context-20260916/src")


class FakeCanonClient:
    def __init__(self):
        self.calls = []

    def health(self):
        return {"ok": True, "configured": True}

    def ingest(self, args):
        self.calls.append(("ingest", args))
        return {"status": "stored", "event_record_id": "context-event-flywheel-turn-1"}

    def query(self, args):
        self.calls.append(("query", args))
        if args["project_id"] != "flywheel-mission":
            return {"status": "not_found_in_searched_sources", "hits": []}
        return {"status": "found_in_searched_sources", "hits": [{"excerpt": "native bridge"}],
                "pending_extraction": []}


def _bridge(client):
    return ContextMemoryBridge(
        client=client,
        config=ContextMemoryConfig(workspace_id="cdev", project_id="flywheel-mission",
                                   project_aliases=("mission-memory",),
                                   owner_refs=(OWNER,)),
    )


def test_capture_writes_to_configured_canon_workspace_and_project():
    client = FakeCanonClient()
    result = _bridge(client).capture(OWNER, {
        "schema": CAPTURE_SCHEMA,
        "project_ref": "mission-memory",
        "event": {
            "event_id": "turn-1",
            "source_app": "flywheel",
            "message_text": "Build native bridge",
            "attachments": [{"ref": "private://frame/1",
                             "extraction_status": "pending_extraction"}],
        },
    })

    assert result["status"] == "stored"
    assert result["workspace_id"] == "cdev"
    assert result["project_ref"] == "mission-memory"
    assert result["scope_binding"]["canonical_project_id"] == "flywheel-mission"
    assert client.calls[0][1]["workspace_id"] == "cdev"
    assert client.calls[0][1]["project_id"] == "flywheel-mission"
    assert client.calls[0][1]["event"]["owner_ref"] == OWNER
    assert client.calls[0][1]["event"]["project_ref"] == "mission-memory"


def test_two_authorized_client_surfaces_share_literal_canonical_project():
    client = FakeCanonClient()
    bridge = _bridge(client)

    bridge.capture(OWNER, {
        "schema": CAPTURE_SCHEMA,
        "project_ref": "mission-memory",
        "event": {"event_id": "codex-turn-1", "source_app": "codex"},
    })
    bridge.capture(OWNER, {
        "schema": CAPTURE_SCHEMA,
        "project_ref": "mission-memory",
        "event": {"event_id": "claude-turn-1", "source_app": "claude"},
    })
    bridge.preflight(OWNER, {
        "schema": PREFLIGHT_SCHEMA,
        "project_ref": "mission-memory",
        "query": "native bridge",
    })

    assert [call[1]["project_id"] for call in client.calls] == [
        "flywheel-mission", "flywheel-mission", "flywheel-mission"]
    assert [call[1]["workspace_id"] for call in client.calls] == ["cdev", "cdev", "cdev"]


def test_preflight_not_found_is_bounded_to_configured_scope():
    client = FakeCanonClient()

    found = _bridge(client).preflight(OWNER, {
        "schema": PREFLIGHT_SCHEMA,
        "project_ref": "mission-memory",
        "query": "native bridge",
    })

    assert found["status"] == "found_in_searched_sources"
    assert "not_found does not mean never discussed" in found["does_not_prove"]


def test_legacy_found_current_status_is_reported_as_searched_sources():
    class LegacyStatusClient(FakeCanonClient):
        def query(self, args):
            self.calls.append(("query", args))
            return {"status": "found_current", "hits": [{"excerpt": "legacy"}]}

    result = _bridge(LegacyStatusClient()).preflight(OWNER, {
        "schema": PREFLIGHT_SCHEMA,
        "project_ref": "mission-memory",
        "query": "legacy status",
    })

    assert result["status"] == "found_in_searched_sources"

def test_request_cannot_select_unbound_canon_project_scope():
    client = FakeCanonClient()
    with pytest.raises(ContextMemoryError) as exc:
        _bridge(client).preflight(OWNER, {
            "schema": PREFLIGHT_SCHEMA,
            "project_ref": "other-project",
            "query": "native bridge",
        })

    assert exc.value.code == "CONTEXT_SCOPE_NOT_BOUND"
    assert client.calls == []


def test_cross_owner_denied_before_shared_canon_project_query():
    client = FakeCanonClient()
    with pytest.raises(ContextMemoryError) as exc:
        _bridge(client).preflight(OTHER, {
            "schema": PREFLIGHT_SCHEMA,
            "project_ref": "mission-memory",
            "query": "native bridge",
        })

    assert exc.value.code == "CONTEXT_OWNER_NOT_BOUND"
    assert client.calls == []


def test_config_does_not_accept_request_supplied_process_or_store_paths():
    client = FakeCanonClient()
    with pytest.raises(ContextMemoryError) as exc:
        _bridge(client).preflight(OWNER, {
            "schema": PREFLIGHT_SCHEMA,
            "project_ref": "mission-memory",
            "query": "native bridge",
            "canon_db": "C:/tmp/other.sqlite",
        })

    assert exc.value.code == "UNKNOWN_FIELD"
    assert client.calls == []


def test_scope_config_requires_explicit_workspace_and_project():
    client = FakeCanonClient()
    with pytest.raises(ContextMemoryError) as exc:
        ContextMemoryBridge(client=client, config=ContextMemoryConfig()).preflight(OWNER, {
            "schema": PREFLIGHT_SCHEMA,
            "project_ref": "mission-memory",
            "query": "native bridge",
        })

    assert exc.value.code == "CANON_CONTEXT_SCOPE_UNCONFIGURED"
    assert client.calls == []


def test_owner_binding_is_explicit_not_format_only():
    client = FakeCanonClient()
    config = ContextMemoryConfig(workspace_id="cdev", project_id="flywheel-mission",
                                 project_aliases=("mission-memory",))
    with pytest.raises(ContextMemoryError) as exc:
        ContextMemoryBridge(client=client, config=config).preflight(OWNER, {
            "schema": PREFLIGHT_SCHEMA,
            "project_ref": "mission-memory",
            "query": "native bridge",
        })

    assert exc.value.code == "CANON_CONTEXT_OWNER_UNCONFIGURED"
    assert client.calls == []


def test_canon_mcp_client_timeout_is_not_silent_empty(tmp_path):
    script = ("import time\n"
              "time.sleep(2)\n")
    client = CanonContextMcpClient(
        command=[sys.executable, "-c", script],
        env={**os.environ, "CANON_CONTEXT_DB": str(tmp_path / "context.sqlite")},
        timeout_s=0.01,
    )

    with pytest.raises(ContextMemoryError) as exc:
        client.query({"workspace_id": "cdev",
                      "project_id": "p", "query": "x"})

    assert exc.value.code == "CANON_CONTEXT_TIMEOUT"


def test_canon_mcp_client_rejects_tool_errors():
    script = (
        "import json, sys\n"
        "for line in sys.stdin:\n"
        "    req=json.loads(line)\n"
        "    print(json.dumps({'jsonrpc':'2.0','id':req.get('id'),"
        "'result':{'isError':True,'content':[{'type':'text','text':'bad args'}]}}), flush=True)\n"
    )
    client = CanonContextMcpClient(command=[sys.executable, "-c", script],
                                   env=dict(os.environ), timeout_s=1)

    with pytest.raises(ContextMemoryError) as exc:
        client.ingest({"workspace_id": "cdev",
                       "project_id": "p", "event": {"event_id": "t"}})

    assert exc.value.code == "CANON_CONTEXT_TOOL_ERROR"


def test_canon_mcp_client_hides_windows_child_console(monkeypatch):
    calls = []

    class Done:
        returncode = 0
        stdout = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {
            "content": [{"text": "{}"}]}}) + "\n"
        stderr = ""

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        return Done()

    monkeypatch.setattr("harness.context_memory_bridge.subprocess.run", fake_run)
    client = CanonContextMcpClient(command=["gateway.exe", "--canon-context-mcp"],
                                   env=dict(os.environ), timeout_s=1)

    client.health()

    assert calls[0][1]["creationflags"] == (
        subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)


def test_context_mcp_command_uses_source_module_until_frozen(tmp_path, monkeypatch):
    db = tmp_path / "context.sqlite"
    env = {**os.environ, "FLYWHEEL_CANON_CONTEXT_DB": str(db)}
    source = CanonContextMcpClient.from_environment(env)
    assert source.command == [sys.executable, "-m", "canon.context_mcp"]
    assert source.env["CANON_CONTEXT_DB"] == str(db)
    assert source.env["CANON_CONTEXT_SCOPE"] == "trusted-local-process"

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "D:/app/flywheel-gateway.exe")
    frozen = CanonContextMcpClient.from_environment(env)
    assert frozen.command == ["D:/app/flywheel-gateway.exe", "--canon-context-mcp"]


def test_actual_canon_context_mcp_roundtrip_when_available(tmp_path):
    if not (CANON_SRC / "canon" / "context_mcp.py").exists():
        pytest.skip("Canon context MCP worktree source is unavailable")

    db = tmp_path / "context.sqlite"
    client = CanonContextMcpClient(env={**os.environ, "CANON_CONTEXT_DB": str(db),
                                        "PYTHONPATH": str(CANON_SRC)})
    bridge = ContextMemoryBridge(
        client=client,
        config=ContextMemoryConfig(workspace_id="cdev", project_id="flywheel-mission",
                                   project_aliases=("mission-memory",), owner_refs=(OWNER,)),
    )
    captured = bridge.capture(OWNER, {
        "schema": CAPTURE_SCHEMA,
        "project_ref": "mission-memory",
        "event": {"event_id": "turn-1", "source_app": "flywheel",
                  "message_text": "Actual cross-process Canon bridge",
                  "extractions": [{"source_id": "message",
                                   "text": "Actual cross-process Canon bridge"}]},
    })
    preflight = bridge.preflight(OWNER, {
        "schema": PREFLIGHT_SCHEMA,
        "project_ref": "mission-memory",
        "query": "cross-process Canon",
    })

    assert captured["status"] in {"stored", "already_present"}
    assert preflight["status"] == "found_in_searched_sources"
