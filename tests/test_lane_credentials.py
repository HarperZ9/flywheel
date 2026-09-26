"""A provider key saved in the app reaches one lane child, for one granted call.

The key moves by the existing credential_refs path: the grant names an opaque
ref, the plan freezes the slot name (never the value), the value is resolved
after the grant is consumed, and it joins only the launch of the lane that call
spawns. A planted fake value stands in for a real key throughout.
"""
import hashlib
import json
import logging
import sys
import textwrap

import pytest

from harness.credential_handles import CredentialBindings, CredentialHandleStore
from harness.gateway_operation import AuthorizedOperation, GatewayOperationError
from harness.mcp_client import LaunchSpec

FAKE = "planted-fake-key-value-0123456789"
OWNER = "owner_" + "a" * 32
SLOT = "EXAMPLE_API_KEY"
_STUB = textwrap.dedent("""
    import hashlib, json, os, sys
    marker = os.environ.get("STUB_MARKER")
    if marker:
        open(marker, "w").close()
    for line in sys.stdin:
        msg = json.loads(line)
        if "id" not in msg:
            continue
        result = {}
        if msg["method"] == "initialize":
            result = {"protocolVersion": "2025-06-18", "capabilities": {},
                      "serverInfo": {"name": "stub", "version": "1"}}
        elif msg["method"] == "tools/call":
            params = msg["params"]
            value = os.environ.get(params["arguments"]["name"], "")
            body = ({"present": bool(value), "cwd": os.getcwd(),
                     "sha256": hashlib.sha256(value.encode()).hexdigest()}
                    if params["name"] == "probe.env" else {"echo": value})
            result = {"content": [{"type": "text", "text": json.dumps(body)}]}
        print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}),
              flush=True)
""")


@pytest.fixture
def granted(monkeypatch):
    import harness.lanes as lanes
    registry = {"forum": {"env_allow": [SLOT]}}
    monkeypatch.setattr(lanes, "read_registry", lambda: registry)
    return registry


def _operation(lane: str, refs: list[str]) -> AuthorizedOperation:
    return AuthorizedOperation.for_test(action="lane.call", operation={
        "name": lane, "tool": f"{lane}.route", "args": {}, "data_refs": [],
        "credential_refs": refs}, scopes=("exec", "network", "plugin"))


def _bind(tmp_path, name=SLOT) -> str:
    store = CredentialHandleStore(tmp_path, keychain_get=lambda _n: FAKE)
    return store.bind(OWNER, name).credential_ref


def test_plan_freezes_a_granted_slot_without_reading_its_value(
        tmp_path, granted, monkeypatch):
    from harness import keychain
    from harness.gateway_provider_adapter import freeze_execution_plan

    ref = _bind(tmp_path)
    reads = []
    monkeypatch.setattr(keychain, "keychain_get", lambda n: reads.append(n))
    plan = freeze_execution_plan(_operation("forum", [ref]), owner_ref=OWNER,
                                 state_root=tmp_path)
    assert plan.required_slots == (SLOT,)
    assert plan.credential_refs == (ref,)
    assert reads == []
    assert FAKE not in repr(plan)


@pytest.mark.parametrize("lane,registry", [
    ("forum", {}),                                  # not granted
    ("forum", {"forum": {"env_allow": ["OTHER"]}}),  # another name granted
    ("gather", {"forum": {"env_allow": [SLOT]}}),    # granted to another lane
    ("bulletin", {"bulletin": {"env_allow": [SLOT]}}),  # http lane spawns nothing
])
def test_plan_refuses_a_slot_not_granted_to_that_lane(
        tmp_path, monkeypatch, lane, registry):
    import harness.lanes as lanes
    from harness.gateway_provider_adapter import freeze_execution_plan

    ref = _bind(tmp_path)
    monkeypatch.setattr(lanes, "read_registry", lambda: registry)
    with pytest.raises(GatewayOperationError) as refused:
        freeze_execution_plan(_operation(lane, [ref]), owner_ref=OWNER,
                              state_root=tmp_path)
    assert refused.value.code == "PERMISSION_REQUIRED"


