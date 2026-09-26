"""lane_call_route.py -- the generic lane caller, behind an exact grant.

`POST /api/lane/<name>/<tool>` spawns the lane's MCP server and calls one of
its tools, so it is an execution and reaches the gateway only as a granted
operation. The grant names the lane and the tool; the path names them too.
Both must agree, or the call is refused: a grant that attests to one target
while the route runs another is not a grant.

A failed call answers with one fixed code (``LANE_ERROR_CODES``), a fixed
message and a reason slug from a closed set. Tool text and server stderr are
not passed through (O-7 default): the codes are what the gateway lets past its
failure mask (``gateway._json`` ``public_boundary``), and a code that carried
free text could carry a granted key's value with it. A call that could not
launch rewrites the lane's probe record (H-10), and a key bound to a call that
succeeded is recorded as validated (names only).
"""
from __future__ import annotations

import re

_DEFAULT_TIMEOUT = 20
LANE_ERROR_CODES = frozenset((
    "CAPABILITY_NOT_ADMITTED", "NOT_IN_BUILD", "LANE_SETUP_REQUIRED",
    "LANE_CANNOT_LAUNCH", "LANE_TIMEOUT", "LANE_TOOL_ERROR"))
_ERRORS = {
    "LANE_SETUP_REQUIRED": (409, "the lane needs a setup step before this tool runs"),
    "LANE_CANNOT_LAUNCH": (503, "the lane could not start"),
    "LANE_TIMEOUT": (504, "the lane tool did not answer in time"),
    "LANE_TOOL_ERROR": (502, "the lane tool reported an error"),
}
_SLUG = re.compile(r"[a-z0-9_]{1,64}\Z")
# What lane_caller writes into its error strings, mapped to (code, reason).
# test_lane_call_route pins each against the real lane_caller.
_CALLER_ERRORS = (
    ("MCPError: no response within", ("LANE_TIMEOUT", "no_response")),
    ("MCPError: server closed", ("LANE_CANNOT_LAUNCH", "server_exited")),
    ("MCPError: server stdin is closed", ("LANE_CANNOT_LAUNCH", "server_exited")),
    ("MCPError: CAPABILITY_NOT_ADMITTED", ("CAPABILITY_NOT_ADMITTED", "")),
    ("FileNotFoundError", ("LANE_CANNOT_LAUNCH", "runtime_executable_missing")),
    ("PermissionError", ("LANE_CANNOT_LAUNCH", "launch_failed")),
    ("OSError", ("LANE_CANNOT_LAUNCH", "launch_failed")),
    ("MCPError", ("LANE_TOOL_ERROR", "mcp_error")),
)


def parse_lane_path(path: str) -> tuple[str, str] | None:
    """('lane', 'tool') from /api/lane/<lane>/<tool>, or None if malformed."""
    parts = path.split("?", 1)[0].split("/")
    if (len(parts) != 5 or parts[:3] != ["", "api", "lane"]
            or not parts[3].strip() or not parts[4].strip()):
        return None
    return parts[3], parts[4]


def lane_error(code: str, lane: str, tool: str, reason: str,
               **extra: object) -> tuple[dict, int]:
    """One fixed lane error body and its HTTP status."""
    status, message = _ERRORS[code]
    body = {"code": code, "error": message, "status": "unavailable", "name": lane,
            "tool": tool, "reason": reason if _SLUG.fullmatch(reason) else "lane_error"}
    return {**body, **extra}, status


def runtime_refusal(lane: str, tool: str, codes) -> tuple[dict, int]:
    """LANE_SETUP_REQUIRED naming the setup items, or LANE_CANNOT_LAUNCH."""
    from .lane_runtime_frozen import launch_state, setup_items
    codes = [str(c) for c in codes] or ["runtime_launch_missing"]
    if launch_state(codes) == "needs_setup":
        return lane_error("LANE_SETUP_REQUIRED", lane, tool, codes[0],
                          setup=list(setup_items(codes)))
    _record_failure(lane, codes[0])
    return lane_error("LANE_CANNOT_LAUNCH", lane, tool, codes[0])


def _record_failure(lane: str, code: str) -> None:
    from .lane_probe_cache import default_cache, lane_pin
    from .lanes_registry import LANES
    if lane in LANES:
        default_cache().record_failure(lane, lane_pin(lane), code)


