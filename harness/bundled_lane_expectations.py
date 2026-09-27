"""Compiled expectations for lane components bundled into a frozen gateway."""
from __future__ import annotations


EXPECTED_BUNDLED_LANES: dict[str, dict[str, object]] = {
    "relay": {
        "schema": "flywheel.bundled-lane-expectation/v1",
        "name": "relay",
        "version": "0.3.0",
        "source_repo": "https://github.com/HarperZ9/relay",
        "source_commit": "786c62506223594f5c6a19975649236e24a34ca8",
        "source_path": "src/relay",
        "source_manifest_sha256": (
            "sha256:1c9f26d64754ee811f493868931831ea2d39f9a7675e2197"
            "b8a42072eae84693"
        ),
        "descriptor_sha256": (
            "sha256:866c07d056cf43c6dd1ec8783f51c6d131f5cd07f3e70c71"
            "55623f3c499f4ad0"
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
