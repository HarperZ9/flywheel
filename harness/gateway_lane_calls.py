"""gateway_lane_calls.py — the gateway's two outbound lane calls.

The gateway forwards a small number of requests to lanes that run as their own
MCP servers. Both calls degrade rather than raise: a lane that is down turns
into an error dict the view can draw, because a dead lane must not take the
whole origin with it.

These live outside gateway.py so the handler module stays under the file gate,
with the stop step the gateway runs when it stops serving.
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


def _proxy_refusal(lane: str, tool: str, args: dict) -> dict | None:
    """A GET proxy carries a bearer and no grant, so it runs at T1: a tool the
    policy puts above T1 (forum.run.room) or an argument the id and path guards
    refuse is answered here, before anything spawns."""
    from harness.lane_caller import required_tier
    from harness.lane_tier_gate import argument_refusal
    required = required_tier(lane, tool)
    if required != "T1":
        from harness.mcp_client import capability_not_admitted
        return {**capability_not_admitted(lane, tool), "required_tier": required,
                "route": "lane.call"}
    return argument_refusal(lane, tool, args)


def _proxy_launch(lane: str):
    """The lane launch for a T1 proxy call, without key-shaped grants (C-8)."""
    from harness.lanes import resolve_mcp_launch
    from harness.lane_credentials import strip_key_grants
    return strip_key_grants(lane, resolve_mcp_launch(lane))


def _forum_mcp_call(tool: str, args: dict) -> dict:
    """Call one forum MCP tool, gracefully degraded.

    Spawns the forum lane's MCP server, calls the named tool, and returns the
    parsed JSON. If the forum lane is down or slow, returns an honest error
    dict so the desktop view can render a 'forum offline' state.
    """
    from harness.mcp_client import MCPClient, MCPError
    from harness.lanes import LaneRuntimeError
    if (refused := _proxy_refusal("forum", tool, args)) is not None:
        return refused
    try:
        command = _proxy_launch("forum")
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
    Status, result and the run list read the relay lane session, where a run
    started on the lane route lives (lane_session_calls).
    """
    from harness.lanes import LaneRuntimeError
    from harness.mcp_client import (
        MCPClient, MCPError, capability_not_admitted, launch_allows_tool)
    if (refused := _proxy_refusal("relay", tool, args)) is not None:
        return refused
    try:
        from harness.lane_session import is_session_tool
        if is_session_tool("relay", tool):   # a background run lives in the session
            from harness.lane_session_calls import relay_session_call
            return relay_session_call(tool, args)
        command = _proxy_launch("relay")
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


def _stop_serving(operation_service, servers) -> None:
    """Stop the operation service, close every lane session (their children
    end with the engine, lane_session) and close every socket."""
    operation_service.shutdown()
    from harness import lane_session
    lane_session.close_lane_sessions()
    for s in servers:
        s.server_close()
