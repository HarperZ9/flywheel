"""Compiled expectations for lane components bundled into a frozen gateway."""
from __future__ import annotations


EXPECTED_BUNDLED_LANES: dict[str, dict[str, object]] = {
    "relay": {
        "schema": "flywheel.bundled-lane-expectation/v1",
        "name": "relay",
        "version": "0.2.0",
        "source_repo": "https://github.com/HarperZ9/relay",
        "source_commit": "81d544bd5f7435fc65f16a81d3f369818e493ddf",
        "source_path": "src/relay",
        "source_manifest_sha256": (
            "sha256:72ce514efefa26f06749e37a2738c790a912bea7c51ec784ed"
            "89df3574c9bd78"
        ),
        "descriptor_sha256": (
            "sha256:f634d2218ee9b9bf67947cf21651f09b2052d4f9ca8f2da"
            "21f5292226d5d6680"
        ),
        "module": "relay.local_mcp",
        "callable": "serve",
        "health_tool": "relay.status",
        "allowed_tools": ("relay.status",),
    },
}


def expected_bundled_lane(name: str) -> dict[str, object]:
    value = EXPECTED_BUNDLED_LANES[name]
    return dict(value)
