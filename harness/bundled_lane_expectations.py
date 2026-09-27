"""Compiled expectations for lane components bundled into a frozen gateway."""
from __future__ import annotations


EXPECTED_BUNDLED_LANES: dict[str, dict[str, object]] = {
    "relay": {
        "schema": "flywheel.bundled-lane-expectation/v1",
        "name": "relay",
        "version": "0.5.0",
        "source_repo": "https://github.com/HarperZ9/relay",
        "source_commit": "ba1e4f21f05ff610a182f9b4665bb82f05a969f8",
        "source_path": "src/relay",
        "source_manifest_sha256": (
            "sha256:93c31fd35a5e6a8e42bd3f26baba65275efb9179992b1fe4"
            "938f8688ee51501f"
        ),
        "descriptor_sha256": (
            "sha256:b474cc3174c560e3a9e264260773463f2aa0c05e56262cbc"
            "14eefc143d41441e"
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
