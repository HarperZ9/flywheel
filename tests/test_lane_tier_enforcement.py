"""The engine computes the tier a lane call needs, on every route.

Before this, the tier gate ran only when a caller sent ``governance_tier``,
Plugins and agent runs checked ``allowed_tools`` alone, and a relay run took
``allow_write`` and ``allow_exec`` from its arguments. Each test below is one
of those paths, driven through the real gate with a fake MCP client so nothing
is spawned.
"""
from __future__ import annotations

import sys

import pytest

from harness import lane_tool_policy as policy
from harness.lanes_registry import LANES
from harness.mcp_client import LaunchSpec


class _Recorder:
    """A fake MCP client that records each launch and call."""

    def __init__(self):
        self.calls: list[tuple[LaunchSpec, str, dict]] = []

    def factory(self, launch, **_kw):
        recorder = self

        class _Client:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def call_text(self, tool, args):
                recorder.calls.append((launch, tool, dict(args)))
                return {"ok": True, "text": '{"ok": true}'}

        return _Client()


@pytest.fixture
def lane_calls(monkeypatch):
    """call_lane_tool with a frozen-shaped launch: the lane's T1 tools only."""
    import harness.lanes as lanes
    import harness.mcp_client as mcp_client
    recorder = _Recorder()

    def frozen_launch(name):
        return LaunchSpec(("engine.exe", "--bundled-lane-mcp", name),
                          allowed_tools=tuple(policy.admitted_tools(name)))

    monkeypatch.setattr(lanes, "resolve_mcp_launch", frozen_launch)
    monkeypatch.setattr(mcp_client, "MCPClient", recorder.factory)
    return recorder


def _call(lane, tool, args=None, tier=""):
    from harness.lane_caller import call_lane_tool
    return call_lane_tool(lane, tool, args or {}, governance_tier=tier, timeout=1)


def test_a_call_without_a_tier_cannot_reach_a_t2_tool(lane_calls):
    result = _call("gather", "gather.run")
    assert result.get("governance_denied") is True
    assert "T2" in result["error"]
    assert lane_calls.calls == []


def test_a_granted_t2_call_widens_the_launch_for_that_call_only(lane_calls):
    assert _call("gather", "gather.run", {"config": {}}, tier="T2") == {"ok": True}
    assert _call("gather", "gather.docs", {"path": "x"}) == {"ok": True}
    (first, tool1, _), (second, tool2, _) = lane_calls.calls
    assert tool1 == "gather.run" and "gather.run" in first.allowed_tools
    assert tool2 == "gather.docs" and "gather.run" not in second.allowed_tools


def test_a_t2_grant_never_widens_a_tool_the_build_leaves_out(lane_calls):
    result = _call("calibrate-pro", "calibrate-pro.list-targets", tier="T2")
    assert result["code"] == "NOT_IN_BUILD"
    assert result["reason"] == "numpy_not_in_build"
    assert lane_calls.calls == []


def test_a_listed_t1_tool_runs_without_a_tier_on_a_t2_floor_lane(lane_calls):
    assert _call("relay", "relay.doctor") == {"ok": True}
    assert _call("accountable-surface", "accountable-surface.perceive",
                 {"subject": "."}) == {"ok": True}


def test_an_unlisted_tool_is_t2_whatever_the_lane_floor(lane_calls):
    from harness.lane_caller import required_tier
    assert required_tier("local-model", "a_tool_added_later") == "T2"
    assert required_tier("gather", "a_tool_added_later") == "T2"   # O-12
    assert required_tier("bulletin", "a_tool_added_later") == "T2"
    assert _call("local-model", "a_tool_added_later").get("governance_denied") is True
    assert _call("gather", "a_tool_added_later").get("governance_denied") is True


@pytest.mark.parametrize("lane", ["relay", "local-model"])
def test_an_agent_run_asking_for_exec_runs_with_write_and_exec_off(lane_calls, lane):
    args = {"goal": "list files", "allow_write": True, "allow_exec": True}
    assert _call(lane, "local_agent_run", args, tier="T2") == {"ok": True}
    _launch, tool, sent = lane_calls.calls[-1]
    assert tool == "local_agent_run"
    assert sent == {"goal": "list files", "allow_write": False, "allow_exec": False,
                    "online": False}
    assert args["allow_exec"] is True


def test_a_write_path_argument_is_dropped_on_a_t1_tool(lane_calls):
    _call("index", "index.map", {"root": ".", "resume_state": "C:/elsewhere/state.jsonl"})
    assert lane_calls.calls[-1][2] == {"root": "."}


def _plugin_lane(monkeypatch, recorder, lane):
    import harness.plugins as plugins
    launch = LaunchSpec(("lane-child", lane))
    monkeypatch.setattr(plugins, "plugin_execution_plan",
                        lambda name: (launch, "lane", (), ()))
    monkeypatch.setattr(plugins, "_launch", lambda command, *a, **k: command)
    return lambda tool, args=None: plugins.call_plugin(
        lane, tool, args or {}, client_factory=recorder.factory)


