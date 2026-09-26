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
            "sha256:40d6eeb3db3e4b7d9975ab3d8a560537c128e875206f7c15"
            "039edef57640ae8e"
        ),
        "module": "relay.local_mcp",
        "callable": "serve",
        "health_tool": "relay.status",
        # Relay's T1 tools in the lane tool policy (lane_tool_policy_agents).
        "allowed_tools": (
            "local_agent_health", "local_agent_chat", "local_agent_run",
            "local_agent_runs", "local_agent_sessions", "relay.status", "relay.doctor",
        ),
    },
}


def expected_bundled_lane(name: str) -> dict[str, object]:
    value = EXPECTED_BUNDLED_LANES[name]
    return dict(value)
