"""Safety checks for the /api/agent route.

Every /api/agent request is canonicalized before an agent worker ever
starts: a blank goal or endpoint, a step budget above the runaway-loop
guard, or an unstated write/exec permission is rejected outright. The
request never reaches the agent, and nothing is silently substituted
in its place. This closes a gap in the operation-route rewrite: the
canonicalizer already enforces these rules, but nothing exercised them
through the route a client actually posts to.
"""
from __future__ import annotations

import json
import time
from harness.gateway_agent_binding import freeze_agent_binding
from harness.plan_run_snapshot import thaw_json

from harness.gateway_operation import canonicalize_operation
from harness.gateway_operation_process import _run_agent
from harness.gateway_operation_route import route_gateway_operation

_OWNER = "owner_" + "a" * 32
_JOURNEY = "jrn_" + "a" * 32
_HEAD = "a" * 64
_GRANT = "gnt_" + "a" * 32

_OPERATION = {
    "goal": "fix the bug", "endpoint": "anthropic", "max_steps": 6,
    "allow_write": False, "allow_exec": False, "stream": False,
    "data_refs": [], "credential_refs": [],
}


def _post_agent(operation: dict):
    raw = json.dumps({
        "schema": "flywheel.gateway-operation/v1", "journey_ref": _JOURNEY,
        "expected_event_head": _HEAD, "client_request_id": "agent-1",
        "grant_ref": _GRANT, **operation,
    }).encode()
    # A malformed operation is refused during canonicalization, before the
    # route ever touches the owning service or starts a worker, so both
    # can be left unset here.
    return route_gateway_operation(
        "POST", "/api/agent", owner_ref=_OWNER, raw=raw,
        content_type="application/json", service=None, process_factory=None)


def _assert_rejected(operation: dict) -> None:
    response = _post_agent(operation)
    assert response.status == 422
    assert response.body["error"]["code"] == "INVALID_REQUEST"


def test_agent_route_rejects_a_blank_goal():
    _assert_rejected(dict(_OPERATION, goal=""))


def test_agent_route_rejects_a_blank_endpoint():
    _assert_rejected(dict(_OPERATION, endpoint=""))


def test_agent_route_rejects_a_step_budget_above_the_runaway_guard():
    _assert_rejected(dict(_OPERATION, max_steps=99))
    # the boundary itself still goes through untouched: the guard refuses
    # what is over budget, it does not quietly shrink an in-range request
    accepted = canonicalize_operation(
        "agent.run", dict(_OPERATION, max_steps=12))
    assert accepted.operation["max_steps"] == 12


def test_agent_route_refuses_to_infer_write_or_exec_permission():
    for key in ("allow_write", "allow_exec"):
        operation = {name: value for name, value in _OPERATION.items()
                     if name != key}
        _assert_rejected(operation)


def test_agent_route_denied_permission_reaches_the_agent_call_unchanged(
        tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    seen = {}

    def fake_run(goal, endpoint, **kwargs):
        seen.update(kwargs)
        return {"final": "done", "steps": 1, "verified": True,
                "checkpoint": "abc", "endpoint": endpoint}

    monkeypatch.setattr("harness.router_agent.run_router_agent", fake_run)
    from harness.gateway_agent_trace import AgentTrace
    trace = AgentTrace(tmp_path, "owner_" + "a" * 32,
                       "jrn_" + "b" * 32, "op_" + "c" * 32)
    operation = dict(_OPERATION, endpoint="stub", root=str(tmp_path))
    binding = thaw_json(freeze_agent_binding(canonicalize_operation("agent.run", operation), tmp_path))
    _run_agent(operation, {}, tmp_path, tmp_path, trace=trace, binding=binding,
               deadline=time.monotonic() + binding["budget"]["timeout_s"])
    assert seen["allow_write"] is False
    assert seen["allow_exec"] is False
    assert seen["max_steps"] == 6
