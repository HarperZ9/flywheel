"""Packaged public MCP resources for Flywheel skills.

The manifest is closed: callers may read only named public skill resources from
package data. URIs are identifiers, not paths, so traversal and file:// input
never reach the filesystem.
"""
from __future__ import annotations

import hashlib
from importlib import resources
from typing import Final

SCHEMA: Final = "flywheel.skill-resources/v1"
_SKILL_VERSION: Final = "0.1.0"
_MIME_MARKDOWN: Final = "text/markdown"

_RESOURCE_ROWS: Final = (
    {
        "uri": "flywheel://skills/flywheel-evidence-task/SKILL.md",
        "name": "flywheel-evidence-task/SKILL.md",
        "description": "Public Flywheel evidence-task skill entrypoint.",
        "package_path": ("skill_resources", "flywheel-evidence-task", "SKILL.md"),
        "skill": "flywheel-evidence-task",
        "version": _SKILL_VERSION,
    },
    {
        "uri": "flywheel://skills/flywheel-evidence-task/references/constraints.md",
        "name": "flywheel-evidence-task/references/constraints.md",
        "description": "Public constraints reference for Flywheel evidence tasks.",
        "package_path": (
            "skill_resources", "flywheel-evidence-task", "references", "constraints.md"
        ),
        "skill": "flywheel-evidence-task",
        "version": _SKILL_VERSION,
    },
)


def _read_packaged(parts: tuple[str, ...]) -> str:
    target = resources.files("harness")
    for part in parts:
        target = target.joinpath(part)
    return target.read_text(encoding="utf-8")


def _public(row: dict, text: str) -> dict:
    return {
        "uri": row["uri"],
        "name": row["name"],
        "description": row["description"],
        "mimeType": _MIME_MARKDOWN,
        "skill": row["skill"],
        "version": row["version"],
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "bytes": len(text.encode("utf-8")),
    }


def list_resources() -> dict:
    """List the public skill resources this package serves."""
    return {
        "schema": SCHEMA,
        "resources": [
            _public(row, _read_packaged(row["package_path"])) for row in _RESOURCE_ROWS
        ],
    }


def read_resource(uri: str) -> dict:
    """Read one named public skill resource from packaged data."""
    if type(uri) is not str:
        raise KeyError("unknown skill resource")
    for row in _RESOURCE_ROWS:
        if uri == row["uri"]:
            text = _read_packaged(row["package_path"])
            return {
                "schema": SCHEMA,
                "contents": [
                    {"uri": uri, "mimeType": _MIME_MARKDOWN, "text": text}
                ],
            }
    raise KeyError("unknown skill resource")
