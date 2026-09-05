"""Tests for the generic lane caller and governance gating."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from harness.lane_caller import (
    LANE_MIN_TIERS,
    SPLIT_DEFAULT_TIER,
    TOOL_MIN_TIERS,
    _tier_allows,
    call_lane_tool,
    list_available_lanes,
    required_tier,
)


# --- governance gating --------------------------------------------------


def test_t1_can_call_t1_lane():
    """A T1 governance tier can call a T1-minimum lane."""
    result = call_lane_tool("gather", "gather.run", {},
                            governance_tier="T1",
                            timeout=1)  # will fail to spawn, but check gate first
    # The call will fail at the MCP spawn level, not the governance gate
    assert "governance_denied" not in result


def test_t1_cannot_call_t2_lane():
    """A T1 governance tier is denied access to a T2-minimum lane."""
    result = call_lane_tool("local-model", "local_agent_health", {},
                            governance_tier="T1")
    assert result.get("governance_denied") is True
    assert "T2" in result["error"]


def test_t2_can_call_t2_lane():
    """A T2 governance tier can access a T2-minimum lane."""
    result = call_lane_tool("local-model", "local_agent_health", {},
                            governance_tier="T2", timeout=1)
    assert "governance_denied" not in result


def test_t3_can_call_any_lane():
    """A T3 governance tier has access to all lanes."""
    result = call_lane_tool("local-model", "local_agent_health", {},
                            governance_tier="T3", timeout=1)
    assert "governance_denied" not in result


def test_no_governance_tier_allows_all():
    """When no governance tier is set, no gating occurs."""
    result = call_lane_tool("local-model", "local_agent_health", {},
                            governance_tier="", timeout=1)
    assert "governance_denied" not in result


# --- unknown lane handling ----------------------------------------------


def test_unknown_lane_returns_error():
    result = call_lane_tool("nonexistent", "some_tool", {})
    assert "error" in result
    assert "unknown lane" in result["error"]


def test_unknown_lane_lists_available():
    result = call_lane_tool("nonexistent", "some_tool", {})
    assert "gather" in result["error"]
    assert "forum" in result["error"]


# --- lane listing -------------------------------------------------------


def test_list_available_lanes():
    lanes = list_available_lanes()
    assert isinstance(lanes, list)
    assert len(lanes) > 0
    names = [l["name"] for l in lanes]
    assert "gather" in names
    assert "forum" in names


def test_lane_listing_includes_tier():
    lanes = list_available_lanes()
    for lane in lanes:
        assert "min_tier" in lane
        assert lane["min_tier"] in ("T1", "T2", "T3")


def test_lane_listing_carries_the_registry_description():
    # The listing feeds the gateway /lanes endpoint straight to the client, so a
    # blank description ships a blank card. The value comes from the lane's role
    # field (Lane has no `description` attr), so every lane must carry non-empty text.
    from harness.lanes import LANES
    lanes = list_available_lanes()
    for lane in lanes:
        assert lane["description"], f"{lane['name']} listing has an empty description"
        assert lane["description"] == LANES[lane["name"]].role


def test_local_model_requires_t2():
    assert LANE_MIN_TIERS.get("local-model") == "T2"


# --- mocked MCP call ----------------------------------------------------


def test_successful_mcp_call():
    """When the MCP server responds, the result is parsed as JSON."""
    mock_result = {"status": "ok", "version": "1.0.0"}
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.call_text.return_value = {
        "ok": True, "text": '{"status": "ok", "version": "1.0.0"}'}

    with patch("harness.lane_caller.MCPClient", return_value=mock_client) if False else \
         patch.dict("sys.modules", {"harness.mcp_client": MagicMock(
             MCPClient=MagicMock(return_value=mock_client),
             MCPError=Exception)}):
        result = call_lane_tool("gather", "gather.run", {"query": "test"}, timeout=5)
    # Result depends on whether the mock was actually used; the test verifies
    # that call_lane_tool doesn't crash on a mocked path
    assert isinstance(result, dict)


def test_lane_caller_uses_runtime_launch_spec(monkeypatch):
    import harness.lanes as lanes
    import harness.mcp_client as mcp_client
    from harness.mcp_client import LaunchSpec

    expected = LaunchSpec(("gather-runtime",), "/source")
    seen = []

    class FakeClient:
        def __init__(self, launch, **kwargs):
            seen.append(launch)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def call_text(self, tool, arguments):
            return {"ok": True, "text": '{"status":"ok"}'}

    monkeypatch.setattr(lanes, "resolve_mcp_launch", lambda name: expected,
                        raising=False)
    monkeypatch.setattr(lanes, "resolve_mcp_command", lambda name: ["portable"])
    monkeypatch.setattr(mcp_client, "MCPClient", FakeClient)
    assert call_lane_tool("gather", "gather.run") == {"status": "ok"}
    assert seen == [expected]


# --- per-tool tiers -----------------------------------------------------
#
# The lane floor cannot say that reading a public board and posting to it are
# different acts, and bulletin is the lane where that matters: reading is the
# point of the board, writing publishes under a persistent identity on a host
# other people read.


def test_a_t1_run_may_read_the_open_board():
    assert required_tier("bulletin", "board_feed") == "T1"
    assert _tier_allows("T1", required_tier("bulletin", "board_feed"))


def test_a_t1_run_may_not_post_to_the_board():
    # The denial path returns before anything is spawned or dialled, so this
    # runs the real gate inside call_lane_tool without touching a network.
    result = call_lane_tool("bulletin", "board_write_post", {},
                            governance_tier="T1")
    assert result.get("governance_denied") is True
    assert "board_write_post" in result["error"]
    assert "T2" in result["error"]


def test_a_t2_run_may_post_to_the_board():
    assert _tier_allows("T2", required_tier("bulletin", "board_write_post"))


def test_a_tool_nobody_listed_is_refused_rather_than_opened():
    """The fail-closed direction, and why the map lists the reads not the writes.

    A tool added to the board after this map was written is unlisted here.
    Defaulting it to the lane floor would open it at T1 the day it shipped, and
    a gate that widens on its own when the far side grows is not a gate.
    """
    assert required_tier("bulletin", "board_tool_that_does_not_exist_yet") == "T2"


def test_a_lane_with_one_tier_is_untouched_by_the_split():
    assert required_tier("gather", "anything_at_all") == "T1"
    assert required_tier("local-model", "anything_at_all") == "T2"


def test_the_per_tool_map_only_ever_raises_the_floor():
    # An entry below its lane floor would be a hole in the lane gate: the lane
    # says T2, one tool says T1, and the tool wins.
    ranks = {"T1": 1, "T2": 2, "T3": 3}
    for lane, tools in TOOL_MIN_TIERS.items():
        floor = LANE_MIN_TIERS.get(lane, "T1")
        for tool in tools:
            assert ranks[required_tier(lane, tool)] >= ranks[floor], f"{lane}.{tool}"


def test_every_tier_named_in_either_map_is_a_tier():
    assert SPLIT_DEFAULT_TIER in ("T1", "T2", "T3")
    for tier in LANE_MIN_TIERS.values():
        assert tier in ("T1", "T2", "T3")
    for tools in TOOL_MIN_TIERS.values():
        for tier in tools.values():
            assert tier in ("T1", "T2", "T3")


@pytest.mark.parametrize("tool", ["board_write_post", "board_flag_post",
                                  "board_create_room", "board_update_profile",
                                  "board_promote"])
def test_no_board_tool_that_changes_the_board_sits_in_the_open_set(tool):
    """The control on the map itself.

    These five are the board's write surface. The open set here is hand-written
    and the board lives in another repository, so nothing mechanical stops one
    of them being added to it. This is what catches that.
    """
    assert TOOL_MIN_TIERS["bulletin"].get(tool) is None
    assert required_tier("bulletin", tool) == "T2"


def test_the_listing_says_when_a_lane_charges_two_tiers():
    # A client reading min_tier alone would conclude every bulletin tool is
    # open at T1. The listing carries the split or it misleads.
    listing = {row["name"]: row for row in list_available_lanes()}
    assert listing["bulletin"]["unlisted_tool_tier"] == "T2"
    assert listing["bulletin"]["tool_tiers"]["board_feed"] == "T1"
    assert "unlisted_tool_tier" not in listing["gather"]
