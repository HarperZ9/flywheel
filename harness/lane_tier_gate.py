"""The tool policy applied on each route that reaches a lane tool.

``lane_tool_policy`` says which tier each lane tool needs, which tools the
build leaves out and which arguments the engine forces. This module applies
that table where a call is made:

- ``/api/lane/<lane>/<tool>`` (``lane_caller.call_lane_tool``): the engine
  computes the tier; a granted T2 call widens the frozen launch for its one
  tool and that call only, and adds the tool's launch grant, if it has one, to
  that one launch (forum's ``--allow-gate-decisions``); a tool the build leaves
  out answers ``NOT_IN_BUILD``;
- Plugins (``plugins.call_plugin``): no tier travels with a plugin call, so a
  lane tool is reachable there only when the table lists it at T1;
- agent runs (``gateway_agent_mcp_cache.restricted_catalog_launch``): an agent
  may select a lane tool only when the table lists it at T1, in the build,
  with no argument guard, no state write and no open egress, since the agent
  runtime passes the model's arguments through and no inner call has a grant
  of its own (POLICY-DECISION C-11, C-12). Neither route reaches a lane
  session tool (``lane_session``): only the lane call route holds the session.

Argument guards apply on the lane call and Plugins routes: ``argument_refusal``
before anything spawns, then ``guard_args`` (allowlist, then forced values).
"""
from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from .lane_tool_policy import ID_PATTERN, WINDOWS_DEVICE_STEMS, guard_args, tool_policy

__all__ = ["admission_refusal", "agent_tool_refusal", "argument_refusal", "guard_args",
           "lane_policy_review", "not_in_build", "plugin_refusal", "widen_for_call"]


def not_in_build(lane: str, tool: str) -> dict[str, str]:
    """The fixed answer for a tool this build leaves out, with its reason slug."""
    entry = tool_policy(lane, tool)
    return {"code": "NOT_IN_BUILD", "error": "this build does not run this lane tool",
            "status": "unavailable", "name": lane, "tool": tool,
            "reason": entry.not_in_build if entry else ""}


def widen_for_call(launch: Any, lane: str, tool: str, granted_tier: str) -> Any:
    """The launch for one call: a granted T2 call admits its own T2 tool.

    Only a tool the table lists at T2 and keeps in the build, and only when the
    call carries T2 or higher. A restricted launch admits the tool; a tool with
    a ``launch_grant`` gets that flag at the end of the argv, in every install
    mode. The widened launch serves this call and is dropped with it, so no
    other call, listing, probe, plugin or agent run starts the lane with the
    grant. An unlisted tool never gets one."""
    entry = tool_policy(lane, tool)
    if (entry is None or entry.tier != "T2" or entry.not_in_build
            or granted_tier not in ("T2", "T3")):
        return launch
    allowed = getattr(launch, "allowed_tools", None)
    if allowed is not None and tool not in allowed:
        launch = replace(launch, allowed_tools=(*allowed, tool))
    argv = tuple(getattr(launch, "argv", ()) or ())
    if entry.launch_grant and argv and entry.launch_grant not in argv:
        launch = replace(launch, argv=(*argv, entry.launch_grant))
    return launch


def admission_refusal(launch: Any, lane: str, tool: str) -> dict | None:
    """None when the launch admits the tool; else the refusal to return."""
    from .mcp_client import capability_not_admitted, launch_allows_tool
    if launch_allows_tool(launch, tool):
        return None
    entry = tool_policy(lane, tool)
    if entry is not None and entry.not_in_build:
        return not_in_build(lane, tool)
    return capability_not_admitted(lane, tool)


def _plain_id(value: object) -> bool:
    return (isinstance(value, str) and bool(ID_PATTERN.fullmatch(value)) and ".." not in value
            and value.split(".", 1)[0].upper() not in WINDOWS_DEVICE_STEMS)


