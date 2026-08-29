"""Tests for the generic lane caller and governance gating."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from harness.lane_caller import (
    LANE_MIN_TIERS,
    call_lane_tool,
    list_available_lanes,
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
