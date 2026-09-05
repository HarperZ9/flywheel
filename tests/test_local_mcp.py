"""Falsifiers for the harness MCP server (agent-consumable over JSON-RPC).

Load-bearing: (1) initialize names the local-agent server; (2) tools/list
advertises health/chat/run; (3) the health tool returns the real tier report;
(4) a chat with no live backend is a typed error, not a crash; (5) unknown
method/tool are typed; (6) the serve loop round-trips JSON-RPC.
"""
import io
import json

from harness.local_agent import available_backends as _real_backends
from harness.local_mcp import PROTOCOL, __version__, handle, serve


def _req(method, rid=1, params=None):
    r = {"jsonrpc": "2.0", "method": method}
    if rid is not None:
        r["id"] = rid
    if params is not None:
        r["params"] = params
    return r


def test_initialize_and_tools_list():
    assert handle(_req("initialize"))["result"]["serverInfo"]["name"] == "local-agent"
    tools = {t["name"] for t in handle(_req("tools/list"))["result"]["tools"]}
    assert tools == {"local_agent_health", "local_agent_chat", "local_agent_run",
                     "local-model.status", "local-model.doctor"}


def test_lane_probe_finds_a_status_tool():
    # The lane roster reads a lane stale when its server exposes no status or
    # doctor tool, which is what local-model reported before these existed.
    # The names are the ones harness/lanes.py::_probe_lane looks for.
    tools = {t["name"] for t in handle(_req("tools/list"))["result"]["tools"]}
    assert {"local-model.status", "local-model.doctor"} & tools


def test_status_is_identity_and_doctor_adds_the_tiers():
    st = json.loads(handle(_req("tools/call", params={
        "name": "local-model.status", "arguments": {}}))["result"]["content"][0]["text"])
    assert st == {"ok": True, "server": "local-model", "version": __version__,
                  "protocol": PROTOCOL}
    doc = json.loads(handle(_req("tools/call", params={
        "name": "local-model.doctor", "arguments": {}}))["result"]["content"][0]["text"])
    assert doc["tiers_configured"] == ["ServeBackend", "OllamaBackend"]
    assert "unprobed" in doc["reachability"]
    assert "local_agent_run" in doc["tools"]


def test_doctor_pings_nothing():
    # The description says network-free. Point both tiers at dead ports: a
    # doctor that probed would stall or report them down, and it does neither.
    import harness.local_mcp as m
    from harness.local_agent import ServeBackend
    calls = []

    def dead(*a, **k):
        calls.append(1)
        return [ServeBackend(base_url="http://127.0.0.1:1")]
    m.__dict__["available_backends"] = dead
    try:
        doc = json.loads(handle(_req("tools/call", params={
            "name": "local-model.doctor", "arguments": {}}))["result"]["content"][0]["text"])
    finally:
        m.__dict__["available_backends"] = _real_backends
    assert doc["tiers_configured"] == ["ServeBackend"] and calls == [1]
    assert "unprobed" in doc["reachability"]


def test_health_tool_returns_tier_report():
    resp = handle(_req("tools/call", params={"name": "local_agent_health", "arguments": {}}))
    report = json.loads(resp["result"]["content"][0]["text"])
    assert "tiers" in report and {t["backend"] for t in report["tiers"]} >= {"serve", "ollama"}


def test_chat_with_no_backend_is_typed_error(monkeypatch):
    # force every backend unhealthy: point at dead local ports and no online
    import harness.local_mcp as m
    from harness.local_agent import ServeBackend

    def dead(*a, **k):
        return [ServeBackend(base_url="http://127.0.0.1:1"),
                ServeBackend(base_url="http://127.0.0.1:2")]
    monkeypatch.setattr(m, "available_backends", dead)
    resp = handle(_req("tools/call", params={"name": "local_agent_chat",
                                             "arguments": {"prompt": "hi"}}))
    assert resp["result"]["isError"] is True


def test_unknown_tool_and_method_are_typed():
    assert handle(_req("tools/call", params={"name": "nope", "arguments": {}}))["result"]["isError"]
    assert handle(_req("bogus"))["error"]["code"] == -32601


def test_serve_loop_roundtrips():
    stdin = io.StringIO(json.dumps(_req("initialize")) + "\n")
    out = io.StringIO()
    serve(stdin=stdin, stdout=out)
    assert json.loads(out.getvalue())["result"]["serverInfo"]["name"] == "local-agent"
