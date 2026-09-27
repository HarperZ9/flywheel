"""Compiled expectations for lane components bundled into a frozen gateway."""
from __future__ import annotations


EXPECTED_BUNDLED_LANES: dict[str, dict[str, object]] = {
    "relay": {
        "schema": "flywheel.bundled-lane-expectation/v1",
        "name": "relay",
        "version": "0.4.0",
        "source_repo": "https://github.com/HarperZ9/relay",
        "source_commit": "ac4d79877f19e3e4c439c15d4781c3896e2f33db",
        "source_path": "src/relay",
        "source_manifest_sha256": (
            "sha256:d196d6d0c2cebb6b19bd6f5b83432b38f02a606f304040df"
            "9ebd9fd5320725cb"
        ),
        "descriptor_sha256": (
            "sha256:8ce4af1f1e46764cd841f75fd7d1ca0e8ed8e4411f77f85b"
            "4503829912912878"
        ),
        "module": "relay.local_mcp",
        "callable": "serve",
        "health_tool": "relay.status",
        # Relay's T1 tools in the lane tool policy (lane_tool_policy_agents).
        # local_agent_status and local_agent_result read the relay lane session
        # (WP10); local_agent_start is T2 and joins only a granted call's launch.
        "allowed_tools": (
            "local_agent_health", "local_agent_chat", "local_agent_run",
            "local_agent_status", "local_agent_result", "local_agent_runs",
            "local_agent_sessions", "relay.status", "relay.doctor",
        ),
    },
}


def expected_bundled_lane(name: str) -> dict[str, object]:
    value = EXPECTED_BUNDLED_LANES[name]
    return dict(value)
