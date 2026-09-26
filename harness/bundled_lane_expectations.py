"""Compiled expectations for lane components bundled into a frozen gateway."""
from __future__ import annotations


EXPECTED_BUNDLED_LANES: dict[str, dict[str, object]] = {
    "relay": {
        "schema": "flywheel.bundled-lane-expectation/v1",
        "name": "relay",
        "version": "0.2.5",
        "source_repo": "https://github.com/HarperZ9/relay",
        "source_commit": "29b8cc298c360c383ee2ff56212298b6185298c1",
        "source_path": "src/relay",
        "source_manifest_sha256": (
            "sha256:9dddeabcb4d019a013cbf6164fc48a7a55d519cdb7b798db"
            "8229ac28523e0c97"
        ),
        "descriptor_sha256": (
            "sha256:0c5905a9b5e3b0558c69de83c495ca4ca4fa575a014708d6"
            "aa1ffaaae409ab20"
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
