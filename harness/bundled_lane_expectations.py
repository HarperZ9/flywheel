"""Compiled expectations for lane components bundled into a frozen gateway."""
from __future__ import annotations


EXPECTED_BUNDLED_LANES: dict[str, dict[str, object]] = {
    "relay": {
        "schema": "flywheel.bundled-lane-expectation/v1",
        "name": "relay",
        "version": "0.2.2",
        "source_repo": "https://github.com/HarperZ9/relay",
        "source_commit": "a1f7f553cf2963ed756d0ec28d00015a3007188f",
        "source_path": "src/relay",
        "source_manifest_sha256": (
            "sha256:5809a688e62d9d895f23dec1503b9876a80beaaed0633a46"
            "a0c93108d5163092"
        ),
        "descriptor_sha256": (
            "sha256:c3b279cd7ed02f0bce50de04056171764a6741d6e90f6492"
            "16927ea7703794e7"
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
