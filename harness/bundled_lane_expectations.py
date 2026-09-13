"""Compiled expectations for lane components bundled into a frozen gateway."""
from __future__ import annotations


EXPECTED_BUNDLED_LANES: dict[str, dict[str, object]] = {
    "relay": {
        "schema": "flywheel.bundled-lane-expectation/v1",
        "name": "relay",
        "version": "0.2.1",
        "source_repo": "https://github.com/HarperZ9/relay",
        "source_commit": "84ca5a4057bd6702709b8cb7e67a7516d06bc2e4",
        "source_path": "src/relay",
        "source_manifest_sha256": (
            "sha256:34bc74bbae4f6ea740477e16bc3cb1cb4636b833ea61808b"
            "28fc03fd98f63e14"
        ),
        "descriptor_sha256": (
            "sha256:73a7cdd68c8228ac84e9ca9a20edb08bee9dc2156d479909"
            "0988080e696ab65b"
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
