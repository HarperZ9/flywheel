"""The lane routes that reach a lane session (WP10), driven through the real gates.

relay 0.3.0 takes its write and exec grants only from its launch. The engine
starts relay with both off (lane_workdir), and ``local_agent_start`` is T2: it
runs only on a call a granted T2 operation carries, which widens the launch for
that one call. Status and result are T1 reads of the run the session holds.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from harness import lane_tool_policy as policy
from harness.lane_session import LaneSessionPool
from harness.mcp_client import LaunchSpec

FAKE = Path(__file__).with_name("fake_session_mcp.py")


@pytest.fixture
def sessions(monkeypatch, tmp_path):
    """call_lane_tool against the fake relay: a frozen-shaped launch (the lane's
    T1 tools only) and a private session pool."""
    import harness.lane_session as lane_session
    import harness.lanes as lanes
    pool = LaneSessionPool(reaper=False)
    env = (("FAKE_CALL_LOG", str(tmp_path / "calls.log")),
           ("FAKE_PID_LOG", str(tmp_path / "pids.log")))

    def launch(name):
        return LaunchSpec((sys.executable, str(FAKE)), cwd=str(tmp_path), env_overrides=env,
                          allowed_tools=tuple(policy.admitted_tools(name)))

    monkeypatch.setattr(lanes, "resolve_mcp_launch", launch)
    monkeypatch.setattr(lane_session, "default_pool", lambda: pool)
    yield tmp_path
    pool.close_all()


def _call(lane, tool, args=None, tier="", **kw):
    from harness.lane_caller import call_lane_tool
    return call_lane_tool(lane, tool, args or {}, governance_tier=tier, timeout=10, **kw)


def _calls(tmp_path):
    log = tmp_path / "calls.log"
    return [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []


def test_relay_start_needs_a_granted_t2_call(sessions):
    result = _call("relay", "local_agent_start", {"goal": "g"})
    assert result.get("governance_denied") is True and "T2" in result["error"]
    assert _calls(sessions) == []


def test_start_status_and_result_reach_one_child_through_the_lane_route(sessions):
    started = _call("relay", "local_agent_start", {"goal": "g"}, tier="T2")
    run_id = started["run_id"]
    for _ in range(100):
        if _call("relay", "local_agent_status", {"run_id": run_id})["state"] == "done":
            break
        time.sleep(0.05)
    result = _call("relay", "local_agent_result", {"run_id": run_id})
    assert result["run_id"] == run_id and result["result"] == {"final": "did g"}
    assert len({row["pid"] for row in _calls(sessions)}) == 1


def test_relay_start_runs_with_write_exec_and_online_off_and_unlisted_args_dropped(sessions):
    _call("relay", "local_agent_start", {
        "goal": "g", "allow_write": True, "allow_exec": True, "online": True,
        "root": "C:/", "check": "del /q *", "test_cmd": "x"}, tier="T2")
    (row,) = _calls(sessions)
    assert row["args"] == {"goal": "g", "allow_write": False, "allow_exec": False,
                           "online": False}


def test_the_widened_start_does_not_admit_start_for_a_later_t1_call(sessions):
    _call("relay", "local_agent_start", {"goal": "g"}, tier="T2")
    again = _call("relay", "local_agent_start", {"goal": "g"})
    assert again.get("governance_denied") is True
    assert [row["tool"] for row in _calls(sessions)] == ["local_agent_start"]


@pytest.mark.parametrize("run_id", ["../x", "a/b", "", "x" * 80])
def test_a_run_id_must_be_a_plain_id(sessions, run_id):
    out = _call("relay", "local_agent_status", {"run_id": run_id})
    assert out["code"] == "LANE_TOOL_ERROR" and out["reason"] == "argument_refused"
    assert _calls(sessions) == []


def test_a_session_tool_never_takes_a_bound_key(sessions, monkeypatch):
    import harness.lane_credentials as creds
    monkeypatch.setattr(creds, "binds_any_key", lambda bindings: bindings is not None)
    monkeypatch.setattr(creds, "bind_lane_credentials", lambda lane, command, b: command)
    out = _call("relay", "local_agent_status", {"run_id": "r1"}, tier="T2",
                credential_bindings=object())
    assert out["code"] == creds.LaneCredentialError.code
    assert _calls(sessions) == []


def test_the_phone_relay_routes_read_the_same_session(sessions):
    from harness.gateway_lane_calls import _relay_mcp_call
    started = _call("relay", "local_agent_start", {"goal": "g"}, tier="T2")
    status = _relay_mcp_call("local_agent_status", {"run_id": started["run_id"]})
    runs = _relay_mcp_call("local_agent_runs", {})
    assert status["run_id"] == started["run_id"]
    assert [r["run_id"] for r in runs["runs"]] == [started["run_id"]]
    assert len({row["pid"] for row in _calls(sessions)}) == 1
    refused = _relay_mcp_call("local_agent_status", {"run_id": "../../x"})
    assert refused["reason"] == "argument_refused"


def test_the_phone_start_route_stays_refused():
    from harness.gateway_lane_calls import _relay_start_not_admitted

    class _Handler:
        def _req_json(self):
            return {"goal": "g"}, None

        def _json(self, body, status):
            return body, status

    body, status = _relay_start_not_admitted(_Handler())
    assert status == 403 and body["code"] == "CAPABILITY_NOT_ADMITTED"


@pytest.mark.parametrize("lane,tool", [("relay", "local_agent_status"),
                                       ("relay", "local_agent_runs"),
                                       ("index", "index.router.job.status")])
def test_plugins_and_agent_runs_cannot_reach_a_session_tool(lane, tool):
    from harness.lane_tier_gate import agent_tool_refusal, plugin_refusal
    refusal = plugin_refusal(lane, tool)
    assert refusal["code"] == "CAPABILITY_NOT_ADMITTED" and refusal["route"] == "lane.call"
    assert agent_tool_refusal(lane, "lane", [tool]) == "CAPABILITY_NOT_ADMITTED"


def test_session_tools_are_in_the_build_with_their_tiers():
    relay, index = policy.lane_policy("relay"), policy.lane_policy("index")
    assert relay["local_agent_start"].tier == "T2"
    for name in ("local_agent_start", "local_agent_status", "local_agent_result"):
        assert relay[name].not_in_build == ""
    assert relay["local_agent_status"].id_args == ("run_id",)
    assert relay["local_agent_start"].forced_args == (
        ("allow_write", False), ("allow_exec", False), ("online", False))
    admitted = policy.admitted_tools("relay")
    assert {"local_agent_status", "local_agent_result"} <= set(admitted)
    assert "local_agent_start" not in admitted
    for action in ("start", "status", "result", "cancel", "resume"):
        entry = index[f"index.router.job.{action}"]
        assert entry.tier == "T1" and entry.not_in_build == ""
    assert index["index.router.job.start"].path_args == ("root",)
    assert index["index.router.job.status"].id_args == ("job_id",)
    assert policy.validate_policy() == []
