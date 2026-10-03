"""Compiled expectations for lane components bundled into a frozen gateway."""
from __future__ import annotations


EXPECTED_BUNDLED_LANES: dict[str, dict[str, object]] = {
    "relay": {
        "schema": "flywheel.bundled-lane-expectation/v1",
        "name": "relay",
        "version": "0.6.0",
        "source_repo": "https://github.com/HarperZ9/relay",
        "source_commit": "2510d6b3db9c42074c1139af21155a6bf8187b62",
        "source_path": "src/relay",
        # The LF bytes of the tag (the relay payload row's manifest), not the
        # CRLF form a Windows checkout writes (check_bundled_lane_descriptors).
        "source_manifest_sha256": (
            "sha256:81fd85c8cf8fbfe8a6046668ed8d2e64cc0789bdc59736551c81a1ff5"
            "c93c684"
        ),
        "descriptor_sha256": (
            "sha256:174d65e1e2fd9ff07c907240a221270634bf2df3c794f61ff96f7d405"
            "ac6f7f0"
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
