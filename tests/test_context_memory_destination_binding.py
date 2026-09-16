import json
import os
import sys
from pathlib import Path

import pytest

import harness.context_memory_route as route
import harness.local_mcp as local_mcp
from harness.context_memory_bridge import (
    CAPTURE_SCHEMA,
    PREFLIGHT_SCHEMA,
    CanonContextMcpClient,
    ContextMemoryBridge,
    ContextMemoryConfig,
    ContextMemoryError,
)

OWNER = "owner_" + "a" * 32
STORE_ID = "ctxstore_" + "1" * 32
CANON_TEST_SRC_ENV = "FLYWHEEL_CANON_CONTEXT_TEST_SRC"
LEAK_SENTINEL = "C:/private/API_SECRET_ABC123-token"


class FakeCanonClient:
    def __init__(self):
        self.calls = []

    def health(self):
        return {"ok": True, "configured": True, "store_id": STORE_ID}

    def ingest(self, args):
        self.calls.append(("ingest", args))
        return {"status": "stored", "event_record_id": "context-event-flywheel-turn-1"}

    def query(self, args):
        self.calls.append(("query", args))
        return {"status": "found_in_searched_sources",
                "hits": [{"excerpt": "native bridge"}],
                "pending_extraction": []}


def _bridge(client):
    return ContextMemoryBridge(
        client=client,
        config=ContextMemoryConfig(workspace_id="cdev", project_id="flywheel-mission",
                                   project_aliases=("mission-memory",),
                                   owner_refs=(OWNER,),
                                   container_id="flywheel-desktop",
                                   db_path_sha256="d" * 64),
    )


def _destination(bridge):
    return bridge.health(OWNER)["destination_binding"]


def _capture_req(binding):
    return {"schema": CAPTURE_SCHEMA, "project_ref": "mission-memory",
            "config_generation": binding["config_generation"],
            "canon_store_id": binding["canon_store_id"],
            "event": {"event_id": "turn-1", "source_app": "flywheel",
                      "message_text": "Build native bridge"}}


def _preflight_req(binding):
    return {"schema": PREFLIGHT_SCHEMA, "project_ref": "mission-memory",
            "config_generation": binding["config_generation"],
            "canon_store_id": binding["canon_store_id"], "query": "native bridge"}


def _tool_error_client(error_text=LEAK_SENTINEL):
    script = (
        "import json, os, sys\n"
        "for line in sys.stdin:\n"
        "    req=json.loads(line)\n"
        "    name=req['params']['name']\n"
        "    if name == 'canon.context.health':\n"
        "        payload={'ok': True, 'configured': True, "
        "'store_id': os.environ['TEST_STORE_ID']}\n"
        "        result={'content':[{'type':'text','text':json.dumps(payload)}]}\n"
        "    else:\n"
        "        result={'isError': True, 'content':[{'type':'text',"
        "'text':os.environ['TEST_TOOL_ERROR']}]} \n"
        "    print(json.dumps({'jsonrpc':'2.0','id':req.get('id'),"
        "'result':result}), flush=True)\n"
    )
    return CanonContextMcpClient(
        command=[sys.executable, "-c", script],
        env={**os.environ, "TEST_STORE_ID": STORE_ID,
             "TEST_TOOL_ERROR": error_text},
        timeout_s=1,
    )


def test_owner_scoped_status_exposes_config_generation_and_canon_store_id():
    bridge = _bridge(FakeCanonClient())
    status = bridge.health(OWNER)

    assert status["destination_binding_configured"] is True
    binding = status["destination_binding"]
    assert binding["schema"] == "flywheel.context-memory-destination-binding/v1"
    assert binding["config_generation"] and len(binding["config_generation"]) == 64
    assert binding["canon_store_id"] == STORE_ID
    assert binding["same_store_check"] == "canon.expected_store_id.transaction/v1"
    assert "C:/dev" not in json.dumps(status)


def test_capture_and_preflight_bind_expected_canon_store_id_at_operation():
    client = FakeCanonClient()
    bridge = _bridge(client)
    binding = _destination(bridge)

    captured = bridge.capture(OWNER, _capture_req(binding))
    preflight = bridge.preflight(OWNER, _preflight_req(binding))

    assert captured["destination_binding_checked"]["canon_store_id"] == STORE_ID
    assert preflight["destination_binding_checked"]["canon_store_id"] == STORE_ID
    assert [call[1]["expected_store_id"] for call in client.calls] == [
        STORE_ID, STORE_ID]


def test_stale_config_generation_refuses_before_canon_call():
    client = FakeCanonClient()
    bridge = _bridge(client)
    request = _capture_req(_destination(bridge))
    request["config_generation"] = "0" * 64

    with pytest.raises(ContextMemoryError) as exc:
        bridge.capture(OWNER, request)

    assert exc.value.code == "CONTEXT_DESTINATION_CHANGED"
    assert client.calls == []


