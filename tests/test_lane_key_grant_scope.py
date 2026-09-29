"""Granted provider keys reach only the lane calls whose action spends them.

- Plugins (F5): a plugin call carries no tier, so it runs at T1, and the key
  rule (C-8) says a T1 call runs key-free. The frozen build's bundled launch
  already held every ``env_allow`` name and ``_restricted_launch`` passed it
  through, so ``mneme.remember`` through Plugins ran with the key. The plugin
  plan now strips key-shaped grants in both launch shapes.
- The gateway's forum and relay GET proxies launch the same way; they strip too,
  and refuse a tool the policy puts above T1 (F7: ``forum.run.room`` is T2) or
  an argument the id guard refuses, before anything spawns.
- The lane call route (F6): a T2 call kept every granted key whatever the tool
  did, an unlisted tool included. Now env-granted keys stay only for a listed
  tool whose effect spends a model call (``spend``, ``model_call``). A key the
  call binds through credential_refs still joins its one child. The approval
  sheet names an unlisted tool's effect as not reviewed.
"""
from __future__ import annotations

import pytest

import harness.lanes as lanes
from harness.mcp_client import LaunchSpec

KEY = "OPENAI_API_KEY"
SENTINEL = "sentinel-not-a-real-key-0123"


def _bundled(lane: str) -> LaunchSpec:
    return LaunchSpec(("engine.exe", "--bundled-lane-mcp", lane),
                      env_overrides=((KEY, SENTINEL), ("PYTHONUTF8", "1")),
                      inherit_env=False)


def _confined(lane: str) -> LaunchSpec:
    return LaunchSpec(("python.exe", "-m", f"{lane}.cli", "mcp"),
                      env_overrides=((KEY, SENTINEL), ("PATH", "C:/Windows")),
                      inherit_env=False)


@pytest.fixture()
def granted(monkeypatch):
    registry = {lane: {"env_allow": [KEY]} for lane in (
        "mneme", "forum", "relay", "articulate", "gather")}
    monkeypatch.setattr(lanes, "read_registry", lambda: registry)
    return registry


def _keys(launch) -> set[str]:
    return {k for k, v in launch.env_overrides if k.upper() == KEY and v}


@pytest.mark.parametrize("shape", [_bundled, _confined])
def test_a_plugins_lane_plan_carries_no_key(granted, monkeypatch, shape):
    from harness import plugins
    monkeypatch.setattr(plugins, "resolve_mcp_launch", lambda name: shape(name))
    launch = plugins.plugin_execution_plan("mneme")[0]
    assert not _keys(launch)


class _Spy:
    launches: list = []

    def __init__(self, launch, **_kwargs):
        _Spy.launches.append(launch)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def call_text(self, tool, arguments):
        return {"ok": True, "text": "{}"}


@pytest.fixture()
def spy(monkeypatch):
    _Spy.launches = []
    monkeypatch.setattr("harness.mcp_client.MCPClient", _Spy)
    return _Spy


def test_the_forum_and_relay_proxies_launch_key_free(granted, monkeypatch, spy):
    from harness import gateway_lane_calls as calls
    monkeypatch.setattr(lanes, "resolve_mcp_launch", lambda name: _bundled(name))
    calls._forum_mcp_call("forum.status", {})
    calls._relay_mcp_call("relay.doctor", {})
    assert len(spy.launches) == 2 and not any(_keys(l) for l in spy.launches)


def test_the_forum_proxy_refuses_a_t2_tool_before_it_spawns(granted, monkeypatch, spy):
    from harness import gateway_lane_calls as calls
    monkeypatch.setattr(lanes, "resolve_mcp_launch", lambda name: _confined(name))
    out = calls._forum_mcp_call("forum.run.room", {})
    assert out["code"] == "CAPABILITY_NOT_ADMITTED" and out["required_tier"] == "T2"
    assert spy.launches == []


def test_the_relay_proxy_refuses_a_run_id_that_is_not_plain(granted, monkeypatch, spy):
    from harness import gateway_lane_calls as calls
    monkeypatch.setattr(lanes, "resolve_mcp_launch", lambda name: _confined(name))
    out = calls._relay_mcp_call("local_agent_status", {"run_id": "../outside/ledger"})
    assert out.get("reason") == "argument_refused"
    assert spy.launches == []


def _launch_for(lane, tool, tier, monkeypatch, bindings=None):
    from harness import lane_caller
    monkeypatch.setattr(lanes, "resolve_mcp_launch", lambda name: _confined(name))
    return lane_caller._launch_for_call(lane, tool, tier, bindings)


@pytest.mark.parametrize(("lane", "tool"), [
    ("mneme", "mneme.forget"), ("gather", "gather.run"), ("mneme", "mneme.unlisted_tool")])
def test_a_t2_call_that_spends_nothing_gets_no_granted_key(granted, monkeypatch, lane, tool):
    launch = _launch_for(lane, tool, "T2", monkeypatch)
    assert isinstance(launch, LaunchSpec) and not _keys(launch)


@pytest.mark.parametrize(("lane", "tool"), [("articulate", "judge"), ("relay", "local_agent_start")])
def test_a_t2_call_that_spends_a_model_call_keeps_its_granted_key(
        granted, monkeypatch, lane, tool):
    launch = _launch_for(lane, tool, "T2", monkeypatch)
    assert isinstance(launch, LaunchSpec) and _keys(launch)


class _Bound:
    def child_environment(self, _env, platform="windows"):
        return {KEY: "bound-value"}

    def value_for(self, _slot):
        return "bound-value"

    def redact(self, text):
        return text.replace("bound-value", "[redacted]")


def test_a_bound_key_still_joins_a_call_that_names_it(granted, monkeypatch):
    launch = _launch_for("mneme", "mneme.forget", "T2", monkeypatch, _Bound())
    assert dict(launch.env_overrides)[KEY] == "bound-value"


def test_the_approval_sheet_says_an_unlisted_tool_was_not_reviewed():
    from harness.lane_tier_gate import lane_policy_review
    review = lane_policy_review({"name": "mneme", "tool": "mneme.unlisted_tool",
                                 "args": {}, "governance_tier": "T2"})
    assert review["listed"] is False and review["required_tier"] == "T2"
    assert review["effect"] == "not reviewed: effect unknown"
    assert review["keys"] == "granted keys stripped"
    listed = lane_policy_review({"name": "articulate", "tool": "judge", "args": {},
                                 "governance_tier": "T2"})
    assert listed["keys"] == "granted keys pass"