def _reaches_home(lane: str, value: object, environ: Mapping[str, str], *,
                  device_names: bool = True) -> bool:
    """True when a path argument resolves inside Flywheel's own state (the home
    or the run root, flywheel_state_roots) outside the lane's own folder, or is
    a Windows device or UNC spelling, or (``device_names``) names a reserved
    Windows device such as ``C:\\docs\\CON.md`` (path_identity). A relative path
    resolves from the lane folder, the child's working directory in every
    install mode (lane_workdir). A URL is not a local path.

    Lanes differ on "~" and on blanks: a lane that calls expanduser reads the
    user's folder, and index reads the text as given, "~" as a folder name
    under the lane folder and a leading blank as part of a name. So the value
    is checked both as given and stripped with "~" expanded, and either one
    reaching the state refuses the call: a root of ``~/../../../state`` expands
    to a folder outside the home, while index reads it from the lane folder as
    the home's state."""
    from .flywheel_state_roots import state_roots
    from .lane_workdir import flywheel_home
    from .path_identity import device_or_unc, inside, reserved_device_name
    if not isinstance(value, str) or not value.strip() or "://" in value:
        return False
    if device_or_unc(value) or (device_names and reserved_device_name(value)):
        return True
    own = flywheel_home(environ) / "lanes" / lane
    try:
        spellings = {value, os.path.expanduser(value.strip())}
        targets = [os.path.realpath(raw if raw.is_absolute() else own / raw)
                   for raw in map(Path, spellings)]
        own_s = os.path.realpath(own)
        roots = state_roots(environ)
    except (OSError, ValueError):
        return True   # an unresolvable path is refused, not guessed at
    return any(any(inside(target, root) for root in roots) and not inside(target, own_s)
               for target in targets)


_TREE_LIMIT = 4096                  # strings checked in one tree argument


def _tree_strings(value: object) -> list[str] | None:
    """Every string inside an object, a list or its JSON text; None when the
    tree holds more than ``_TREE_LIMIT`` strings (refused, not sampled)."""
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            parsed = None
        if isinstance(parsed, (dict, list)):
            value = parsed
    found: list[str] = []
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            found.append(item)
        elif isinstance(item, dict):
            stack.extend(item.keys())
            stack.extend(item.values())
        elif isinstance(item, (list, tuple)):
            stack.extend(item)
        if len(found) > _TREE_LIMIT:
            return None
    return found


def _tree_base(base_arg: str, args: Mapping[str, Any]) -> Path | None:
    """The folder the lane joins a relative tree string to, spelled as the lane
    reads it: the ``tree_base`` argument as given. index.route does
    ``Path(root)`` and then ``root / entry`` for a relative entry. A relative
    base stays relative, and ``_reaches_home`` reads the joined string from the
    lane folder, the child's working directory. None when the tool names no
    base or the call carries no string for it."""
    raw = args.get(base_arg) if base_arg else None
    if not isinstance(raw, str) or not raw.strip():
        return None
    return Path(raw)


def _tree_reaches_home(lane: str, value: object, environ: Mapping[str, str],
                       base: Path | None = None) -> bool:
    """A tree also holds text that is not a path, such as a query that reads
    "aux", so a reserved device name there is left to the lane: gather 1.9.1
    refuses one in any path it opens (NON_LOCAL_PATH, argument_refused). With a
    ``base``, each string is also checked joined to it, as the lane joins it."""
    strings = _tree_strings(value)
    return strings is None or any(
        _reaches_home(lane, text, environ, device_names=False)
        or (base is not None and _reaches_home(lane, str(base / text), environ,
                                               device_names=False))
        for text in strings)


def argument_refusal(lane: str, tool: str, args: Mapping[str, Any],
                     environ: Mapping[str, str] | None = None) -> dict | None:
    """None when the arguments pass the tool's id and path guards; else the
    fixed refusal, returned before any child spawns (C-4, C-14)."""
    entry = tool_policy(lane, tool)
    if entry is None:
        return None
    env = os.environ if environ is None else environ
    base = _tree_base(entry.tree_base, args)
    bad = any(name in args and not _plain_id(args[name]) for name in entry.id_args) or any(
        name in args and _reaches_home(lane, args[name], env) for name in entry.path_args) or any(
        name in args and _tree_reaches_home(lane, args[name], env, base)
        for name in entry.tree_args)
    reason = "argument_refused" if bad else _create_only_refusal(lane, tool, args, env)
    if not reason:
        return None
    return {"code": "LANE_TOOL_ERROR", "error": "the engine refused an argument of this "
            "lane tool", "status": "unavailable", "name": lane, "tool": tool,
            "reason": reason}


