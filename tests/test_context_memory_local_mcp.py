import json

import harness.local_mcp as local_mcp
from harness.context_memory_bridge import CAPTURE_SCHEMA, PREFLIGHT_SCHEMA

OWNER = "owner_" + "a" * 32


def _req(name, arguments):
    return {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": name, "arguments": arguments}}


def _payload(response):
    result = response["result"]
    return result, json.loads(result["content"][0]["text"])


class FakeBridge:
    def health(self, owner_ref=None):
        return {"ok": True, "configured": True, "owner_ref": owner_ref}

    def capture(self, owner_ref, req):
        return {"schema": "flywheel.context-memory-capture/v1",
                "status": "stored", "owner_ref": owner_ref,
                "project_ref": req["project_ref"]}

    def preflight(self, owner_ref, req):
        return {"schema": "flywheel.context-memory-preflight/v1",
                "status": "found_in_searched_sources",
                "hits": [{"excerpt": req["query"]}]}


def test_context_memory_tools_are_listed_with_no_process_path_arguments():
    tools = {tool["name"]: tool for tool in
             local_mcp.handle({"id": 1, "method": "tools/list"})["result"]["tools"]}

    assert {"flywheel.context.health", "flywheel.context.capture",
            "flywheel.context.preflight"} <= set(tools)
    for name in ("flywheel.context.capture", "flywheel.context.preflight"):
        props = tools[name]["inputSchema"]["properties"]
        assert tools[name]["inputSchema"]["additionalProperties"] is False
        assert "configured binding" in props["owner_ref"]["description"]
        assert "partition" not in props["owner_ref"]["description"]
        assert "canon_db" not in props
        assert "executable" not in props
        assert "path" not in props


def test_context_memory_mcp_uses_same_bridge_backend(monkeypatch):
    monkeypatch.setattr(local_mcp, "_context_memory_bridge",
                        lambda: FakeBridge())

    captured = local_mcp.handle(_req("flywheel.context.capture", {
        "owner_ref": OWNER,
        "schema": CAPTURE_SCHEMA,
        "project_ref": "mission-memory",
        "event": {"event_id": "turn-1"},
    }))
    preflight = local_mcp.handle(_req("flywheel.context.preflight", {
        "owner_ref": OWNER,
        "schema": PREFLIGHT_SCHEMA,
        "project_ref": "mission-memory",
        "query": "native bridge",
    }))

    capture_result, capture_body = _payload(captured)
    preflight_result, preflight_body = _payload(preflight)
    assert capture_result.get("isError") is not True
    assert preflight_result.get("isError") is not True
    assert capture_body["owner_ref"] == OWNER
    assert preflight_body["hits"][0]["excerpt"] == "native bridge"
