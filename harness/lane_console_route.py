"""The lane console routes: callable lanes, setup, tool listing, a one-lane
check, lane install, and the two setup choices a person makes in the app.

- ``GET /api/lanes/callable``: every lane with its tool tiers.
- ``GET /api/lanes/<lane>/setup``: every setup item the card states.
- ``POST /api/lanes/<lane>/check``: probe one lane now; the row with its state.
  It spawns the lane, so it sits under private custody (S6).
- ``POST /api/lanes/<lane>/tools``: every tool the lane's server lists, from
  an unfiltered ``tools/list`` (``MCPClient.list_tools`` filters, so it cannot
  be used as is), each marked ``admitted``, ``tier``, ``not_in_build`` and
  ``path_args`` (the arguments the desktop may fill with a local path). It
  spawns the lane, so it carries the same approval as ``plugin.probe``: the
  body is a ``plugin.probe`` grant envelope naming this lane (O-4 keeps POST
  with the grant; there is no GET).
- ``POST /api/lanes/install``: install one lane at its pinned version, only
  after the gateway consumed an exact ``lane.install`` grant (the body is the
  approved operation).
- ``GET|POST /api/lanes/local-model/root`` and ``GET|POST
  /api/settings/node_path``: the two setup choices (``lane_settings_route``);
  each POST arrives only after the gateway consumed its exact grant.

The gateway sends every ``/api/lanes/`` request and the node path setting here
through one line per method, so ``harness/gateway.py`` stays inside its frozen
size.
"""
from __future__ import annotations

import os
from typing import Callable, Mapping

from .lane_settings_route import (  # re-exported for the gateway and the tests
    INSTALL_ROUTE, LOCAL_MODEL_ROOT_ROUTE, NODE_PATH_ROUTE, node_path_get, node_path_post, root_body,
    root_post, setting_post)

SCHEMA_TOOLS = "flywheel.lane-tools/v1"
LANES_PREFIX = "/api/lanes/"
CALLABLE_ROUTE = "/api/lanes/callable"
CONSOLE_ROUTES = (
    ("GET", "/api/lanes/{lane}/setup", "every setup item a lane card states"),
    ("POST", "/api/lanes/{lane}/check", "probe one lane now and return its state"),
    ("POST", "/api/lanes/{lane}/tools", "every tool a lane lists, under a plugin.probe grant"),
    ("GET", LOCAL_MODEL_ROOT_ROUTE, "the local-model project folder"),
    ("POST", LOCAL_MODEL_ROOT_ROUTE, "choose or clear the local-model project folder, "
                                     "under a lane.root grant"),
    ("GET", NODE_PATH_ROUTE, "the node executable the Node lanes use"),
    ("POST", NODE_PATH_ROUTE, "choose or clear node.exe for the Node lanes, under a "
                              "settings.node_path grant"),
)


def serves(path: str) -> bool:
    """True for a path this module answers."""
    bare = path.split("?", 1)[0]
    return bare.startswith(LANES_PREFIX) or bare == NODE_PATH_ROUTE


def _bad(reason: str, status: int = 400) -> tuple[dict, int]:
    return {"code": "INVALID_REQUEST", "error": "the request is invalid",
            "reason": reason}, status


def parse_console_path(path: str) -> tuple[str, str] | None:
    """(lane, action) from /api/lanes/<lane>/<action>, or None."""
    parts = path.split("?", 1)[0].split("/")
    if len(parts) != 5 or parts[:3] != ["", "api", "lanes"] or not parts[3] or not parts[4]:
        return None
    return parts[3], parts[4]


def console_get(path: str, *, environ: Mapping[str, str] | None = None) -> tuple[dict, int]:
    env = os.environ if environ is None else environ
    bare = path.split("?", 1)[0]
    if bare == CALLABLE_ROUTE:
        from .lane_caller import list_available_lanes
        return {"lanes": list_available_lanes()}, 200
    if bare == NODE_PATH_ROUTE:
        return node_path_get(env), 200
    if bare == LOCAL_MODEL_ROOT_ROUTE:
        return root_body(env), 200
    target = parse_console_path(path)
    from .lanes_registry import LANES
    if target is None or target[1] != "setup":
        return {"code": "NOT_FOUND", "error": "no such lane console route"}, 404
    if target[0] not in LANES:
        return {"code": "NOT_FOUND", "error": "unknown lane", "name": target[0]}, 404
    from .lane_setup import SetupChecks, lane_setup
    return lane_setup(target[0], SetupChecks(env)), 200


def check_lane(lane: str, *, status_fn: Callable[..., dict] | None = None) -> tuple[dict, int]:
    """Probe one lane now, record it, and return its row with the state fields."""
    from .lane_roster_row import roster_rows
    from .lanes_registry import LANES
    if lane not in LANES:
        return {"code": "NOT_FOUND", "error": "unknown lane", "name": lane}, 404
    if status_fn is None:
        from .lanes import lane_status as status_fn
    row = status_fn(lane, probe=True, timeout=20.0)
    return roster_rows([row], probed=True)[0], 200


# ---- tool listing -------------------------------------------------------

