"""Falsifiers for the MCP server (agent-consumable mesh over JSON-RPC).

Load-bearing: (1) initialize reports the plexus server; (2) tools/list advertises
the four mesh tools with schemas; (3) tools/call actually runs discovery/plan/
route and returns JSON content; (4) a bad tool or bad method is a typed error, not
a crash; (5) notifications get no response. All via handle() — no pipes needed.
"""
import io
import json
import sys
import subprocess
import os
from pathlib import Path

from plexus.mcp import handle, serve


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
        [sys.executable, "-u", "-m", "plexus.mcp"],
        input=stdin_text,
        text=True,
        capture_output=True,
        cwd=root,
        env=env,
        timeout=12,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def test_initialize_reports_the_server():
    resp = handle(_req("initialize"))
    assert resp["result"]["serverInfo"]["name"] == "plexus"
    assert "protocolVersion" in resp["result"]


def test_tools_list_advertises_the_mesh_tools():
    tools = {t["name"] for t in handle(_req("tools/list"))["result"]["tools"]}
    assert tools == {"plexus_discover", "plexus_wiring", "plexus_plan", "plexus_route",
                     "plexus.status", "plexus.doctor"}


def test_call_discover_returns_the_real_mesh():
    resp = handle(_req("tools/call", params={"name": "plexus_discover", "arguments": {}}))
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert {"gather", "crucible", "forum", "index", "mneme"} <= set(payload["organs"])
    assert any(e["producer"] == "mneme" and e["consumer"] == "crucible" for e in payload["edges"])


def test_call_plan_and_route():
    plan = json.loads(handle(_req("tools/call", params={
        "name": "plexus_plan", "arguments": {"goal": "crucible"}}))["result"]["content"][0]["text"])
    assert "gather" in plan["order"]
    rt = json.loads(handle(_req("tools/call", params={
        "name": "plexus_route", "arguments": {"source": "gather", "target": "crucible"}}))["result"]["content"][0]["text"])
    assert rt["connected"] is True


def test_unknown_tool_and_method_are_typed_not_crashes():
    bad_tool = handle(_req("tools/call", params={"name": "nope", "arguments": {}}))
    assert bad_tool["result"]["isError"] is True
    bad_method = handle(_req("frobnicate"))
    assert bad_method["error"]["code"] == -32601


def test_notification_gets_no_response():
    assert handle(_req("notifications/initialized", rid=None)) is None


def test_serve_loop_reads_and_writes_jsonrpc():
    stdin = io.StringIO(json.dumps(_req("initialize")) + "\n"
                        + json.dumps(_req("tools/list", rid=2)) + "\n")
    out = io.StringIO()
    serve(stdin=stdin, stdout=out)
    lines = [json.loads(x) for x in out.getvalue().splitlines() if x.strip()]
    assert lines[0]["result"]["serverInfo"]["name"] == "plexus"
    assert lines[1]["id"] == 2 and "tools" in lines[1]["result"]


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
    assert lines[1]["result"]["serverInfo"]["name"] == "plexus"


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


def test_status_and_doctor_health_tools():
    # the Flywheel lane probe marks plexus LIVE only if a status/doctor tool answers
    for name in ("plexus.status", "plexus.doctor"):
        r = handle(_req("tools/call", params={"name": name}))
        body = json.loads(r["result"]["content"][0]["text"])
        assert body["ok"] is True and body["server"] == "plexus"
        assert r["result"].get("isError") is not True


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
    import plexus.mcp as server_module
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
