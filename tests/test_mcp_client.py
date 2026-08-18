"""test_mcp_client.py — the MCP client speaks the protocol, and the agent loop
can call an external MCP tool (gated + witnessed), with an injected fake server.

Success criteria:
  - initialize handshake, tools/list, tools/call flatten to text.
  - a server error raises MCPError; server-initiated notifications are skipped.
  - as_external_tools bridges tools into the executor; allow_mcp gates them.
  - end to end: the loop advertises the tool, calls it, and the ledger records it.
"""
import os
import subprocess

import pytest

from harness.local_loop import run_agent
from harness.local_tools import ToolExecutor, ToolGate
from harness.mcp_client import (
    LaunchSpec,
    MCPAllowlist,
    MCPClient,
    MCPError,
    StdioTransport,
    as_external_tools,
    open_mcp,
)


class _EmptyStream:
    def __iter__(self):
        return iter(())


class _FakeProc:
    stdin = None
    stdout = _EmptyStream()
    stderr = _EmptyStream()

    def poll(self):
        return None

    def terminate(self):
        pass

    def wait(self, timeout=None):
        return 0


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


def test_stdio_transport_launch_spec_forwards_cwd_and_merged_child_env(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda argv, **kwargs: seen.update(argv=argv, **kwargs) or _FakeProc(),
    )

    StdioTransport(
        LaunchSpec(("python", "-m", "demo"), "/repo", (("PYTHONPATH", "/repo"),))
    )

    assert seen["argv"] == ["python", "-m", "demo"]
    assert seen["cwd"] == "/repo"
    assert seen["env"]["PYTHONPATH"] == "/repo"


def test_stdio_transport_launch_spec_does_not_mutate_parent_environment(monkeypatch):
    monkeypatch.setenv("FLYWHEEL_MCP_TEST_VALUE", "parent")
    parent_env = dict(os.environ)
    seen = {}
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda argv, **kwargs: seen.update(argv=argv, **kwargs) or _FakeProc(),
    )

    StdioTransport(
        LaunchSpec(("python",), env_overrides=(("FLYWHEEL_MCP_TEST_VALUE", "child"),))
    )

    assert dict(os.environ) == parent_env
    assert seen["env"]["FLYWHEEL_MCP_TEST_VALUE"] == "child"


def test_stdio_transport_plain_argv_keeps_existing_popen_contract(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda argv, **kwargs: seen.update(argv=argv, kwargs=kwargs) or _FakeProc(),
    )

    StdioTransport(["python", "-m", "demo"])

    assert seen == {
        "argv": ["python", "-m", "demo"],
        "kwargs": {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "bufsize": 1,
        },
    }


def test_started_client_context_does_not_respawn_or_initialize_twice(monkeypatch):
    popen_calls = []
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda argv, **kwargs: popen_calls.append((argv, kwargs)) or _FakeProc(),
    )
    initialize_calls = 0

    def handler(req):
        nonlocal initialize_calls
        if req.get("method") == "initialize":
            initialize_calls += 1
        return _echo_server(req)

    client = MCPClient(LaunchSpec(("python", "-m", "demo")))
    client._t = FakeTransport(handler)
    client.start()

    with client as entered:
        assert entered is client

    assert len(popen_calls) == 1
    assert initialize_calls == 1


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


def test_allowlist_permits_prefix_and_denies_others():
    al = MCPAllowlist([["python", "-m", "myserver"]])
    assert al.permits(["python", "-m", "myserver", "--flag"])   # prefix match
    assert not al.permits(["python", "-m", "evil"])
    assert not al.permits(["rm", "-rf", "/"])
    assert not MCPAllowlist([]).permits(["python"])             # empty denies all


def test_open_mcp_refuses_non_allowlisted_before_spawning():
    al = MCPAllowlist([["python", "-m", "safe"]])
    with pytest.raises(MCPError):
        open_mcp(["python", "-m", "danger"], allowlist=al)      # raises without spawning


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
