"""Falsifiers for the harness MCP server (agent-consumable over JSON-RPC).

Load-bearing: (1) initialize names the local-agent server; (2) tools/list
advertises health/chat/run; (3) the health tool returns the real tier report;
(4) a chat with no live backend is a typed error, not a crash; (5) unknown
method/tool are typed; (6) the serve loop round-trips JSON-RPC.
"""
import io
import json
import sys
import subprocess
import os
import tomllib
from pathlib import Path

from relay.local_mcp import handle, serve


def _req(method, rid=1, params=None):
    r = {"jsonrpc": "2.0", "method": method}
    if rid is not None:
        r["id"] = rid
    if params is not None:
        r["params"] = params
    return r


def _stdio_vectors():
    return json.loads(
        (Path(__file__).parent / "fixtures" / "mcp_stdio_error_vectors.json")
        .read_text(encoding="utf-8"))




def _run_stdio_module(stdin_text: str):
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(root / "src")}
    if os.environ.get("PYTHONPATH"):
        env["PYTHONPATH"] += os.pathsep + os.environ["PYTHONPATH"]
    return subprocess.run(
        [sys.executable, "-u", "-m", "relay.local_mcp"],
        input=stdin_text,
        text=True,
        capture_output=True,
        cwd=root,
        env=env,
        timeout=12,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def test_initialize_and_tools_list():
    assert handle(_req("initialize"))["result"]["serverInfo"]["name"] == "local-agent"
    tools = {t["name"] for t in handle(_req("tools/list"))["result"]["tools"]}
    assert tools == {"local_agent_health", "local_agent_chat", "local_agent_run",
                     "local_agent_start", "local_agent_status", "local_agent_result",
                     "local_agent_runs", "local_agent_sessions",
                     "relay.status", "relay.doctor"}


def test_package_import_and_mcp_versions_match():
    import relay
    import relay.local_mcp as m
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]

    assert version == relay.__version__ == m.__version__
    assert handle(_req("initialize"))["result"]["serverInfo"]["version"] == version


def test_background_run_start_status_result(monkeypatch):
    # A phone starts a run and polls it. Stub run_agent so no live backend is
    # needed; the tool wiring, the run_id handoff, and the result projection are
    # what is under test.
    import time

    import relay.local_mcp as m

    def fake_run_agent(agent, goal, ex, ledger, *, max_steps=6):
        ledger.append("assistant", f"working on {goal}")
        return {"final": "done", "steps": 1, "verified": True, "final_answer": True,
                "chain_ok": True, "checkpoint": "abc123", "accepted": True, "ledger": ledger}

    monkeypatch.setattr(m, "run_agent", fake_run_agent)
    start = handle(_req("tools/call", params={"name": "local_agent_start",
                                              "arguments": {"goal": "fix the bug"}}))
    body = json.loads(start["result"]["content"][0]["text"])
    run_id = body["run_id"]
    assert body["state"] == "running" and run_id

    res = {"state": "running"}
    for _ in range(400):
        res = json.loads(handle(_req("tools/call", params={
            "name": "local_agent_result", "arguments": {"run_id": run_id}}))["result"]["content"][0]["text"])
        if res["state"] == "done":
            break
        time.sleep(0.005)
    assert res["state"] == "done"
    assert res["result"]["final"] == "done" and res["result"]["checkpoint"] == "abc123"
    assert "ledger" not in res["result"]  # the non-serializable ledger object is not leaked

    st = json.loads(handle(_req("tools/call", params={
        "name": "local_agent_status", "arguments": {"run_id": run_id}}))["result"]["content"][0]["text"])
    assert st["steps"] == 1 and st["state"] == "done"


def test_run_tool_description_does_not_overclaim_exec_sandbox():
    # The MCP description an auto-consuming client trusts must not claim a blanket
    # root sandbox that the run/exec tool does not honor (exec only sets cwd).
    from relay.local_mcp import TOOLS
    run_tool = next(t for t in TOOLS if t["name"] == "local_agent_run")
    desc = run_tool["description"]
    assert "tools sandboxed to root" not in desc
    assert "cwd" in desc.lower() or "not path-confined" in desc.lower()


