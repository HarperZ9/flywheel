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
            "sha256:10df491efab2ac04bc21c98d1f39ffebd66f86f77162cf58"
            "e3e2219c5e19e062"
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
