"""Every MCP tool states its title and read/write hints.

The Anthropic Software Directory Policy requires readOnlyHint, destructiveHint
and title on every tool a listed server exposes. These tests hold each Canon
server to that and check that the hints match what the tool does.
"""
import json

from canon import context_mcp, local_mcp
from canon.client_mcp import ClientServer, parse_config

HINTS = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")


def _assert_complete(tools):
    assert tools
    for tool in tools:
        notes = tool["annotations"]
        assert notes["title"] and tool["title"] == notes["title"], tool["name"]
        assert all(isinstance(notes[key], bool) for key in HINTS), tool["name"]
        assert len(tool["name"]) <= 64
        if notes["readOnlyHint"]:
            assert notes["destructiveHint"] is False, tool["name"]


def test_client_server_tools_are_annotated(tmp_path):
    db = tmp_path / "canon.db"
    for extra in (["--allow-context-write"], []):
        server = ClientServer(parse_config(["--context-db", str(db), "--workspace-id", "w",
                                            "--project-id", "p", *extra]))
        tools = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]
        _assert_complete(tools)
        by_name = {tool["name"]: tool["annotations"] for tool in tools}
        assert by_name["canon.context.query"]["readOnlyHint"] is True
        if extra:
            assert by_name["canon.context.ingest"]["readOnlyHint"] is False
        else:
            assert "canon.context.ingest" not in by_name


def test_context_server_marks_purge_destructive():
    tools = context_mcp.tools()
    _assert_complete(tools)
    by_name = {tool["name"]: tool["annotations"] for tool in tools}
    assert by_name["canon.context.purge"]["destructiveHint"] is True
    assert by_name["canon.context.ingest"]["readOnlyHint"] is False


def test_local_server_tools_are_read_only():
    response = local_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    tools = response["result"]["tools"]
    _assert_complete(tools)
    assert all(tool["annotations"]["readOnlyHint"] for tool in tools)
    json.dumps(tools)
