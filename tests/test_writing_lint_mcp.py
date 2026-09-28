"""The stateless prose-lint MCP surface: initialize, list, lint, delta."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json  # noqa: E402

from harness.writing_lint import mcp  # noqa: E402


def _call(name, arguments):
    resp = mcp.handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": name, "arguments": arguments}})
    payload = resp["result"]["content"][0]["text"]
    return json.loads(payload)


def test_initialize_names_the_lint_server():
    resp = mcp.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    info = resp["result"]["serverInfo"]
    assert info["name"] == "writing-lint"
    assert resp["result"]["protocolVersion"] == mcp.PROTOCOL


def test_tools_list_exposes_lint_delta_profiles():
    resp = mcp.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in resp["result"]["tools"]}
    assert names == {"writing.lint", "writing.delta", "writing.profiles"}


def test_profiles_tool_lists_known_and_default():
    out = _call("writing.profiles", {})
    assert "flavored" in out["profiles"]
    assert out["default"] == "flavored"


def test_lint_scores_text_and_surfaces_structural_tells():
    out = _call("writing.lint",
                {"text": "We support arms, legs, and heads.", "profile": "readme"})
    assert out["per100w"] == 0.0
    assert out["violations"].get("rule_of_three", 0) >= 1
    assert out["report_per100w"] > 0.0
    assert "does_not_prove" in out


def test_lint_requires_text_or_path():
    out = _call("writing.lint", {"profile": "readme"})
    assert out["error"]["code"] == "LINT_FAILED"


def test_lint_unknown_profile_is_a_clean_error():
    out = _call("writing.lint", {"text": "Words here.", "profile": "no-such"})
    assert out["error"]["code"] == "UNKNOWN_PROFILE"


def test_delta_reports_the_change():
    out = _call("writing.delta",
                {"old_text": "We utilize the leverage of numerous tools.",
                 "new_text": "We use the tools.", "profile": "readme"})
    assert out["old"] > out["new"]
    assert out["delta"] < 0


def test_unknown_method_returns_jsonrpc_error():
    resp = mcp.handle_request({"jsonrpc": "2.0", "id": 9, "method": "no.such"})
    assert resp["error"]["code"] == -32601