def test_health_tool_returns_tier_report():
    resp = handle(_req("tools/call", params={"name": "local_agent_health", "arguments": {}}))
    report = json.loads(resp["result"]["content"][0]["text"])
    assert "tiers" in report and {t["backend"] for t in report["tiers"]} >= {"serve", "ollama"}


def test_chat_with_no_backend_is_typed_error(monkeypatch):
    # force every backend unhealthy: point at dead local ports and no online
    import relay.local_mcp as m
    from relay.local_agent import ServeBackend

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


def test_stdio_reports_malformed_json_and_keeps_server_alive_without_echoing_input():
    case = next(c for c in _stdio_vectors()["cases"] if c["name"] == "malformed_json_returns_parse_error_without_echo")
    stdin = io.StringIO(case["line"] + "\n"
                        + json.dumps(_req("initialize", rid=7)) + "\n")
    out = io.StringIO()

    serve(stdin=stdin, stdout=out)

    text = out.getvalue()
    lines = [json.loads(line) for line in text.splitlines()]
    assert lines[0]["id"] == case["expect_id"]
    assert lines[0]["error"]["code"] == case["expect_code"]
    assert case["secret"] not in text
    assert lines[1]["id"] == 7
    assert lines[1]["result"]["serverInfo"]["name"] == "local-agent"


def test_valid_json_nonrequest_is_invalid_request_with_null_id():
    case = next(c for c in _stdio_vectors()["cases"] if c["name"] == "valid_json_array_is_invalid_request")

    resp = handle(case["message"])

    assert resp["id"] == case["expect_id"]
    assert resp["error"]["code"] == case["expect_code"]


def test_invalid_object_requests_preserve_request_id_in_error():
    cases = [c for c in _stdio_vectors()["cases"]
             if c["name"] in {"missing_method_preserves_request_id",
                              "non_string_method_preserves_request_id"}]

    for case in cases:
        resp = handle(case["message"])
        assert resp["id"] == case["expect_id"]
        assert resp["error"]["code"] == case["expect_code"]


def test_mixed_stdio_notifications_do_not_emit_spurious_replies():
    stdin = io.StringIO(json.dumps(_req("notifications/initialized", rid=None)) + "\n"
                        + json.dumps(_req("tools/list", rid="after-notification")) + "\n")
    out = io.StringIO()

    serve(stdin=stdin, stdout=out)

    lines = [json.loads(line) for line in out.getvalue().splitlines()]
    assert len(lines) == 1
    assert lines[0]["id"] == "after-notification"


def test_relay_status_and_doctor_are_healthy_network_free():
    # The Flywheel lane probe marks a lane LIVE only if its MCP server answers a
    # status/doctor tool. relay.status is a network-free liveness+identity check.
    status = handle(_req("tools/call", params={"name": "relay.status"}))
    body = json.loads(status["result"]["content"][0]["text"])
    assert body["ok"] is True and body["server"] == "relay"
    assert body["version"] and body["protocol"]
    assert status["result"].get("isError") is not True

    doctor = handle(_req("tools/call", params={"name": "relay.doctor"}))
    dbody = json.loads(doctor["result"]["content"][0]["text"])
    assert dbody["ok"] is True
    assert "ServeBackend" in dbody["local_tiers"]  # configured local tiers, no ping
    assert "relay.status" in dbody["tools"]


def test_health_tools_are_advertised():
    names = {t["name"] for t in handle(_req("tools/list"))["result"]["tools"]}
    assert {"relay.status", "relay.doctor"} <= names


