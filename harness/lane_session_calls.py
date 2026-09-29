"""How a lane call reaches a lane session (``lane_session``).

Two routes send session tools there:

- ``/api/lane/<lane>/<tool>`` (``lane_caller.call_lane_tool``), after the tier,
  the bulletin access check, the argument guards and the admission check. A
  granted T2 call widens the launch for its one tool before this point, so
  relay ``local_agent_start`` reaches the session only on a call a granted T2
  operation carries;
- the phone's relay read routes (``/api/relay/status``, ``/result``,
  ``/runs``, through ``gateway_lane_calls._relay_mcp_call``), which apply the
  same argument guards and admission here, so a run started on the lane route
  is the run those routes read.

A session child outlives the call that started it, so no provider key joins
it: a call that would bind one is refused, and the launch loses the lane's
key-shaped grants whatever the tier (the key rule, POLICY-DECISION C-8).
"""
from __future__ import annotations

from typing import Any

from .mcp_client import LaunchSpec


def session_call(lane: str, tool: str, command: LaunchSpec, args: dict[str, Any],
                 timeout: float, credential_bindings: object = None) -> dict[str, Any]:
    """Send one checked call to the lane's session."""
    from . import lane_session
    from .lane_credentials import binds_any_key, credential_refused, strip_key_grants
    if binds_any_key(credential_bindings):
        return credential_refused(lane, tool)
    launch = strip_key_grants(lane, command)
    return lane_session.default_pool().call(lane, tool, launch, args, timeout)


def relay_session_call(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """A relay session read from the phone routes, through the same guards as
    the lane route. Raises what ``resolve_mcp_launch`` raises."""
    from .lane_tier_gate import admission_refusal, argument_refusal, guard_args
    from .lane_tool_policy import DEFAULT_TIMEOUT_S, tool_policy
    from .lanes import resolve_mcp_launch
    refused = argument_refusal("relay", tool, args)
    if refused is not None:
        return refused
    command = resolve_mcp_launch("relay")
    refused = admission_refusal(command, "relay", tool)
    if refused is not None:
        return refused
    entry = tool_policy("relay", tool)
    timeout = entry.timeout_s if entry is not None else DEFAULT_TIMEOUT_S
    return session_call("relay", tool, command, guard_args("relay", tool, args), timeout)
