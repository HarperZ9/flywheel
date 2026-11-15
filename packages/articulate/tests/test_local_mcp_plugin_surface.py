"""The stdio server behavior the Claude plugin relies on.

The plugin starts the server with ARTICULATE_MCP_TOOLS=local and
ARTICULATE_LOCAL_ONLY=1. The first lists only the tools that read the text and
nothing else; the second makes a hosted tool refuse before any network call even
if the listing were wrong. These tests pin both, and the protocol details a host
depends on: ping, a failed call marked as an error, a check result that stays
inside a host's output cap, and a doctor report a user can paste into an issue.
"""
import io
import json
import re
import subprocess

import pytest

from articulate import local_mcp, mcp_server, tool_meta

# Enough repeated findings to pass the default cap of 50 span records.
LONG = "By leveraging cutting-edge technology, teams move faster.\n\n" * 300


def _request(method, params=None):
    req = {"jsonrpc": "2.0", "id": 7, "method": method}
    if params is not None:
        req["params"] = params
    return local_mcp.handle(req)


def _call(name, arguments=None):
    return _request("tools/call", {"name": name, "arguments": arguments or {}})["result"]


def _payload(result):
    return json.loads(result["content"][0]["text"])


@pytest.fixture
def no_process(monkeypatch):
    """Any attempt to start the claude CLI fails the test."""
    def refuse(*args, **kwargs):
        raise AssertionError("a refused hosted call started a process")
    monkeypatch.setattr(subprocess, "Popen", refuse)
    monkeypatch.setattr(subprocess, "run", refuse)


@pytest.mark.parametrize("value, expected", [(None, "all"), ("", "all"), (" ALL ", "all"),
                                            ("local", "local"), ("lcoal", "local")])
def test_tool_set_typos_keep_editors_offline(value, expected):
    env = {} if value is None else {tool_meta.TOOLS_VAR: value}
    assert tool_meta.tool_set(env) == expected
    if expected == "local":
        assert all(not t["annotations"]["openWorldHint"] for t in local_mcp.listed_tools(env))


@pytest.mark.parametrize("name", ["fix", "judge", "polish"])
@pytest.mark.parametrize("switches", [{"ARTICULATE_MCP_TOOLS": "local"}, {"ARTICULATE_LOCAL_ONLY": "1"}])
@pytest.mark.parametrize("backend", [None, "auto", "host", "none"])
def test_local_editors_never_resolve_a_backend(monkeypatch, name, switches, backend):
    from articulate import backends
    for key in ("ARTICULATE_MCP_TOOLS", "ARTICULATE_LOCAL_ONLY"):
        monkeypatch.delenv(key, raising=False)
    for key, value in switches.items():
        monkeypatch.setenv(key, value)
    def fail(*a, **k):
        pytest.fail("local editor reached backend resolution")
    monkeypatch.setattr(backends, "complete", fail)
    args = {"text": "The cat sat."}
    if backend is not None:
        args["backend"] = backend
    session = local_mcp.Session(io.StringIO(), io.StringIO())
    session.initialized = session.sampling_advertised = True
    monkeypatch.setattr(session, "sample", fail)
    result = local_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                              "params": {"name": name, "arguments": args}}, session)["result"]
    payload = _payload(result)
    assert not result.get("isError"), payload
    assert payload["backend"] == ("none" if backend == "none" else "host")
    if backend != "none":
        assert payload["status"] == "host_edit_required"


@pytest.mark.parametrize("name", ["fix", "judge", "polish"])
@pytest.mark.parametrize("backend", ["sampling", "anthropic", "claude-cli", "openai", "ollama"])
@pytest.mark.parametrize("switch", ["ARTICULATE_MCP_TOOLS", "ARTICULATE_LOCAL_ONLY"])
def test_local_editors_refuse_explicit_connections_before_execution(monkeypatch, name, backend, switch):
    from articulate import editing
    monkeypatch.setenv(switch, "local" if switch == "ARTICULATE_MCP_TOOLS" else "1")
    def fail(*a, **k):
        pytest.fail("refused backend entered editing")
    monkeypatch.setattr(editing, "run_edit", fail)
    result = _call(name, {"text": "The cat sat.", "backend": backend})
    assert result["isError"] is True
    payload = _payload(result)
    assert payload["ok"] is False
    assert backend in payload["error"] and name in payload["error"]
    assert "local-only" in payload["note"]


def test_local_only_host_submit_accepts_good_and_refuses_bad(monkeypatch):
    monkeypatch.setenv("ARTICULATE_LOCAL_ONLY", "1")
    text = "The team leveraged 12 samples. See [report](https://example.com/report)."
    plan = _payload(_call("edit_plan", {"text": text}))
    good = _payload(_call("edit_submit", {"text": text, "rewrite": text.replace("leveraged", "used"), "plan_id": plan["plan_id"]}))
    assert good["receipt"]["backend"] == "host" and good["gate"] == "ok"
    bad = _payload(_call("edit_submit", {"text": text, "rewrite": "The team used 13 samples.", "plan_id": plan["plan_id"]}))
    assert bad["refused"] and bad["text"] == text


