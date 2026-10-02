"""False-success controls for the frozen Articulate acceptance checker."""
import copy
import importlib
import json
from hashlib import sha256
from pathlib import Path

import pytest


def _checker():
    return importlib.import_module("scripts.check_frozen_articulate")


def _tool(value, refused=False):
    result = {"content": [{"type": "text", "text": json.dumps(value)}]}
    if refused:
        result["isError"] = True
    return result


def _initial():
    names = ["check", "score", "judge", "fix", "polish", "edit_plan", "edit_submit",
             "articulate.status", "articulate.doctor"]
    initialize = {"protocolVersion": "2025-06-18",
                  "serverInfo": {"name": "articulate", "version": "0.6.0"}}
    plan = {"ok": True, "backend": "host", "status": "host_edit_required", "attempts": [],
            "text": "The sample contains 14 records.", "masked_text": "The sample contains 14 records.",
            "plan_id": "fixture-token", "quality_status": "unassessed"}
    rows = {1: initialize, 2: {"tools": [{"name": name, "annotations": {
        "openWorldHint": False, "readOnlyHint": True, "destructiveHint": False,
        "idempotentHint": True}} for name in names]},
        3: _tool({"ok": True, "version": "0.6.0", "tool_set": "local", "local_only_switch": True,
                  "offline_editors": True, "editor_default": "host", "sampling_advertised": True})}
    rid = 4
    for tool in ("judge", "fix", "polish"):
        for backend in ("anthropic", "openai", "claude-cli", "sampling", "ollama"):
            rows[rid] = _tool({"ok": False, "error":
                f"{tool} backend '{backend}' is not available in local-only mode"}, True)
            rid += 1
    rows[19] = _tool(plan)
    rows[20] = _tool(plan)
    return rows


def _submissions():
    original = "The sample contains 14 records."
    good = "The sample has 14 records."
    def result(text, refused):
        return _tool({"ok": True, "text": text, "backend": "host", "refused": refused,
                      "receipt": {"backend": "host", "attempts": [], "quality_status": "unassessed",
                          "original_sha256": "sha256:" + sha256(original.encode()).hexdigest(),
                          "text_sha256": "sha256:" + sha256(text.encode()).hexdigest()}})
    return {1: _initial()[1], 2: result(good, []),
            3: result(original, [{"reasons": ["number changed"]}])}


def _wire(rows):
    return "".join(json.dumps({"jsonrpc": "2.0", "id": rid, "result": value}) + "\n"
                   for rid, value in rows.items())


def test_checker_accepts_only_complete_local_host_workflow():
    checker = _checker()
    rows = checker.parse_replies(_wire(_initial()), set(range(1, 21)))
    assert checker.validate_initial(rows, "0.6.0")["plan_id"] == "fixture-token"
    checker.validate_submissions(_submissions(), "0.6.0")


@pytest.mark.parametrize("fault", ["missing", "duplicate", "sampling", "wrong_id", "error", "bad_json"])
def test_transcript_rejects_missing_duplicate_or_unsolicited_responses(fault):
    wire = _wire({1: {}})
    if fault == "missing":
        wire = ""
    elif fault == "duplicate":
        wire += wire
    elif fault == "sampling":
        wire += json.dumps({"jsonrpc": "2.0", "id": 99, "method": "sampling/createMessage"})
    elif fault == "wrong_id":
        wire = wire.replace('"id": 1', '"id": true')
    elif fault == "error":
        wire = json.dumps({"jsonrpc": "2.0", "id": 1, "error": {"code": -1}})
    else:
        wire = "not json"
    with pytest.raises(RuntimeError):
        _checker().parse_replies(wire, {1})


@pytest.mark.parametrize("fault", ["version", "extra_tool", "missing_tool", "duplicate_tool", "online_hint",
                                  "wide_profile", "backend_success", "backend_wrong_error", "no_plan"])
def test_initial_validator_rejects_success_shaped_but_wrong_results(fault):
    rows = _initial()
    if fault == "version":
        rows[1]["serverInfo"]["version"] = "0.5.0"
    elif fault == "extra_tool":
        rows[2]["tools"].append({"name": "run_shell"})
    elif fault == "missing_tool":
        rows[2]["tools"].pop()
    elif fault == "duplicate_tool":
        rows[2]["tools"].append(copy.deepcopy(rows[2]["tools"][0]))
    elif fault == "online_hint":
        rows[2]["tools"][0]["annotations"]["openWorldHint"] = True
    elif fault == "wide_profile":
        rows[3] = _tool({"ok": True, "tool_set": "all"})
    elif fault == "backend_success":
        rows[4] = _tool({"ok": True, "text": "A rewrite"})
    elif fault == "backend_wrong_error":
        rows[4] = _tool({"ok": False, "error": "network failed"}, True)
    else:
        rows[19] = _tool({"ok": True})
    with pytest.raises(RuntimeError):
        _checker().validate_initial(rows, "0.6.0")


@pytest.mark.parametrize("fault", ["changed_number", "no_refusal", "bad_hash", "model_attempt", "wrong_good"])
def test_submission_validator_requires_numeric_refusal_and_bound_receipt(fault):
    rows = _submissions()
    rid = 2 if fault == "wrong_good" else 3
    payload = json.loads(rows[rid]["content"][0]["text"])
    if fault == "changed_number":
        payload["text"] = "The sample contains 15 records."
    elif fault == "no_refusal":
        payload["refused"] = []
    elif fault == "bad_hash":
        payload["receipt"]["text_sha256"] = "sha256:wrong"
    elif fault == "model_attempt":
        payload["receipt"]["attempts"] = [{"backend": "openai"}]
    else:
        payload["text"] = "The sample contains 14 records."
    rows[rid] = _tool(payload)
    with pytest.raises(RuntimeError):
        _checker().validate_submissions(rows, "0.6.0")


def test_check_uses_two_bounded_sessions_with_isolated_secret_free_environment(tmp_path, monkeypatch):
    checker = _checker()
    executable = tmp_path / "engine.exe"
    executable.write_bytes(b"fixture engine")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-sentinel")
    monkeypatch.setenv("PYTHONPATH", "untrusted-sentinel")
    calls = []
    def run(exe, args, home, env, wire, **limits):
        assert exe == executable.resolve()
        assert args == ["--bundled-lane-mcp", "articulate", "--local-only"]
        assert "ANTHROPIC_API_KEY" not in env and "PYTHONPATH" not in env
        assert Path(env["PATH"]).name == "System32"
        assert env["ARTICULATE_MCP_TOOLS"] == "all" and env["ARTICULATE_LOCAL_ONLY"] == "0"
        assert env["ARTICULATE_OLLAMA_URL"].startswith("http://127.0.0.1:")
        assert env["HTTPS_PROXY"] == env["ARTICULATE_OLLAMA_URL"]
        assert Path(env["FLYWHEEL_HOME"]).is_dir()
        assert limits == {"timeout": 30, "max_bytes": 2_000_000}
        calls.append([json.loads(line) for line in wire.splitlines()])
        return _wire(_initial() if len(calls) == 1 else _submissions())
    monkeypatch.setattr(checker, "run_mcp_process", run)
    receipt = {}
    checker.check(executable, "0.6.0", receipt)
    assert len(calls) == 2
    assert calls[0][0]["params"]["capabilities"] == {"sampling": {}}
    assert calls[1][-1]["params"]["arguments"]["rewrite"] == "The sample contains 15 records."
    assert receipt["executable_sha256"] == "sha256:" + sha256(b"fixture engine").hexdigest()
    assert receipt["observed_version"] == "0.6.0"
    assert receipt["isolated_runtime_removed"] is True