def test_plugins_cannot_reach_a_t2_lane_tool(monkeypatch):
    recorder = _Recorder()
    call = _plugin_lane(monkeypatch, recorder, "gather")
    result = call("gather.run", {"config": {}})
    assert result["code"] == "CAPABILITY_NOT_ADMITTED"
    assert result["required_tier"] == "T2"
    assert recorder.calls == []
    assert call("gather.docs", {"path": "x"})["tool"] == "gather.docs"


def test_plugins_force_relay_write_and_exec_off(monkeypatch):
    recorder = _Recorder()
    call = _plugin_lane(monkeypatch, recorder, "relay")
    call("local_agent_run", {"goal": "g", "allow_exec": True})
    assert recorder.calls[-1][2] == {"goal": "g", "allow_write": False, "allow_exec": False,
                                     "online": False}


def _catalog_lane(monkeypatch, tmp_path):
    import harness.plugins as plugins
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("FLYWHEEL_WORKSPACE_ROOT", str(workspace))
    launch = LaunchSpec((sys.executable, "-I", "-m", "lane"), inherit_env=False)
    monkeypatch.setattr(plugins, "plugin_execution_plan",
                        lambda name: (launch, "lane", (), ()))


@pytest.mark.parametrize("catalog,tool", [("gather", "gather.run"),
                                          ("accountable-surface", "accountable-surface.actuate"),
                                          ("relay", "local_agent_run"),
                                          ("index", "index.map"),
                                          ("relay", "local_agent_start")])
def test_an_agent_run_cannot_select_a_t2_guarded_or_left_out_lane_tool(
        monkeypatch, tmp_path, catalog, tool):
    from harness.gateway_agent_mcp_cache import restricted_catalog_launch
    from harness.gateway_operation import GatewayOperationError
    _catalog_lane(monkeypatch, tmp_path)
    with pytest.raises(GatewayOperationError, match="CAPABILITY_NOT_ADMITTED"):
        restricted_catalog_launch(catalog, [tool])


def test_an_agent_run_may_select_plain_t1_lane_tools(monkeypatch, tmp_path):
    from harness.gateway_agent_mcp_cache import restricted_catalog_launch
    _catalog_lane(monkeypatch, tmp_path)
    launch, kind = restricted_catalog_launch("forum", ["forum.route"])
    assert kind == "lane" and launch.allowed_tools == ("forum.route",)


def test_node_launches_carry_the_policy_t1_tools(tmp_path):
    from tests.test_node_lanes import _env, _finder, _stage
    from harness import node_lanes
    stage = _stage(tmp_path)
    for lane in ("learn", "telos"):
        res = node_lanes.resolve_node_lane(LANES[lane], "frozen", _env(tmp_path),
                                           stage_root=stage, find=_finder())
        assert res.launch.allowed_tools == tuple(policy.admitted_tools(lane))
    assert "learn_tutor_record" not in policy.admitted_tools("learn")
    assert "telos.native.control" not in policy.admitted_tools("telos")


def test_frozen_local_model_and_writing_launches_carry_the_policy_t1_tools(tmp_path):
    from harness import lane_runtime_frozen as lrf
    home, project = tmp_path / "home", tmp_path / "project"
    project.mkdir()
    (home / "lanes" / "local-model").mkdir(parents=True)
    (home / "lanes" / "local-model" / "root").write_text(str(project), encoding="utf-8")
    env = {"FLYWHEEL_HOME": str(home)}
    for lane in ("local-model", "writing"):
        launch, _sel, _comp, codes = lrf.select_frozen_launch(
            LANES[lane], "auto", "engine.exe", env, lambda module: True)
        assert codes == (), lane
        assert launch.allowed_tools == tuple(policy.admitted_tools(lane)), lane
    assert "flywheel.context.capture" not in policy.admitted_tools("local-model")


def test_relay_bundled_admission_follows_the_policy():
    from harness.bundled_lane_admission import ADMITTED_BUNDLED_RELAY_TOOLS
    from harness.bundled_lane_expectations import expected_bundled_lane
    assert ADMITTED_BUNDLED_RELAY_TOOLS == tuple(policy.admitted_tools("relay"))
    assert expected_bundled_lane("relay")["allowed_tools"] == ADMITTED_BUNDLED_RELAY_TOOLS
    assert "local_agent_start" not in ADMITTED_BUNDLED_RELAY_TOOLS


def test_the_listing_carries_each_lane_tool_tier():
    from harness.lane_caller import list_available_lanes
    listing = {row["name"]: row for row in list_available_lanes()}
    assert listing["gather"]["tool_tiers"]["gather.run"] == "T2"
    assert listing["relay"]["tool_tiers"]["local_agent_run"] == "T1"
    assert listing["bulletin"]["unlisted_tool_tier"] == "T2"
    assert listing["gather"]["unlisted_tool_tier"] == "T2"   # O-12
