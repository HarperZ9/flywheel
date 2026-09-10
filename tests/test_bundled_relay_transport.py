import json
import os
import sys

import pytest


def test_launch_spec_allowed_tools_filters_list_and_refuses_unadmitted_call_before_transport():
    """Catches widening bundled Relay admission beyond relay.status."""
    from harness.mcp_client import LaunchSpec, MCPClient, MCPError

    class FakeTransport:
        def __init__(self):
            self.sent = []

        def send(self, msg):
            self.sent.append(msg)

        def receive(self):
            msg = self.sent[-1]
            method = msg.get("method")
            if method == "initialize":
                return {"jsonrpc": "2.0", "id": msg["id"],
                        "result": {"serverInfo": {"name": "local-agent",
                                                   "version": "0.2.0"}}}
            if method == "tools/list":
                return {"jsonrpc": "2.0", "id": msg["id"],
                        "result": {"tools": [
                            {"name": "relay.status", "description": "",
                             "inputSchema": {"type": "object"}},
                            {"name": "local_agent_start", "description": "",
                             "inputSchema": {"type": "object"}},
                        ]}}
            raise AssertionError(f"unexpected request: {method}")

        def close(self):
            pass

    transport = FakeTransport()
    client = MCPClient(
        LaunchSpec(("relay-child",), allowed_tools=("relay.status",)),
        transport=transport,
    ).start()

    tools = client.list_tools()

    assert [tool["name"] for tool in tools] == ["relay.status"]
    with pytest.raises(MCPError, match="CAPABILITY_NOT_ADMITTED"):
        client.call_text("local_agent_start", {})
    assert not any(
        msg.get("method") == "tools/call"
        and msg.get("params", {}).get("name") == "local_agent_start"
        for msg in transport.sent
    )


def test_child_environment_excludes_secret_sentinel_and_pythonpath():
    """Catches inherited secrets or source path injection in the bundled child."""
    from harness.bundled_lane_admission import bundled_child_environment

    env = bundled_child_environment({
        "SYSTEMROOT": "C:/Windows",
        "WINDIR": "C:/Windows",
        "COMSPEC": "C:/Windows/System32/cmd.exe",
        "PATHEXT": ".COM;.EXE",
        "SYSTEMDRIVE": "C:",
        "TEMP": "D:/t",
        "TMP": "D:/t",
        "PATH": "D:/shadow",
        "PYTHONPATH": "D:/malicious",
        "OPENAI_API_KEY": "sentinel-openai",
        "ANTHROPIC_API_KEY": "sentinel-anthropic",
        "RELAY_SESSION_DIR": "D:/private/sessions",
    }, platform="nt")

    assert "PYTHONPATH" not in env
    assert "OPENAI_API_KEY" not in env
    assert "ANTHROPIC_API_KEY" not in env
    assert "RELAY_SESSION_DIR" not in env
    assert env["PATH"] == "C:/Windows/System32"
    assert env["SYSTEMROOT"] == "C:/Windows"


def test_launch_spec_hide_window_passes_windows_flag(monkeypatch):
    """Catches losing CREATE_NO_WINDOW for the bundled child."""
    import harness.mcp_client as mcp_client
    from harness.mcp_client import LaunchSpec, StdioTransport

    captured = {}

    class FakeStdin:
        def write(self, _text):
            pass

        def flush(self):
            pass

    class FakeProc:
        stdin = FakeStdin()
        stdout = []
        stderr = []
        pid = 12345

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

        def kill(self):
            pass

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return FakeProc()

    monkeypatch.setattr(mcp_client.os, "name", "nt")
    monkeypatch.setattr(mcp_client.subprocess, "Popen", fake_popen)

    StdioTransport(LaunchSpec(("gateway.exe", "--bundled-lane-mcp", "relay"),
                              hide_window=True), timeout=0.1)

    assert captured["kwargs"]["creationflags"] == mcp_client.subprocess.CREATE_NO_WINDOW


def test_timed_out_child_is_closed():
    """Catches non-responsive stdio children left running after timeout."""
    from harness.mcp_client import LaunchSpec, MCPError, StdioTransport

    transport = StdioTransport(
        LaunchSpec((sys.executable, "-I", "-c",
                    "import time; time.sleep(30)"),
                   inherit_env=False,
                   env_overrides=(("PATH", os.environ.get("PATH", "")),)),
        timeout=0.1,
    )
    try:
        with pytest.raises(MCPError, match="no response"):
            transport.receive()
    finally:
        transport.close()

    assert transport.proc.poll() is not None