def test_a_successful_call_is_not_marked_as_an_error():
    assert "isError" not in _call("check", {"text": "The cat sat on the mat."})


def test_ping_gets_an_empty_result():
    assert _request("ping") == {"jsonrpc": "2.0", "id": 7, "result": {}}


def test_a_long_check_fits_inside_the_host_output_cap():
    result = _call("check", {"text": LONG})
    text = result["content"][0]["text"]
    payload = json.loads(text)
    full = mcp_server.do_check(LONG)
    assert len(full["hits"]) > 50, "the case no longer reaches the cap"
    assert len(payload["hits"]) == 50
    assert payload["hits"] == full["hits"][:50]
    assert payload["hits_omitted"] == len(full["hits"]) - 50
    assert payload["texture_score"] == full["texture_score"]
    assert payload["verdict"] == full["verdict"]
    # Claude Code warns above 10,000 tokens in one tool result. At roughly four
    # characters a token, 40,000 characters stays under that line.
    assert len(text) < 40_000, len(text)


@pytest.mark.parametrize("max_hits", [100, 1000])
def test_a_check_at_any_allowed_max_hits_fits_inside_the_host_output_cap(max_hits):
    text = _call("check", {"text": LONG, "max_hits": max_hits})["content"][0]["text"]
    payload = json.loads(text)
    full = mcp_server.do_check(LONG)
    assert len(text) < 40_000, len(text)
    shown = len(payload["hits"])
    assert shown >= 50, "the budget cut below the default"
    assert payload["hits"] == full["hits"][:shown]
    assert payload["hits_omitted"] == len(full["hits"]) - shown
    assert payload["texture_score"] == full["texture_score"]


def test_max_hits_zero_returns_the_counts_only():
    payload = _payload(_call("check", {"text": LONG, "max_hits": 0}))
    assert payload["hits"] == []
    assert payload["hits_omitted"] == len(mcp_server.do_check(LONG)["hits"])
    assert payload["texture_score"]


def test_a_short_check_has_no_omitted_count():
    assert "hits_omitted" not in _payload(_call("check", {"text": "The cat sat."}))


@pytest.mark.parametrize("value", [-1, 1001, "5", 2.5, True])
def test_an_out_of_range_max_hits_is_a_tool_error(value):
    result = _call("check", {"text": "The cat sat.", "max_hits": value})
    assert result["isError"] is True
    assert "max_hits" in result["content"][0]["text"]


def test_a_null_max_hits_means_the_default():
    # Some clients send null for an optional argument they leave unset.
    payload = _payload(_call("check", {"text": LONG, "max_hits": None}))
    assert len(payload["hits"]) == 50


def test_non_ascii_text_stays_readable_in_the_result():
    result = _call("check", {"text": "Our rÃ©sumÃ© service is cutting-edge."})
    text = result["content"][0]["text"]
    assert "rÃ©sumÃ©" in text, "the snippet was escaped or lost"
    assert "\\u00e9" not in text


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def test_doctor_reports_the_plugin_setup_without_a_path(monkeypatch):
    monkeypatch.setenv(local_mcp.TOOLS_VAR, "local")
    monkeypatch.setenv("ARTICULATE_LOCAL_ONLY", "1")
    doctor = _payload(_call("articulate.doctor"))
    assert doctor["tool_set"] == "local"
    assert doctor["hidden"] == []
    assert set(doctor["tools"]) >= {"edit_plan", "edit_submit", "fix", "judge", "polish"}
    assert doctor["local_only_switch"] is True
    assert re.fullmatch(r"\d+\.\d+\.\d+", doctor["python"])
    # The local set never looks the claude CLI up on the PATH.
    assert "backend_cli_found" not in doctor
    for value in _strings(doctor):
        assert "/" not in value and "\\" not in value, value


def _serve(lines):
    out = io.StringIO()
    assert local_mcp.serve(io.StringIO("".join(line + "\n" for line in lines)), out) == 0
    return [json.loads(line) for line in out.getvalue().splitlines() if line.strip()]


PING = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"})


def test_a_deeply_nested_request_is_a_parse_error_and_the_server_keeps_serving():
    deep = ('{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": '
            '"check", "arguments": {"text": "x", "extra": ' + "[" * 10_000
            + "]" * 10_000 + "}}}")
    answers = _serve([deep, PING])
    assert answers[0]["error"]["code"] == -32700, answers[0]
    assert answers[-1] == {"jsonrpc": "2.0", "id": 2, "result": {}}


def test_an_unexpected_failure_is_an_internal_error_and_the_server_keeps_serving(
        monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("planted failure")
    monkeypatch.setattr(local_mcp, "listed_tools", boom)
    answers = _serve([json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
                      PING])
    assert answers[0]["id"] == 1 and answers[0]["error"]["code"] == -32603, answers[0]
    assert "planted failure" not in json.dumps(answers[0])
    assert answers[-1] == {"jsonrpc": "2.0", "id": 2, "result": {}}