def test_resolved_bindings_carry_the_value_only_after_the_grant(
        tmp_path, granted, monkeypatch):
    from harness import keychain
    from harness.gateway_provider_adapter import freeze_execution_plan, resolve_credentials
    from dataclasses import replace

    ref = _bind(tmp_path)
    operation = _operation("forum", [ref])
    plan = freeze_execution_plan(operation, owner_ref=OWNER, state_root=tmp_path)
    monkeypatch.setattr(keychain, "resolve_credential", lambda _n: FAKE)
    authorized = resolve_credentials(replace(operation, execution_plan=plan), tmp_path)
    assert authorized.credential_bindings.value_for(SLOT) == FAKE
    assert FAKE not in repr(authorized)


def _stub_launch(tmp_path, extra=()):
    from harness.bundled_lane_env import bundled_child_environment
    import os
    script = tmp_path / "stub_lane.py"
    script.write_text(_STUB, encoding="utf-8")
    env = bundled_child_environment(os.environ, git_dir=None)
    env.update(extra)
    return LaunchSpec((sys.executable, str(script)), str(tmp_path),
                      tuple(sorted(env.items())), False)


def _call(tool, bindings, launch, monkeypatch):
    import harness.lanes as lanes
    from harness.lane_call_route import handle_lane_call
    monkeypatch.setattr(lanes, "resolve_mcp_launch", lambda _name: launch)
    return handle_lane_call(f"/api/lane/forum/{tool}",
                            {"args": {"name": SLOT}}, bindings)


def test_fake_key_reaches_the_bound_child_only_and_no_response(
        tmp_path, granted, monkeypatch, caplog):
    import os
    caplog.set_level(logging.DEBUG)
    launch = _stub_launch(tmp_path)
    bound, status = _call("probe.env", CredentialBindings({SLOT: FAKE}),
                          launch, monkeypatch)
    assert status == 200
    assert bound["present"] is True
    assert bound["sha256"] == hashlib.sha256(FAKE.encode()).hexdigest()
    unbound, _ = _call("probe.env", None, launch, monkeypatch)
    assert unbound["present"] is False
    assert SLOT not in os.environ
    assert FAKE not in json.dumps([bound, unbound]) + caplog.text


def test_a_tool_that_echoes_the_key_is_redacted(tmp_path, granted, monkeypatch):
    launch = _stub_launch(tmp_path)
    echoed, status = _call("probe.echo", CredentialBindings({SLOT: FAKE}),
                           launch, monkeypatch)
    assert status == 200
    assert FAKE not in json.dumps(echoed)
    assert echoed["echo"] == "[REDACTED]"


def test_a_binding_the_lane_no_longer_grants_never_launches(
        tmp_path, monkeypatch):
    import harness.lanes as lanes
    monkeypatch.setattr(lanes, "read_registry", lambda: {})
    marker = tmp_path / "started"
    launch = _stub_launch(tmp_path, {"STUB_MARKER": str(marker)})
    result, status = _call("probe.env", CredentialBindings({SLOT: FAKE}),
                           launch, monkeypatch)
    assert status == 403
    assert result["code"] == "PERMISSION_REQUIRED"
    assert not marker.exists()
    assert FAKE not in json.dumps(result)


def test_roster_row_names_a_granted_key_but_never_its_value(
        tmp_path, monkeypatch):
    import harness.lanes as lanes
    monkeypatch.setenv(SLOT, FAKE)
    monkeypatch.setattr(lanes, "read_registry",
                        lambda: {"mneme": {"env_allow": [SLOT]}})
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda lane: None)
    monkeypatch.setattr(lanes, "_importable", lambda name: True)
    monkeypatch.setattr(lanes, "_installed_version", lambda lane: lane.version)
    launch = lanes.resolve_mcp_launch("mneme")
    assert dict(launch.env_overrides)[SLOT] == FAKE
    row = lanes.lane_status("mneme", probe=False)
    assert FAKE not in json.dumps(row)
