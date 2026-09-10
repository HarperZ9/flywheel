"""gateway_lane_calls.py — the gateway's two outbound lane calls.

The gateway forwards a small number of requests to lanes that run as their own
MCP servers. Both calls degrade rather than raise: a lane that is down turns
into an error dict the view can draw, because a dead lane must not take the
whole origin with it.

These live outside gateway.py so the handler module stays under the file gate.
gateway.py imports both names, so `gateway._forum_mcp_call` still resolves and a
test that patches `gateway._relay_mcp_call` still reaches the dispatch sites.
"""
from __future__ import annotations


def _relay_start_not_admitted(handler):
    """Reject Relay run starts before model/run custody is admitted."""
    _, bad = handler._req_json()
    if bad:
        return bad
    from harness.mcp_client import capability_not_admitted
    return handler._json(capability_not_admitted("relay", "local_agent_start"), 403)


def _forum_mcp_call(tool: str, args: dict) -> dict:
    """Call one forum MCP tool, gracefully degraded.

    Spawns the forum lane's MCP server, calls the named tool, and returns the
    parsed JSON. If the forum lane is down or slow, returns an honest error
    dict so the desktop view can render a 'forum offline' state.
    """
    from harness.mcp_client import MCPClient, MCPError
    from harness.lanes import resolve_mcp_launch, LaneRuntimeError
    try:
        command = resolve_mcp_launch("forum")
        with MCPClient(command, timeout=20, client_name="flywheel-forum-proxy") as c:
            res = c.call_text(tool, args)
            if not res["ok"]:
                return {"error": f"forum {tool} error: {res['text'][:200]}"}
            import json as _json
            try:
                return _json.loads(res["text"])
            except _json.JSONDecodeError:
                return {"raw": res["text"][:500]}
    except LaneRuntimeError:
        from .plugin_lane_runtime import unavailable_response
        return unavailable_response("forum")
    except (MCPError, FileNotFoundError, OSError) as e:
        return {"error": f"forum lane unavailable: {e}"}


def _relay_mcp_call(tool: str, args: dict) -> dict:
    """Call one relay MCP tool, gracefully degraded.

    relay is the execution lane (an accountable, witnessed coding agent). Forwarding
    to it here makes the gateway the single phone-facing origin: a phone drives the
    gateway (one auth, one tunnel), and a relay-backed run comes back with relay's
    verifiable run_id and ledger checkpoint, the same receipts a desktop run gets.
    """
    from harness.lanes import resolve_mcp_launch, LaneRuntimeError
    from harness.mcp_client import (
        MCPClient, MCPError, capability_not_admitted, launch_allows_tool)
    try:
        command = resolve_mcp_launch("relay")
        if not launch_allows_tool(command, tool):
            return capability_not_admitted("relay", tool)
        with MCPClient(command, timeout=30, client_name="flywheel-relay-proxy") as c:
            res = c.call_text(tool, args)
            if not res["ok"]:
                return {"error": f"relay {tool} error: {res['text'][:200]}"}
            import json as _json
            try:
                return _json.loads(res["text"])
            except _json.JSONDecodeError:
                return {"raw": res["text"][:500]}
    except LaneRuntimeError:
        from .plugin_lane_runtime import unavailable_response
        return unavailable_response("relay")
    except (MCPError, FileNotFoundError, OSError) as e:
        return {"error": f"relay lane unavailable: {e}"}