def test_doctor_reports_the_remote_surface_it_does_not_run(monkeypatch):
    """The seam the desktop client reads.

    The phone-facing surface is a separate process, so a client holding this
    stdio server had no way to ask whether it is on. The doctor carries the
    readout; what is under test here is that the block arrives, answers the
    configured question, and carries no secret with it.
    """
    monkeypatch.setenv("RELAY_ENV_FILE", "no-such-file.env")
    monkeypatch.delenv("RELAY_REMOTE_TOKEN", raising=False)
    off = handle(_req("tools/call", params={"name": "relay.doctor"}))
    body = json.loads(off["result"]["content"][0]["text"])
    assert body["remote"]["configured"] is False
    assert "RELAY_REMOTE_TOKEN" in body["remote"]["reason"]

    monkeypatch.setenv("RELAY_REMOTE_TOKEN", "sentinel-token-value")
    on = json.loads(
        handle(_req("tools/call", params={"name": "relay.doctor"}))
        ["result"]["content"][0]["text"])
    assert on["remote"]["configured"] is True
    # The value never travels, only the fact that the key is set.
    assert "sentinel-token-value" not in json.dumps(on)
    assert on["remote"]["keys_present"]["RELAY_REMOTE_TOKEN"] is True


def test_status_stays_a_liveness_check(monkeypatch):
    # relay.status is what the lane probe calls on every refresh. Reading the
    # environment there would make a liveness check depend on configuration.
    monkeypatch.setenv("RELAY_REMOTE_TOKEN", "t")
    body = json.loads(
        handle(_req("tools/call", params={"name": "relay.status"}))
        ["result"]["content"][0]["text"])
    assert "remote" not in body


def test_local_agent_runs_limit_is_strict(monkeypatch):
    import relay.local_mcp as m

    seen = {}

    class Registry:
        def list(self, *, limit=20):
            seen["limit"] = limit
            return {"runs": [], "count": 0}

    monkeypatch.setattr(m, "RUNS", Registry())
    ok = _decode_tool(handle(_req("tools/call", params={"name": "local_agent_runs",
                                                        "arguments": {"limit": 1}})))
    assert ok == {"runs": [], "count": 0}
    assert seen["limit"] == 1

    for bad in ("1", True, 1.2, -1):
        resp = handle(_req("tools/call", params={"name": "local_agent_runs",
                                                 "arguments": {"limit": bad}}))
        assert resp["result"]["isError"] is True
        body = _decode_tool(resp)
        assert body["error"]["code"] == "INVALID_ARGUMENT"


def _launch_grants(monkeypatch, **grants):
    # Write and exec are granted by whoever starts the server, not by arguments.
    import relay.local_mcp as m
    from relay.mcp_grants import StartGrants
    monkeypatch.setattr(m, "_GRANTS", StartGrants(root=m._GRANTS.root, **grants))


def _decode_tool(resp):
    return json.loads(resp["result"]["content"][0]["text"])


class _McpScriptedBackend:
    name = "stub"

    def __init__(self, replies, *, capture=None):
        self._replies = list(replies)
        self.capture = capture if capture is not None else {}

    def health(self):
        return True

    def chat(self, messages, *, system, max_tokens, temperature, seed):
        self.capture["max_tokens"] = max_tokens
        text = self._replies.pop(0) if self._replies else "done"
        return {"text": text, "model_ref": "stub:scripted", "seed": seed}


def test_run_and_start_schemas_expose_cli_parity_fields():
    schemas = {t["name"]: t["inputSchema"] for t in handle(_req("tools/list"))["result"]["tools"]}
    for tool in ("local_agent_run", "local_agent_start"):
        props = schemas[tool]["properties"]
        assert {"backend", "model", "max_tokens", "check", "test_cmd", "compact_budget"} <= set(props)