def _tool_row(lane: str, spec: Mapping[str, object], launch) -> dict:
    from .lane_caller import required_tier
    from .lane_tool_policy import tool_policy
    from .mcp_client import launch_allows_tool
    name = str(spec.get("name", ""))
    entry = tool_policy(lane, name)
    tier = required_tier(lane, name)
    gone = entry.not_in_build if entry else ""
    return {"name": name, "description": str(spec.get("description", "")),
            "inputSchema": spec.get("inputSchema") or {}, "listed": True,
            "admitted": bool(launch_allows_tool(launch, name) and tier == "T1" and not gone),
            "tier": tier, "not_in_build": gone, "main": bool(entry and entry.main),
            "timeout_s": entry.timeout_s if entry else 20,
            "needs": list(entry.needs) if entry else [],
            "path_args": list(entry.path_args) if entry else []}


def tools_listing(lane: str, launch, *, client_factory=None) -> tuple[dict, int]:
    """List every tool the lane's server offers, marked against the policy."""
    from .lane_call_route import _record_failure, lane_error
    from .lane_tool_policy import lane_policy
    from .mcp_client import MCPClient, MCPError
    factory = client_factory or MCPClient
    try:
        with factory(launch, timeout=20.0, client_name="flywheel-lane-console") as client:
            specs = [s for s in client.list_all_tools() if isinstance(s, dict)]
    except FileNotFoundError:
        _record_failure(lane, "runtime_executable_missing")
        return lane_error("LANE_CANNOT_LAUNCH", lane, "", "runtime_executable_missing")
    except MCPError as error:
        if str(error).startswith("no response within"):
            return lane_error("LANE_TIMEOUT", lane, "", "no_response", timeout_s=20)
        _record_failure(lane, "server_exited")
        return lane_error("LANE_CANNOT_LAUNCH", lane, "", "server_exited")
    except OSError:
        _record_failure(lane, "launch_failed")
        return lane_error("LANE_CANNOT_LAUNCH", lane, "", "launch_failed")
    rows = sorted((_tool_row(lane, s, launch) for s in specs), key=lambda r: r["name"])
    listed = {r["name"] for r in rows}
    for name, entry in lane_policy(lane).items():
        if entry.not_in_build and name not in listed:
            rows.append({**_tool_row(lane, {"name": name}, launch), "listed": False})
    return {"schema": SCHEMA_TOOLS, "lane": lane, "n_tools": len(rows), "tools": rows}, 200


def tools_post(lane: str, authorize: Callable[[], object], *,
               client_factory=None) -> tuple[dict, int]:
    """Consume one plugin.probe grant for this lane, then list its tools."""
    from .lanes_registry import LANES
    if lane not in LANES:
        return {"code": "NOT_FOUND", "error": "unknown lane", "name": lane}, 404
    from .lanes import resolve_lane_runtime
    runtime = resolve_lane_runtime(lane)
    if runtime.blocking_codes or runtime.launch is None:
        from .lane_call_route import runtime_refusal
        return runtime_refusal(lane, "", runtime.blocking_codes)
    authorized = authorize()
    if authorized.operation.get("name") != lane:
        return {"code": "GATEWAY_ROUTE_MISMATCH", "error": "the authorized lane does "
                "not match the route it was sent to"}, 409
    plan = getattr(authorized, "execution_plan", None)
    launch = getattr(plan, "launch", None) or runtime.launch
    return tools_listing(lane, launch, client_factory=client_factory)


# ---- gateway mount ------------------------------------------------------

def _install(handler):
    req, bad = handler._req_json()
    if bad:
        return bad
    name = str((req or {}).get("name", "")).strip()
    if not name:
        return handler._json({"error": "provide a lane 'name'"}, 400)
    profile = str(req.get("profile", "package")).strip() or "package"
    from .lanes import install_lane
    return handler._json(install_lane(name, profile=profile))


def console_post_mount(handler, path: str):
    """Serve a POST under /api/lanes/ or the node path setting for the gateway."""
    bare = path.split("?", 1)[0]
    if bare in (LOCAL_MODEL_ROOT_ROUTE, NODE_PATH_ROUTE):  # granted: the body is the operation
        req, bad = handler._req_json()
        return bad if bad else handler._json(*setting_post(bare, req))
    if bare == INSTALL_ROUTE:
        return _install(handler)
    target = parse_console_path(path)
    if target is None or target[1] not in ("tools", "check"):
        return handler._json({"code": "NOT_FOUND", "error": "no such lane console route"}, 404)
    if target[1] == "check":
        return handler._json(*check_lane(target[0]))
    length = handler._content_length()
    if length is None:
        return handler._json(*_bad("invalid_length", 422))
    raw = handler.rfile.read(length)
    from .gateway_grant_route import authorize_gateway_operation, gateway_error_response
    from .gateway_operation import GatewayOperationError

    def _authorize():
        authorized = authorize_gateway_operation(
            "plugin.probe", raw, owner_ref=handler.owner_ref,
            state_root=handler.flywheel_home / "state", clock=handler.clock)
        handler._gateway_guarded = True
        return authorized
    try:
        return handler._json(*tools_post(target[0], _authorize))
    except GatewayOperationError as exc:  # the grant was refused; nothing was spawned
        return handler._json(*gateway_error_response(exc))