def test_malformed_destination_binding_refuses_before_canon_call():
    client = FakeCanonClient()
    bridge = _bridge(client)
    request = _preflight_req(_destination(bridge))
    request["canon_store_id"] = "store_abc"

    with pytest.raises(ContextMemoryError) as exc:
        bridge.preflight(OWNER, request)

    assert exc.value.code == "INVALID_DESTINATION_BINDING"
    assert client.calls == []


def test_canon_store_identity_mismatch_maps_to_destination_changed():
    script = (
        "import json, sys\n"
        "for line in sys.stdin:\n"
        "    req=json.loads(line)\n"
        "    print(json.dumps({'jsonrpc':'2.0','id':req.get('id'),"
        "'result':{'isError':True,'content':[{'type':'text',"
        "'text':'EXPECTED_STORE_ID mismatch C:/private/API_SECRET_ABC123'}]}}), flush=True)\n"
    )
    client = CanonContextMcpClient(command=[sys.executable, "-c", script],
                                   env=dict(os.environ), timeout_s=1)

    with pytest.raises(ContextMemoryError) as exc:
        client.query({"workspace_id": "cdev", "project_id": "p", "query": "x",
                      "expected_store_id": STORE_ID})

    assert exc.value.code == "CONTEXT_DESTINATION_CHANGED"
    assert exc.value.message == "Canon context destination changed"
    assert "API_SECRET_ABC123" not in exc.value.message
    assert "C:/private" not in exc.value.message


def test_http_tool_error_refusal_does_not_echo_canon_text():
    bridge = _bridge(_tool_error_client())

    body, status = route.context_memory_post(
        "/api/context-memory/capture",
        json.dumps(_capture_req(_destination(bridge))).encode(),
        owner_ref=OWNER, state_root="unused", clock=lambda: "now", bridge=bridge)

    raw = json.dumps(body)
    assert status == 502
    assert body["error"]["code"] == "CANON_CONTEXT_TOOL_ERROR"
    assert body["error"]["message"] == "Canon context tool failed"
    assert "API_SECRET_ABC123" not in raw
    assert "C:/private" not in raw


def test_mcp_tool_error_refusal_does_not_echo_canon_text(monkeypatch):
    bridge = _bridge(_tool_error_client())
    binding = _destination(bridge)
    monkeypatch.setattr(local_mcp, "_context_memory_bridge", lambda: bridge)

    response = local_mcp.handle({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "flywheel.context.capture",
            "arguments": {"owner_ref": OWNER, **_capture_req(binding)},
        },
    })

    raw = json.dumps(response)
    body = json.loads(response["result"]["content"][0]["text"])
    assert response["result"]["isError"] is True
    assert body["error"]["code"] == "CANON_CONTEXT_TOOL_ERROR"
    assert body["error"]["message"] == "Canon context tool failed"
    assert "API_SECRET_ABC123" not in raw
    assert "C:/private" not in raw


def _canon_src() -> Path:
    return Path(os.environ.get(CANON_TEST_SRC_ENV, ""))


def test_actual_canon_context_mcp_roundtrip_when_available(tmp_path):
    canon_src = _canon_src()
    if not (canon_src / "canon" / "context_mcp.py").exists():
        pytest.skip("Canon context MCP worktree source is unavailable")

    db = tmp_path / "context.sqlite"
    client = CanonContextMcpClient(env={**os.environ, "CANON_CONTEXT_DB": str(db),
                                        "PYTHONPATH": str(canon_src)})
    bridge = _bridge(client)
    binding = _destination(bridge)
    captured = bridge.capture(OWNER, {
        "schema": CAPTURE_SCHEMA,
        "project_ref": "mission-memory",
        "config_generation": binding["config_generation"],
        "canon_store_id": binding["canon_store_id"],
        "event": {"event_id": "turn-1", "source_app": "flywheel",
                  "message_text": "Actual cross-process Canon bridge",
                  "extractions": [{"source_id": "message",
                                   "text": "Actual cross-process Canon bridge"}]},
    })
    preflight = bridge.preflight(OWNER, {
        "schema": PREFLIGHT_SCHEMA,
        "project_ref": "mission-memory",
        "config_generation": binding["config_generation"],
        "canon_store_id": binding["canon_store_id"],
        "query": "cross-process Canon",
    })

    assert captured["status"] in {"stored", "already_present"}
    assert preflight["status"] == "found_in_searched_sources"


def test_actual_canon_same_path_store_replacement_refuses_bound_operation(tmp_path):
    canon_src = _canon_src()
    if not (canon_src / "canon" / "context_mcp.py").exists():
        pytest.skip("Canon context MCP worktree source is unavailable")

    db = tmp_path / "context.sqlite"
    client = CanonContextMcpClient(env={**os.environ, "CANON_CONTEXT_DB": str(db),
                                        "PYTHONPATH": str(canon_src)})
    bridge = _bridge(client)
    binding = _destination(bridge)
    bridge.capture(OWNER, _capture_req(binding))
    db.unlink()

    with pytest.raises(ContextMemoryError) as exc:
        bridge.preflight(OWNER, _preflight_req(binding))

    assert exc.value.code == "CONTEXT_DESTINATION_CHANGED"