def test_blocking_run_passes_cli_parity_options_and_returns_request_binding(monkeypatch, tmp_path):
    import relay.local_mcp as m

    captured = {}

    def fake_available_backends(*, model=""):
        captured["model"] = model
        return [_McpScriptedBackend(["done"], capture=captured)]

    seen = {}

    def fake_run_agent(agent, goal, ex, ledger, *, max_steps=6, check=None, test_cmd=None,
                       approve=None, compact_budget=0):
        seen.update({
            "goal": goal,
            "root": ex.root,
            "allow_write": ex.gate.allow_write,
            "allow_exec": ex.gate.allow_exec,
            "max_steps": max_steps,
            "check": check,
            "test_cmd": test_cmd,
            "compact_budget": compact_budget,
            "prefer": agent.prefer,
            "max_tokens": agent.max_tokens,
        })
        ledger.append("assistant", "done", {"backend": "stub", "receipt": {"receipt_id": "rid", "model_ref": "stub:scripted"}})
        return {"final": "done", "steps": 1, "verified": True, "final_answer": True,
                "chain_ok": True, "checkpoint": "abc123", "accepted": True,
                "check_passed": True, "ledger": ledger}

    monkeypatch.setattr(m, "available_backends", fake_available_backends)
    monkeypatch.setattr(m, "run_agent", fake_run_agent)
    _launch_grants(monkeypatch, allow_write=True, allow_exec=True)
    resp = handle(_req("tools/call", params={"name": "local_agent_run", "arguments": {
        "goal": "fix the bug", "root": str(tmp_path), "backend": "stub",
        "model": "stub-model", "max_tokens": 123, "max_steps": 4,
        "allow_write": True, "allow_exec": True, "check": "pytest -q",
        "test_cmd": "pytest tests/test_bug.py", "compact_budget": 2048,
    }}))
    body = _decode_tool(resp)
    assert seen == {"goal": "fix the bug", "root": str(tmp_path), "allow_write": True,
                    "allow_exec": True, "max_steps": 4, "check": "pytest -q",
                    "test_cmd": "pytest tests/test_bug.py", "compact_budget": 2048,
                    "prefer": "stub", "max_tokens": 123}
    assert captured["model"] == "stub-model"
    binding = body["request_binding"]
    assert binding["schema"] == "relay.mcp-run-request/v2"
    assert binding["backend"] == "stub" and binding["model"] == "stub-model"
    assert binding["root"] == str(tmp_path)
    assert binding["allow_write"] is True and binding["allow_exec"] is True
    assert binding["max_steps"] == 4 and binding["max_tokens"] == 123
    assert binding["compact_budget"] == 2048
    assert binding["check_present"] is True and binding["test_cmd_present"] is True
    assert len(binding["goal_sha256"]) == 64
    assert body["observed_route"]["backend"] == "stub"
    assert body["observed_route"]["model_ref"] == "stub:scripted"
    assert body["accepted"] is True and body["check_passed"] is True


def test_background_start_passes_cli_parity_options_and_persists_request_binding(monkeypatch, tmp_path):
    import time

    from relay.async_runs import DONE, RunRegistry
    import relay.local_mcp as m

    captured = {}
    seen = {}

    monkeypatch.setattr(m, "RUNS", RunRegistry(id_source=lambda: "mcp-run",
                                               clock=lambda: 11,
                                               run_root=str(tmp_path / "runs")))

    def fake_available_backends(*, model=""):
        captured["model"] = model
        return [_McpScriptedBackend(["done"], capture=captured)]

    def fake_run_agent(agent, goal, ex, ledger, *, max_steps=6, check=None, test_cmd=None,
                       approve=None, compact_budget=0):
        seen.update({"goal": goal, "root": ex.root, "max_steps": max_steps,
                     "check": check, "test_cmd": test_cmd,
                     "compact_budget": compact_budget, "prefer": agent.prefer,
                     "max_tokens": agent.max_tokens})
        ledger.append("assistant", "done", {"backend": "stub", "receipt": {"model_ref": "stub:bg"}})
        return {"final": "done", "steps": 1, "verified": True, "final_answer": True,
                "chain_ok": True, "checkpoint": "abc123", "accepted": True,
                "check_passed": True, "ledger": ledger}

    monkeypatch.setattr(m, "available_backends", fake_available_backends)
    monkeypatch.setattr(m, "run_agent", fake_run_agent)
    _launch_grants(monkeypatch, allow_exec=True)
    start = handle(_req("tools/call", params={"name": "local_agent_start", "arguments": {
        "goal": "background fix", "root": str(tmp_path), "backend": "stub",
        "model": "stub-model", "max_tokens": 321, "max_steps": 5,
        "check": "pytest -q", "test_cmd": "pytest tests/test_bug.py",
        "compact_budget": 1024, "allow_exec": True,
    }}))
    body = _decode_tool(start)
    binding = body["request_binding"]
    assert body["run_id"] == "mcp-run" and binding["backend"] == "stub"

    result = {"state": "running"}
    for _ in range(400):
        result = _decode_tool(handle(_req("tools/call", params={
            "name": "local_agent_result", "arguments": {"run_id": "mcp-run"}})))
        if result["state"] == DONE:
            break
        time.sleep(0.005)

    assert result["state"] == DONE
    assert seen == {"goal": "background fix", "root": str(tmp_path),
                    "max_steps": 5, "check": "pytest -q",
                    "test_cmd": "pytest tests/test_bug.py",
                    "compact_budget": 1024, "prefer": "stub", "max_tokens": 321}
    assert captured["model"] == "stub-model"
    assert result["request_binding"] == binding
    assert result["result"]["request_binding"] == binding
    assert RunRegistry(run_root=str(tmp_path / "runs")).result("mcp-run")["request_binding"] == binding


