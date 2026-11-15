"""Every MCP tool states its title and read/write hints.

The Anthropic Software Directory Policy requires readOnlyHint, destructiveHint
and title on every tool a listed server exposes.
"""
from plexus.mcp import handle

HINTS = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")


def test_every_listed_tool_is_annotated_read_only():
    tools = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]
    assert tools
    for tool in tools:
        notes = tool["annotations"]
        assert notes["title"] and tool["title"] == notes["title"], tool["name"]
        assert all(isinstance(notes[key], bool) for key in HINTS), tool["name"]
        assert len(tool["name"]) <= 64
        assert notes["readOnlyHint"] is True and notes["destructiveHint"] is False
