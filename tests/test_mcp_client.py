"""test_mcp_client.py — the MCP client speaks the protocol, and the agent loop
can call an external MCP tool (gated + witnessed), with an injected fake server.

Success criteria:
  - initialize handshake, tools/list, tools/call flatten to text.
  - a server error raises MCPError; server-initiated notifications are skipped.
  - as_external_tools bridges tools into the executor; allow_mcp gates them.
  - end to end: the loop advertises the tool, calls it, and the ledger records it.
"""
import pytest

from harness.local_loop import run_agent
from harness.local_tools import ToolExecutor, ToolGate
from harness.mcp_client import MCPClient, MCPError, as_external_tools


def _echo_server(req):
    m, rid = req.get("method"), req.get("id")
    if m == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": "2025-06-18",
            "serverInfo": {"name": "fake", "version": "1"},
            "capabilities": {"tools": {}}}}
    if m == "notifications/initialized":
        return None
    if m == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "tools": [{"name": "echo", "description": "echoes msg", "inputSchema": {}}]}}
    if m == "tools/call":
        p = req.get("params", {})
        if p.get("name") == "echo":
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": "echo: " + str(p.get("arguments", {}).get("msg", ""))}]}}
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "unknown tool"}}
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "unknown method"}}


class FakeTransport:
    """Synchronous in-process transport: the handler maps a request to a response
    (or None for a notification, or a list to inject extra out-of-band frames)."""

    def __init__(self, handler):
        self.handler = handler
        self.inbox = []

    def send(self, msg):
        resp = self.handler(msg)
        if resp is None:
            return
        self.inbox.extend(resp if isinstance(resp, list) else [resp])

    def receive(self):
        return self.inbox.pop(0)

    def close(self):
        pass


def _client(handler=_echo_server):
    return MCPClient(transport=FakeTransport(handler)).start()


def test_handshake_list_and_call():
    c = _client()
    assert c.server_info["name"] == "fake"
    tools = c.list_tools()
    assert [t["name"] for t in tools] == ["echo"]
    r = c.call_text("echo", {"msg": "hi"})
    assert r["ok"] is True and r["text"] == "echo: hi"


def test_error_raises_mcp_error():
    c = _client()
    with pytest.raises(MCPError):
        c.call_tool("nonexistent", {})


def test_notifications_are_skipped():
    def noisy(req):
        base = _echo_server(req)
        if req.get("method") == "tools/list":
            return [{"jsonrpc": "2.0", "method": "notifications/progress", "params": {}}, base]
        return base
    c = _client(noisy)
    assert [t["name"] for t in c.list_tools()] == ["echo"]   # skipped the notification


def test_construction_requires_command_or_transport():
    with pytest.raises(ValueError):
        MCPClient()


def test_as_external_tools_bridges_into_the_executor():
    c = _client()
    ext = as_external_tools(c)
    assert "echo" in ext
    ok, text = ext["echo"]["fn"]({"msg": "x"})
    assert ok and text == "echo: x"


def test_executor_gates_mcp_tools_until_allowed():
    c = _client()
    ext = as_external_tools(c)
    gated = ToolExecutor(external=ext, gate=ToolGate()).execute("echo", {"msg": "hi"})
    assert not gated.ok and "[gate]" in gated.output
    allowed = ToolExecutor(external=ext, gate=ToolGate(allow_mcp=True)).execute("echo", {"msg": "hi"})
    assert allowed.ok and "echo: hi" in allowed.output


class _StubAgent:
    system = "you are an agent"

    def __init__(self, script):
        self.script = list(script)

    def send(self, message):
        return {"content": [{"text": self.script.pop(0) if self.script else "done"}]}


def test_loop_advertises_calls_and_witnesses_an_mcp_tool():
    c = _client()
    ex = ToolExecutor(external=as_external_tools(c), gate=ToolGate(allow_mcp=True))
    agent = _StubAgent(['TOOL echo {"msg": "hey"}', "used the tool, done"])
    out = run_agent(agent, "use the echo tool", ex, max_steps=3)
    assert "echo" in agent.system                       # advertised to the model
    assert out["final"] == "used the tool, done"
    led = out["ledger"]
    assert any("echo: hey" in e.content for e in led.entries if e.kind == "tool_result")