def test_exec_grant_binding_reports_effective_write_authority(monkeypatch, tmp_path):
    import relay.local_mcp as m

    seen = {}

    def fake_run_agent(agent, goal, ex, ledger, *, max_steps=6):
        seen["allow_write"] = ex.gate.allow_write
        seen["allow_exec"] = ex.gate.allow_exec
        ledger.append("assistant", "done", {"backend": "stub", "receipt": {"model_ref": "stub:exec"}})
        return {"final": "done", "steps": 1, "verified": True, "final_answer": True,
                "chain_ok": True, "checkpoint": "abc123", "accepted": True,
                "check_passed": True, "ledger": ledger}

    monkeypatch.setattr(m, "available_backends", lambda *, model="": [_McpScriptedBackend(["done"])])
    monkeypatch.setattr(m, "run_agent", fake_run_agent)
    _launch_grants(monkeypatch, allow_exec=True)
    body = _decode_tool(handle(_req("tools/call", params={"name": "local_agent_run", "arguments": {
        "goal": "run a shell", "root": str(tmp_path), "backend": "stub",
        "allow_exec": True,
    }})))

    assert seen == {"allow_write": True, "allow_exec": True}
    assert body["request_binding"]["allow_exec"] is True
    assert body["request_binding"]["allow_write"] is True
    assert body["request_binding"]["requested_allow_write"] is None


def test_background_exec_grant_binding_reports_effective_write_authority(monkeypatch, tmp_path):
    import time

    from relay.async_runs import DONE, RunRegistry
    import relay.local_mcp as m

    monkeypatch.setattr(m, "RUNS", RunRegistry(id_source=lambda: "exec-bg",
                                               run_root=str(tmp_path / "runs")))

    def fake_run_agent(agent, goal, ex, ledger, *, max_steps=6):
        ledger.append("assistant", f"write={ex.gate.allow_write}")
        return {"final": "done", "steps": 1, "verified": True, "final_answer": True,
                "chain_ok": True, "checkpoint": "abc123", "accepted": True,
                "check_passed": True, "ledger": ledger}

    monkeypatch.setattr(m, "available_backends", lambda *, model="": [_McpScriptedBackend(["done"])])
    monkeypatch.setattr(m, "run_agent", fake_run_agent)
    _launch_grants(monkeypatch, allow_exec=True)
    start = _decode_tool(handle(_req("tools/call", params={"name": "local_agent_start",
                                                           "arguments": {
                                                               "goal": "run a shell",
                                                               "backend": "stub",
                                                               "allow_exec": True,
                                                           }})))
    assert start["request_binding"]["allow_write"] is True
    assert start["request_binding"]["requested_allow_write"] is None

    result = {"state": "running"}
    for _ in range(400):
        result = _decode_tool(handle(_req("tools/call", params={
            "name": "local_agent_result", "arguments": {"run_id": "exec-bg"}})))
        if result["state"] == DONE:
            break
        time.sleep(0.005)
    assert result["state"] == DONE
    assert result["request_binding"]["allow_write"] is True
    assert RunRegistry(run_root=str(tmp_path / "runs")).result("exec-bg")[
        "request_binding"]["allow_write"] is True


