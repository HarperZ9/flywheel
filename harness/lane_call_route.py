"""lane_call_route.py -- the generic lane caller, behind an exact grant.

`POST /api/lane/<name>/<tool>` spawns the lane's MCP server and calls one of
its tools, so it is an execution and reaches the gateway only as a granted
operation. The grant names the lane and the tool; the path names them too.
Both must agree, or the call is refused: a grant that attests to one target
while the route runs another is not a grant.
"""
from __future__ import annotations

_DEFAULT_TIMEOUT = 20


def parse_lane_path(path: str) -> tuple[str, str] | None:
    """('lane', 'tool') from /api/lane/<lane>/<tool>, or None if malformed."""
    parts = path.split("/")
    if len(parts) < 5 or not parts[3].strip() or not parts[4].strip():
        return None
    return parts[3], parts[4]


def handle_lane_call(path: str, req: object) -> tuple[dict, int]:
    target = parse_lane_path(path)
    if target is None:
        return {"error": "use /api/lane/<name>/<tool>"}, 400
    lane_name, tool_name = target
    body = req if isinstance(req, dict) else {}
    # When a grant ran, these fields are the authorized ones. Absent (a
    # direct call that never reached the gate) the path stands alone.
    granted_name = body.get("name")
    granted_tool = body.get("tool")
    if ((granted_name is not None and granted_name != lane_name)
            or (granted_tool is not None and granted_tool != tool_name)):
        return {"error": "the authorized lane and tool do not match the "
                         "route they were sent to"}, 409
    args = body.get("args") or {}
    if not isinstance(args, dict):
        return {"error": "'args' must be an object"}, 400
    tier = body.get("governance_tier")
    timeout = body.get("timeout")
    if not isinstance(timeout, int) or isinstance(timeout, bool):
        timeout = _DEFAULT_TIMEOUT
    from .lane_caller import call_lane_tool
    result = call_lane_tool(lane_name, tool_name, args, timeout=timeout,
                            governance_tier=str(tier or ""))
    if result.get("governance_denied"):
        return result, 403
    return result, 400 if "error" in result else 200