def _create_only_refusal(lane: str, tool: str, args: Mapping[str, Any],
                         environ: Mapping[str, str]) -> str:
    """Return "session_exists" when a create-only tool names a file that exists."""
    from .lane_tool_policy_args import CREATE_ONLY
    rule = CREATE_ONLY.get(lane, {}).get(tool)
    if rule is None or not _plain_id(args.get(rule[0])):
        return ""
    from .lane_workdir import lane_workdir
    target = lane_workdir(lane, environ) / rule[1].format(args[rule[0]])
    return "session_exists" if target.exists() else ""


def plugin_refusal(lane: str, tool: str) -> dict | None:
    """None when Plugins may call this lane tool; else the refusal.

    A plugin call carries no tier, so it runs at T1. A lane tool that needs more,
    that the table does not list (C-11), or whose work lives in a lane session
    (a per-call plugin child would lose it, lane_session) is refused before
    anything is spawned, with the route that can carry it."""
    from .lane_caller import required_tier
    from .lanes_registry import LANES
    if lane not in LANES:
        return None
    from .lane_session import is_session_tool
    required = required_tier(lane, tool)
    if (required == "T1" and tool_policy(lane, tool) is not None
            and not is_session_tool(lane, tool)):
        return None
    from .mcp_client import capability_not_admitted
    return {**capability_not_admitted(lane, tool), "required_tier": required,
            "route": "lane.call"}


def agent_tool_refusal(catalog: str, plugin_kind: str | None,
                       tools: tuple[str, ...] | list[str]) -> str | None:
    """None when an agent run may select every one of ``tools``; else a code."""
    from .lanes_registry import LANES
    if plugin_kind != "lane" or catalog not in LANES:
        return None
    from .lane_caller import required_tier
    from .lane_session import is_session_tool
    for tool in tools:
        entry = tool_policy(catalog, tool)
        if (entry is None or required_tier(catalog, tool) != "T1" or entry.not_in_build
                or entry.guarded or entry.effect == "state_write" or entry.open_egress
                or is_session_tool(catalog, tool)):
            return "CAPABILITY_NOT_ADMITTED"
    return None


_UNLISTED_REASON = ("The policy table does not list this tool, so nobody has reviewed "
                    "what it does. It runs only on a T2 approval and without granted keys.")


def lane_policy_review(operation: Mapping[str, Any]) -> dict:
    """What a lane.call approval authorizes, for the owner's approval sheet
    (POLICY-DECISION C-13): the tier the tool needs and the tier requested,
    its effect and reason (an unlisted tool reads as not reviewed), whether the
    lane's granted keys reach the child, what the engine forces or drops, the
    flag the engine adds to this call's launch (``launch_grant``, forum's
    ``--allow-gate-decisions`` on a gate decision), and the arguments the child
    receives, in plain form. Raw secrets never reach an operation
    (``validate_no_raw_secrets``), so the arguments carry none."""
    from .lane_caller import required_tier
    lane, tool = str(operation.get("name", "")), str(operation.get("tool", ""))
    args = operation.get("args") if isinstance(operation.get("args"), Mapping) else {}
    entry = tool_policy(lane, tool)
    binds_key = bool(operation.get("credential_refs"))
    required = required_tier(lane, tool)
    if binds_key and required == "T1":
        required = "T2"   # the key rule (C-8)
    sent = guard_args(lane, tool, args)
    forced = {name: value for name, value in (entry.forced_args if entry else ())
              if value is not None}
    from .lane_credentials import keeps_key_grants
    keys = "granted keys pass" if keeps_key_grants(lane, tool) else "granted keys stripped"
    return {"lane": lane, "tool": tool, "listed": entry is not None,
            "required_tier": required,
            "requested_tier": str(operation.get("governance_tier") or "T1"),
            "t2": required != "T1", "binds_key": binds_key, "keys": keys,
            "effect": entry.effect if entry else "not reviewed: effect unknown",
            "reason": entry.reason if entry else _UNLISTED_REASON,
            "not_in_build": entry.not_in_build if entry else "",
            "forced_arguments": forced,
            "launch_grant": entry.launch_grant if entry else "",
            "dropped_arguments": sorted(set(args) - set(sent)),
            "arguments": sent, "requested_arguments": dict(args)}