def test_mcp_write_denied_keeps_file_unchanged(monkeypatch, tmp_path):
    import relay.local_mcp as m

    monkeypatch.setattr(m, "available_backends", lambda *, model="": [
        _McpScriptedBackend(['TOOL write_file {"path": "x.txt", "content": "hi"}',
                             "write was denied"])
    ])
    resp = handle(_req("tools/call", params={"name": "local_agent_run", "arguments": {
        "goal": "write x", "root": str(tmp_path), "backend": "stub", "max_steps": 3,
        "allow_write": False,
    }}))
    body = _decode_tool(resp)
    assert not (tmp_path / "x.txt").exists()
    assert body["accepted"] is True
    assert body["request_binding"]["allow_write"] is False


def test_mcp_exec_denied_prevents_test_cmd_from_running(monkeypatch, tmp_path):
    import relay.local_mcp as m

    marker = tmp_path / "ran.txt"
    monkeypatch.setattr(m, "available_backends", lambda *, model="": [_McpScriptedBackend(["done"])])
    resp = handle(_req("tools/call", params={"name": "local_agent_run", "arguments": {
        "goal": "answer", "root": str(tmp_path), "backend": "stub", "max_steps": 2,
        "allow_exec": False, "test_cmd": f"python -c \"open(r'{marker}', 'w').write('ran')\"",
    }}))
    body = _decode_tool(resp)
    assert not marker.exists()
    assert body["accepted"] is False and body["check_passed"] is False
    assert "exec is disabled" in body.get("note", "")


def test_mcp_check_failure_cannot_be_accepted(monkeypatch, tmp_path):
    import relay.local_loop as loop
    import relay.local_mcp as m

    class Proc:
        returncode = 1
        stdout = ""
        stderr = "1 failed"

    calls = []
    def fake_run(cmd, *, shell, cwd, capture_output, text, timeout, env):
        calls.append((cmd, cwd))
        return Proc()

    monkeypatch.setattr(loop.subprocess, "run", fake_run)
    monkeypatch.setattr(m, "available_backends", lambda *, model="": [_McpScriptedBackend(["done"])])
    _launch_grants(monkeypatch, allow_exec=True)
    resp = handle(_req("tools/call", params={"name": "local_agent_run", "arguments": {
        "goal": "answer", "root": str(tmp_path), "backend": "stub", "max_steps": 2,
        "check": "pytest -q", "allow_exec": True,
    }}))
    body = _decode_tool(resp)
    assert calls == [("pytest -q", str(tmp_path))]
    assert body["check_passed"] is False and body["accepted"] is False


def test_mcp_unsupported_backend_is_typed_failure(monkeypatch):
    import relay.local_mcp as m

    monkeypatch.setattr(m, "available_backends", lambda *, model="": [_McpScriptedBackend(["done"])])
    resp = handle(_req("tools/call", params={"name": "local_agent_run", "arguments": {
        "goal": "answer", "backend": "missing-backend",
    }}))
    assert resp["result"]["isError"] is True
    body = _decode_tool(resp)
    assert body["error"]["code"] == "UNSUPPORTED_BACKEND"
    assert body["request_binding"]["backend"] == "missing-backend"


def test_mcp_argument_type_errors_are_typed(monkeypatch):
    import relay.local_mcp as m

    monkeypatch.setattr(m, "available_backends", lambda *, model="": [_McpScriptedBackend(["done"])])
    cases = [
        {"goal": ["not a string"]},
        {"goal": "answer", "backend": 3},
        {"goal": "answer", "model": 3},
        {"goal": "answer", "root": 3},
        {"goal": "answer", "check": ["pytest"]},
        {"goal": "answer", "test_cmd": ["pytest"]},
        {"goal": "answer", "max_steps": "4"},
        {"goal": "answer", "max_tokens": 3.7},
        {"goal": "answer", "compact_budget": -1},
        {"goal": "answer", "allow_write": "false"},
    ]
    for args in cases:
        resp = handle(_req("tools/call", params={"name": "local_agent_run", "arguments": args}))
        assert resp["result"]["isError"] is True
        body = _decode_tool(resp)
        assert body["error"]["code"] == "INVALID_ARGUMENT", args


