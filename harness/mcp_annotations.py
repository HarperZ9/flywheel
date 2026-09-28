"""mcp_annotations.py -- one way to give an MCP tool its title and hints.

A client reads `readOnlyHint` and `destructiveHint` to decide whether a call
needs the person's confirmation. The MCP defaults (`readOnlyHint: false`,
`destructiveHint: true`, `idempotentHint: false`, `openWorldHint: true`) fit no
Flywheel tool, so every server sets all four explicitly through this helper,
and `tests/test_mcp_tool_annotations.py` holds every served tool to it.

The hints describe what the tool does to the person's machine and the world
outside it. They are hints: a client should not trust them from a server it
does not trust, and they do not replace the permission rules the person sets.
"""
from __future__ import annotations


def annotated(tool: dict, title: str, *, read_only: bool, destructive: bool,
              idempotent: bool, open_world: bool) -> dict:
    """A copy of `tool` with a top-level title and all four hints set.

    A read-only tool cannot also be destructive; asking for both is a mistake
    in the table that called this, so it raises instead of picking one.
    """
    if read_only and destructive:
        raise ValueError(f"{tool.get('name')}: read-only and destructive together")
    return {**tool, "title": title,
            "annotations": {"title": title, "readOnlyHint": read_only,
                            "destructiveHint": destructive,
                            "idempotentHint": idempotent,
                            "openWorldHint": open_world}}
