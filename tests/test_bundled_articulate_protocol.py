"""Opt-in source protocol acceptance; this does not qualify a frozen executable.

Set FLYWHEEL_PYTHON_LANE_SOURCE_ROOT to the hash-pinned staged source root.
An explicit missing or mismatched source fails; an absent setting skips.
"""
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

import pytest

from harness.bundled_lane_descriptor import load_manifest_rows
from harness.mcp_client import LaunchSpec, MCPError, StdioTransport
from scripts.frozen_payload_datas import stage_dirs


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def staged_articulate():
    setting = os.environ.get("FLYWHEEL_PYTHON_LANE_SOURCE_ROOT")
    if setting is None:
        pytest.skip("explicit staged source required; frozen/installed acceptance remains unverified")
    assert setting.strip(), "staged source setting is empty"
    row = load_manifest_rows()["articulate"]
    checkout, src = stage_dirs(Path(setting), row)
    for item in row["component_descriptor"]["source"]["files"]:
        path = checkout / item["path"]
        assert path.is_file(), f"pinned source missing: {path}"
        assert "sha256:" + sha256(path.read_bytes()).hexdigest() == item["sha256"]
    return src


def _request(transport, rid, method, params):
    transport.send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
    try:
        reply = transport.receive()
    except MCPError as exc:
        pytest.fail(f"{exc}: {transport.stderr_tail()}")
    # A sampling/createMessage here is a failure, even if the server later refuses.
    assert reply.get("id") == rid and "method" not in reply, reply
    assert "error" not in reply, reply
    return reply["result"]


def _call(transport, rid, name, args, *, refused=False):
    result = _request(transport, rid, "tools/call", {"name": name, "arguments": args})
    assert bool(result.get("isError")) is refused, result
    return result.get("structuredContent") or json.loads(result["content"][0]["text"])


@pytest.mark.timeout(90)
def test_actual_entry_forces_local_protocol_and_refuses_all_model_backends(
        staged_articulate, tmp_path):
    violation = tmp_path / "external-attempt.txt"
    # Run the real packaging entry and actual staged modules. The audit tripwire
    # prevents network/child execution and records even a caught exception.
    bootstrap = """
import pathlib, runpy, sys
marker, entry = sys.argv[1:3]
def audit(event, args):
    blocked = event in ('socket.connect', 'socket.getaddrinfo', 'subprocess.Popen', 'os.system')
    blocked = blocked or (event == 'import' and args[0] == 'articulate.editing')
    if blocked:
        pathlib.Path(marker).write_text(event, encoding='utf-8')
        raise RuntimeError('external operation attempted')
sys.addaudithook(audit)
sys.argv = [entry, *sys.argv[3:]]
runpy.run_path(entry, run_name='__main__')
"""
    env = {key: value for key, value in os.environ.items()
           if key.upper() in {"PATH", "SYSTEMROOT", "TEMP", "TMP"}}
    env.update(PYTHONPATH=os.pathsep.join((str(staged_articulate), str(ROOT))),
               PYTHONUTF8="1", FLYWHEEL_HOME=str(tmp_path / "home"),
               ARTICULATE_MCP_TOOLS="all", ARTICULATE_LOCAL_ONLY="0")
    launch = LaunchSpec(
        (sys.executable, "-c", bootstrap, str(violation), str(ROOT / "packaging/gateway_entry.py"),
         "--bundled-lane-mcp", "articulate", "--local-only"),
        cwd=str(tmp_path), env_overrides=tuple(env.items()), inherit_env=False, hide_window=True)
    transport = StdioTransport(launch, timeout=20)
    try:
        initialized = _request(transport, 1, "initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {"sampling": {}},
            "clientInfo": {"name": "flywheel-local-contract-test", "version": "1"}})
        assert initialized["serverInfo"]["version"] == "0.6.0"
        transport.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools = _request(transport, 2, "tools/list", {})["tools"]
        assert {"edit_plan", "edit_submit"} <= {tool["name"] for tool in tools}
        assert all(not tool["annotations"]["openWorldHint"] for tool in tools)
        doctor = _call(transport, 3, "articulate.doctor", {})
        assert doctor["tool_set"] == "local" and doctor["local_only_switch"] is True
        assert doctor["sampling_advertised"] is True and doctor["editor_default"] == "host"
        rid = 4
        text = "Keep the source record."
        for name in ("judge", "fix", "polish"):
            for backend in ("anthropic", "openai", "claude-cli", "sampling", "ollama"):
                result = _call(transport, rid, name, {"text": text, "backend": backend},
                               refused=True)
                assert result["ok"] is False
                assert "not available in local-only mode" in result["error"]
                rid += 1
        automatic = _call(transport, rid, "fix", {"text": text, "backend": "auto"})
        assert automatic["status"] == "host_edit_required"
        plan = _call(transport, rid + 1, "edit_plan", {"text": text})
        assert plan["ok"] is True and plan["backend"] == "host"
        submitted = _call(transport, rid + 2, "edit_submit", {
            "text": text, "rewrite": plan["masked_text"], "plan_id": plan["plan_id"]})
        assert submitted["ok"] is True and submitted["text"] == text
        assert submitted["receipt"]["backend"] == "host"
        assert submitted["receipt"]["attempts"] == []
        assert submitted["receipt"]["quality_status"] == "unassessed"
        claims = "The change may help some users. It does not prove safety."
        rid += 3
        plan = _call(transport, rid, "edit_plan", {"text": claims})
        candidates = [
            ("The change may help some users, and it does not prove safety.", None),
            (claims.replace("may", "will"), "modal"),
            (claims.replace("some", "all"), "scope"),
            (claims.replace("does not", "does"), "negation"),
        ]
        for candidate, kind in candidates:
            rid += 1
            result = _call(transport, rid, "edit_submit", {
                "text": claims, "rewrite": candidate, "plan_id": plan["plan_id"]})
            assert result["text"] == (claims if kind else candidate)
            if kind:
                assert any(kind in reason for refusal in result["refused"]
                           for reason in refusal["reasons"])
            else:
                assert result["refused"] == []
            assert result["receipt"]["attempts"] == []
        assert not violation.exists(), violation.read_text() if violation.exists() else ""
    finally:
        transport.close()
