"""O-12: a lane tool the policy table does not list is T2 in every install mode.

A lane release can add a tool the table never classified. Before O-12 the
frozen build refused it (its launch admits only listed T1 tools) while a pip or
source install let it run at the lane floor, T1 on most lanes. Now the engine
computes T2 for it whatever the install, so it runs only on a call the owner
approved at T2, and the frozen build still never ships it. Plugins and agent
runs keep refusing it outright (C-11).

Each install mode's launch comes from the real runtime resolver where it can
(pip and source); the frozen launch is the bundled shape the resolver returns
in a frozen build. A fake MCP client records what would spawn.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from harness import lane_runtime
from harness import lane_tool_policy as policy
from harness.lanes_registry import LANES
from harness.mcp_client import LaunchSpec
from tests.test_lane_tier_enforcement import (  # noqa: F401  (fixture)
    _Recorder, _catalog_lane, _plugin_lane)

NEW_TOOL = "a_tool_added_later"


def _resolve(lane: str, tmp_path: Path, *, source: bool) -> LaunchSpec:
    """The pip or source launch the real resolver picks for ``lane``."""
    checkout = None
    if source:
        checkout = tmp_path / "src-checkout"
        checkout.mkdir(exist_ok=True)
        (checkout / "pyproject.toml").write_text(
            f'[project]\nname = "x"\nversion = "{LANES[lane].version}"\n', encoding="utf-8")
    runtime = lane_runtime.resolve_lane_runtime(
        lane, LANES, {lane: {"runtime_profile": "source" if source else "package"}},
        environ={"FLYWHEEL_HOME": str(tmp_path / "home"), "PATH": ""},
        python_executable="python.exe", is_frozen=False,
        source_resolver=lambda _lane: checkout, extra_roots=lambda _lane: [],
        importable_fn=lambda _module: True,
        installed_version_fn=lambda entry: entry.version,
        package_runtime_version_fn=lambda _entry, _python: None)
    assert runtime.selected_runtime == ("source" if source else "package")
    return runtime.require_launch()


def _frozen(lane: str, _tmp_path: Path) -> LaunchSpec:
    return LaunchSpec(("engine.exe", "--bundled-lane-mcp", lane), inherit_env=False,
                      allowed_tools=tuple(policy.admitted_tools(lane)))


MODES = {
    "frozen": _frozen,
    "pip": lambda lane, tmp: _resolve(lane, tmp, source=False),
    "source": lambda lane, tmp: _resolve(lane, tmp, source=True),
}


@pytest.fixture
def calls_in(monkeypatch, tmp_path):
    """call_lane_tool against the launch one install mode resolves."""
    import harness.lanes as lanes
    import harness.mcp_client as mcp_client
    recorder = _Recorder()
    monkeypatch.setattr(mcp_client, "MCPClient", recorder.factory)
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path / "home"))

    def use(mode: str, lane: str):
        launch = MODES[mode](lane, tmp_path)
        monkeypatch.setattr(lanes, "resolve_mcp_launch", lambda _name: launch)
        return launch
    use.recorder = recorder
    return use


def _call(lane, tool, tier=""):
    from harness.lane_caller import call_lane_tool
    return call_lane_tool(lane, tool, {}, governance_tier=tier, timeout=1)


@pytest.mark.parametrize("lane", sorted(LANES))
def test_every_lane_charges_t2_for_a_tool_the_table_does_not_list(lane):
    from harness.lane_caller import required_tier
    assert required_tier(lane, NEW_TOOL) == "T2"
    assert required_tier(lane, f"{lane}.{NEW_TOOL}") == "T2"


@pytest.mark.parametrize("lane", ["gather", "mneme", "canon", "crucible"])
@pytest.mark.parametrize("mode", sorted(MODES))
def test_an_unlisted_tool_without_t2_never_spawns_in_any_mode(calls_in, mode, lane):
    calls_in(mode, lane)
    result = _call(lane, f"{lane}.{NEW_TOOL}")
    assert result.get("governance_denied") is True, (mode, result)
    assert "T2" in result["error"]
    assert calls_in.recorder.calls == []


@pytest.mark.parametrize("mode", ["pip", "source"])
def test_a_granted_t2_call_runs_an_unlisted_tool_on_pip_and_source(calls_in, mode):
    launch = calls_in(mode, "gather")
    assert launch.allowed_tools is None   # these installs do not filter tools
    assert _call("gather", f"gather.{NEW_TOOL}", tier="T2") == {"ok": True}
    assert [tool for _l, tool, _a in calls_in.recorder.calls] == [f"gather.{NEW_TOOL}"]


def test_the_frozen_build_never_runs_an_unlisted_tool_even_at_t2(calls_in):
    calls_in("frozen", "gather")
    result = _call("gather", f"gather.{NEW_TOOL}", tier="T2")
    assert result["code"] == "CAPABILITY_NOT_ADMITTED"
    assert calls_in.recorder.calls == []


@pytest.mark.parametrize("mode", sorted(MODES))
def test_a_listed_t1_tool_still_runs_without_a_tier(calls_in, mode):
    calls_in(mode, "gather")
    assert _call("gather", "gather.status") == {"ok": True}


def test_the_listing_names_the_unlisted_tier_on_every_lane():
    from harness.lane_caller import list_available_lanes
    listing = {row["name"]: row for row in list_available_lanes()}
    assert set(listing) == set(LANES)
    assert {row["unlisted_tool_tier"] for row in listing.values()} == {"T2"}


def test_the_console_marks_an_unlisted_tool_t2_and_not_admitted(tmp_path):
    from harness.lane_console_route import _tool_row
    row = _tool_row("gather", {"name": f"gather.{NEW_TOOL}"}, _resolve(
        "gather", tmp_path, source=False))
    assert (row["tier"], row["admitted"]) == ("T2", False)


def test_the_approval_sheet_shows_an_unlisted_tool_as_t2():
    from harness.lane_tier_gate import lane_policy_review
    review = lane_policy_review({"name": "gather", "tool": f"gather.{NEW_TOOL}",
                                 "args": {}, "governance_tier": "T2"})
    assert (review["listed"], review["required_tier"], review["t2"]) == (False, "T2", True)


@pytest.mark.parametrize("lane", ["gather", "mneme", "canon", "relay", "bulletin"])
def test_plugins_still_refuse_an_unlisted_tool(monkeypatch, lane):
    recorder = _Recorder()
    result = _plugin_lane(monkeypatch, recorder, lane)(f"{lane}.{NEW_TOOL}", {})
    assert result["code"] == "CAPABILITY_NOT_ADMITTED"
    assert result["required_tier"] == "T2"
    assert recorder.calls == []


@pytest.mark.parametrize("lane", ["gather", "mneme", "canon", "relay"])
def test_agent_runs_still_refuse_an_unlisted_tool(monkeypatch, tmp_path, lane):
    from harness.gateway_agent_mcp_cache import restricted_catalog_launch
    from harness.gateway_operation import GatewayOperationError
    _catalog_lane(monkeypatch, tmp_path)
    with pytest.raises(GatewayOperationError, match="CAPABILITY_NOT_ADMITTED"):
        restricted_catalog_launch(lane, [f"{lane}.{NEW_TOOL}"])