def test_observed_route_reports_the_last_witnessed_assistant_route():
    import relay.local_mcp as m
    from relay.local_session import SessionLedger

    ledger = SessionLedger()
    ledger.append("assistant", "draft", {
        "backend": "stub-first",
        "receipt": {"receipt_id": "first", "model_ref": "model-first"},
    })
    ledger.append("tool", "read file")
    ledger.append("assistant", "final", {
        "backend": "stub-final",
        "receipt": {"receipt_id": "final", "model_ref": "model-final"},
    })

    projected = m.run_projection(
        {"final": "done", "steps": 2, "verified": True, "final_answer": True,
         "chain_ok": True, "checkpoint": "abc123", "accepted": True,
         "check_passed": True, "ledger": ledger})
    assert projected["observed_route"] == {
        "backend": "stub-final",
        "model_ref": "model-final",
        "receipt_id": "final",
        "source": "last_witnessed_assistant",
        "seq": 2,
    }


def test_request_id_validation_rejects_invalid_ids_without_echoing_input():
    case_names = {
        "object_request_id_uses_null_without_echo",
        "array_request_id_uses_null",
        "boolean_request_id_uses_null",
        "null_request_id_uses_null",
        "float_request_id_uses_null",
    }
    for case in _stdio_vectors()["cases"]:
        if case["name"] not in case_names:
            continue
        resp = handle(case["message"])
        text = json.dumps(resp)
        assert resp["id"] is None
        assert resp["error"]["code"] == case["expect_code"]
        if "secret" in case:
            assert case["secret"] not in text


def test_invalid_envelopes_and_params_return_protocol_errors():
    case_names = {
        "wrong_jsonrpc_version_is_invalid_request",
        "tools_call_array_params_is_invalid_params",
        "tools_call_null_params_is_invalid_params",
        "tools_call_scalar_params_is_invalid_params",
    }
    for case in _stdio_vectors()["cases"]:
        if case["name"] not in case_names:
            continue
        resp = handle(case["message"])
        assert resp["id"] == case["expect_id"]
        assert resp["error"]["code"] == case["expect_code"]


def test_known_method_notifications_do_not_dispatch_or_reply(monkeypatch):
    import relay.local_mcp as server_module
    calls = []

    def fake_call(params):
        calls.append(params)
        return {"content": []}

    monkeypatch.setattr(server_module, "_call", fake_call)
    assert handle({"jsonrpc": "2.0", "method": "tools/list"}) is None
    assert handle({"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "anything"}}) is None
    assert calls == []


def test_real_stdio_probe_vectors_keep_server_alive_and_clean_stdout():
    init = {"jsonrpc": "2.0", "id": 7, "method": "initialize"}
    for case in _stdio_vectors()["cases"]:
        first_line = case.get("line") or json.dumps(case["message"])
        proc = _run_stdio_module(first_line + "\n" + json.dumps(init) + "\n")
        assert proc.returncode == 0, proc.stderr
        assert "AttributeError" not in proc.stderr
        lines = [json.loads(line) for line in proc.stdout.splitlines()]
        if case.get("expect_response", True) is False:
            assert len(lines) == 1, case["name"]
            assert lines[0]["id"] == 7
            assert "result" in lines[0]
        else:
            assert len(lines) == 2, case["name"]
            assert lines[0]["id"] == case["expect_id"]
            assert lines[0]["error"]["code"] == case["expect_code"]
            assert lines[1]["id"] == 7
            assert "result" in lines[1]
        if "secret" in case:
            assert case["secret"] not in proc.stdout
            assert case["secret"] not in proc.stderr
