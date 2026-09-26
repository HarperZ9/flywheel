"""Lane call fixes from the correctness and security reviews.

- C4: the policy's ``timeout_s`` is the timeout a call gets, and a caller value
  is clamped to 1 .. ``timeout_s``;
- C8: a child that exits during a call is a tool error for that call, and does
  not mark the lane as unable to launch;
- C10: a bound key is recorded as validated only after a call to a tool that
  spends it (effect ``spend`` or ``model_call``);
- C13: a probe cache that cannot be written keeps its in-memory state;
- S8: a planted fake key reaches no response, probe cache, log line or file
  under the state folder, on a call that fails and on one that succeeds.
"""
from __future__ import annotations

import logging

import pytest

from harness.lane_call_route import handle_lane_call
from tests.test_lane_call_route import _Client, real_caller  # noqa: F401  (fixture)

FAKE = "sk-planted-fake-value-4242"


def _timeout_seen(monkeypatch, path, body):
    import harness.lane_caller as caller
    seen = {}

    def fake(lane, tool, args, *, timeout, governance_tier, bulletin_access=None, **_k):
        seen["timeout"] = timeout
        return {"ok": True}

    monkeypatch.setattr(caller, "call_lane_tool", fake)
    handle_lane_call(path, body)
    return seen["timeout"]


@pytest.mark.parametrize("path,body,expected", [
    ("/api/lane/index/index.map", {}, 120),
    ("/api/lane/relay/local_agent_run", {}, 300),
    ("/api/lane/crucible/crucible.assess", {}, 60),
    ("/api/lane/index/index.map", {"timeout": 999}, 120),
    ("/api/lane/index/index.map", {"timeout": 30}, 30),
    ("/api/lane/index/index.map", {"timeout": 0}, 1),
    ("/api/lane/gather/a_tool_added_later", {}, 20),
])
def test_the_policy_timeout_applies_and_bounds_a_caller_value(monkeypatch, path, body,
                                                              expected):
    assert _timeout_seen(monkeypatch, path, body) == expected


def test_a_child_that_exits_during_a_call_is_a_tool_error_not_a_launch_failure(
        real_caller, monkeypatch):
    import harness.mcp_client as mcp_client
    from harness.mcp_client import MCPError

    class _Dies(_Client):
        def call_text(self, tool, args):
            raise MCPError("server closed the connection")

    monkeypatch.setattr(mcp_client, "MCPClient", _Dies)
    body, status = handle_lane_call("/api/lane/gather/gather.docs", {})
    assert (status, body["code"], body["reason"]) == (
        502, "LANE_TOOL_ERROR", "server_exited_during_call")
    record, _fresh = real_caller.lookup("gather", "1.8.2")
    assert record is None


class _Bindings:
    def child_environment(self, base, *, platform):
        return {"FORUM_KEY": FAKE}

    def redact(self, text):
        return text.replace(FAKE, "[redacted]")


def test_only_a_tool_that_spends_the_key_validates_it(real_caller, monkeypatch):
    import harness.lane_caller as caller
    monkeypatch.setattr(caller, "call_lane_tool", lambda *a, **k: {"ok": True})
    body, status = handle_lane_call("/api/lane/forum/forum.route", {}, _Bindings())
    assert status == 200
    assert real_caller.validated("forum") == set()
    handle_lane_call("/api/lane/forum/plan", {}, _Bindings())
    assert real_caller.validated("forum") == {"FORUM_KEY"}


def test_a_cache_write_failure_keeps_the_record_in_memory(tmp_path, monkeypatch, caplog):
    import harness.lane_probe_cache as probes
    cache = probes.ProbeCache(tmp_path / "probes.json", engine="9.9.9")

    def refuse(*_a, **_k):
        raise PermissionError("sharing violation")

    monkeypatch.setattr(probes.os, "replace", refuse)
    caplog.set_level(logging.WARNING)
    cache.record("gather", "1.8.2", "answered", tools=["gather.docs"])
    record, fresh = cache.lookup("gather", "1.8.2")
    assert record["outcome"] == "answered" and fresh
    assert "probe cache" in caplog.text


def test_a_planted_key_reaches_no_answer_cache_log_or_state_file(
        real_caller, monkeypatch, tmp_path, caplog, capsys):
    import harness.lanes as lanes
    from harness.credential_handles import CredentialBindings
    from harness.mcp_client import LaunchSpec, MCPError
    monkeypatch.setattr(lanes, "read_registry", lambda: {"forum": {"env_allow": ["FORUM_KEY"]}})
    monkeypatch.setattr(lanes, "resolve_mcp_launch", lambda name: LaunchSpec(
        ("engine.exe", "--bundled-lane-mcp", name), inherit_env=False, allowed_tools=("plan",)))
    caplog.set_level(logging.DEBUG)
    _Client.result = {"ok": True, "text": '{"echo": "%s"}' % FAKE}
    bindings = CredentialBindings({"FORUM_KEY": FAKE})
    good, status = handle_lane_call("/api/lane/forum/plan", {"governance_tier": "T2"},
                                    bindings)
    _Client.error = MCPError("server closed: stderr tail " + FAKE)
    bad, _ = handle_lane_call("/api/lane/forum/plan", {"governance_tier": "T2"}, bindings)
    captured = capsys.readouterr()
    everything = [str(good), str(bad), caplog.text, captured.out, captured.err]
    for path in tmp_path.rglob("*"):
        if path.is_file():
            everything.append(path.read_text(encoding="utf-8", errors="replace"))
    assert status == 200
    assert not [text for text in everything if FAKE in text]
