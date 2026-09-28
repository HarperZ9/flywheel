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
        # The LF bytes of the tag (the relay payload row's manifest), not the
        # CRLF form a Windows checkout writes (check_bundled_lane_descriptors).
        "source_manifest_sha256": (
            "sha256:5ac76b4ee50fc7ec22e244c9333d0593b9dc99d39cd8b020"
            "a98775b760b6112d"
        ),
        "descriptor_sha256": (
            "sha256:5bf51d07953900590fbda232bc947e68126ee64c79afc63a"
            "3147caee9908a0b0"
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