def _classify_error(lane: str, tool: str, text: str, timeout: int) -> tuple[dict, int]:
    from .lanes_registry import LANES
    if lane not in LANES:
        body, _status = lane_error("LANE_CANNOT_LAUNCH", lane, tool, "unknown_lane")
        return body, 404
    if text.startswith("cannot resolve MCP command"):
        from .lanes import resolve_lane_runtime
        return runtime_refusal(lane, tool, resolve_lane_runtime(lane).blocking_codes)
    prefix = f"lane {lane!r} unavailable: "
    rest = text[len(prefix):] if text.startswith(prefix) else None
    for marker, (code, reason) in _CALLER_ERRORS if rest is not None else ():
        if not rest.startswith(marker):
            continue
        if code == "CAPABILITY_NOT_ADMITTED":
            return _not_admitted(lane, tool), 400
        if code == "LANE_CANNOT_LAUNCH":
            _record_failure(lane, reason)
        extra = {"timeout_s": timeout} if code == "LANE_TIMEOUT" else {}
        return lane_error(code, lane, tool, reason, **extra)
    return lane_error("LANE_TOOL_ERROR", lane, tool, "tool_reported_error")


def _not_admitted(lane: str, tool: str) -> dict:
    from .lane_tool_policy import admitted_tools
    from .mcp_client import capability_not_admitted
    return {**capability_not_admitted(lane, tool), "admitted": admitted_tools(lane)}


def public_result(lane: str, tool: str, result: object,
                  timeout: int) -> tuple[object, int]:
    """The route's answer for one lane_caller result."""
    if not isinstance(result, dict):
        return result, 200
    if result.get("governance_denied") or result.get("code") == "PERMISSION_REQUIRED":
        return result, 403
    code = result.get("code")
    if code == "CAPABILITY_NOT_ADMITTED" and result.get("name") == lane:
        return {**result, "admitted": _not_admitted(lane, tool)["admitted"]}, 400
    if code is not None and "error" in result:
        return result, 400
    if "error" in result:
        return _classify_error(lane, tool, str(result["error"]), timeout)
    return result, 200


def _record_validated(lane: str, bindings: object) -> None:
    if bindings is None:
        return
    try:
        names = list(bindings.child_environment({}, platform="windows"))
    except Exception:
        return  # the call already bound them; a missing record is not an error
    if names:
        from .lane_probe_cache import default_cache
        default_cache().record_validated(lane, names)


def handle_lane_call(path: str, req: object,
                     credential_bindings: object = None) -> tuple[dict, int]:
    target = parse_lane_path(path)
    if target is None:
        return {"code": "GATEWAY_ROUTE_MALFORMED",
                "error": "use /api/lane/<name>/<tool>"}, 400
    lane_name, tool_name = target
    body = req if isinstance(req, dict) else {}
    # When a grant ran, these fields are the authorized ones. Absent (a
    # direct call that never reached the gate) the path stands alone.
    granted_name = body.get("name")
    granted_tool = body.get("tool")
    if ((granted_name is not None and granted_name != lane_name)
            or (granted_tool is not None and granted_tool != tool_name)):
        return {"code": "GATEWAY_ROUTE_MISMATCH",
                "error": "the authorized lane and tool do not match the "
                         "route they were sent to"}, 409
    args = body.get("args") or {}
    if not isinstance(args, dict):
        return {"error": "'args' must be an object"}, 400
    tier = body.get("governance_tier")
    timeout = body.get("timeout")
    if not isinstance(timeout, int) or isinstance(timeout, bool):
        timeout = _DEFAULT_TIMEOUT
    bulletin_access = (body["bulletin_access"]
                       if "bulletin_access" in body else None)
    from .lane_caller import call_lane_tool
    from .lane_credentials import redact_result
    bound = {} if credential_bindings is None else {
        "credential_bindings": credential_bindings}
    result = redact_result(call_lane_tool(
        lane_name, tool_name, args, timeout=timeout,
        governance_tier=str(tier or ""), bulletin_access=bulletin_access,
        **bound), credential_bindings)
    answer, status = public_result(lane_name, tool_name, result, timeout)
    if status == 200:
        _record_validated(lane_name, credential_bindings)
    return answer, status
