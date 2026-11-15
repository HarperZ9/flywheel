"""Every MCP tool states its title and read/write hints.

The Anthropic Software Directory Policy requires readOnlyHint, destructiveHint
and title on every tool a listed server exposes.
"""
from relay.local_mcp import handle
from relay.mcp_schema import TOOL_ANNOTATIONS

HINTS = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")


def test_every_listed_tool_is_annotated():
    tools = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]
    assert {tool["name"] for tool in tools} == set(TOOL_ANNOTATIONS)
    for tool in tools:
        notes = tool["annotations"]
        assert notes["title"] and tool["title"] == notes["title"], tool["name"]
        assert all(isinstance(notes[key], bool) for key in HINTS), tool["name"]
        assert len(tool["name"]) <= 64
        if notes["readOnlyHint"]:
            assert notes["destructiveHint"] is False, tool["name"]


def test_hints_match_tool_effects():
    tools = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]
    by_name = {tool["name"]: tool["annotations"] for tool in tools}
    assert by_name["local_agent_run"]["destructiveHint"] is True
    assert by_name["local_agent_chat"]["openWorldHint"] is True
    assert by_name["relay.doctor"]["readOnlyHint"] is True
