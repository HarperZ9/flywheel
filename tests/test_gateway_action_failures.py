import json
import io

import pytest

from harness.gateway_actions import GatewayDispatchError, dispatch_authorized
from harness.gateway_operation import AuthorizedOperation, GatewayOperationError
from harness.gateway_provider_adapter import fixed_external_failure
from harness.gateway_grant_route import (
    authorize_gateway_operation, gateway_grant_post)
from harness.journey_store import JourneyStore, MutationCommand
from harness import gateway


OPERATIONS = {
    "chat.complete": {"model": "local", "messages": [
        {"role": "user", "content": "hello"}], "stream": False,
        "data_refs": [], "credential_refs": []},
    "agent.run": {"goal": "inspect", "endpoint": "local", "max_steps": 2,
        "allow_write": False, "allow_exec": False, "stream": False,
        "data_refs": [], "credential_refs": []},
    "workflow.run": {"workflow": "research-brief", "goal": "inspect",
        "endpoint": "local", "allow_write": False, "allow_exec": False,
        "data_refs": [], "credential_refs": []},
    "plugin.probe": {"name": "gather", "data_refs": [],
        "credential_refs": []},
    "plugin.call": {"name": "gather", "tool": "find", "arguments": {},
        "data_refs": [], "credential_refs": []},
    "plugin.register": {"name": "x", "command": ["tool"], "detail": "safe",
        "requires": [], "data_refs": [], "credential_refs": []},
    "plugin.toggle": {"name": "x", "enabled": True, "data_refs": [],
        "credential_refs": []},
    "plugin.remove": {"name": "x", "data_refs": [], "credential_refs": []},
    "marketplace.install": {"name": "fetch", "data_refs": [],
        "credential_refs": []},
    "marketplace.add": {"name": "x", "command": ["tool"], "detail": "safe",
        "requires": [], "data_refs": [], "credential_refs": []},
    "marketplace.remove": {"name": "fetch", "data_refs": [],
        "credential_refs": []},
}
ROUTES = {
    "chat.complete": "/v1/chat/completions",
    "agent.run": "/api/agent", "workflow.run": "/api/workflow",
    "plugin.probe": "/api/plugins/probe",
    "plugin.call": "/api/plugins/call",
    "plugin.register": "/api/plugins/register",
    "plugin.toggle": "/api/plugins/toggle",
    "plugin.remove": "/api/plugins/remove",
    "marketplace.install": "/api/marketplace/install",
    "marketplace.add": "/api/marketplace/add",
    "marketplace.remove": "/api/marketplace/remove",
}


@pytest.mark.parametrize("action", OPERATIONS)
def test_every_assigned_action_uses_one_exact_adapter(action):
    calls = []
    operation = AuthorizedOperation.for_test(
        action=action, operation=OPERATIONS[action], scopes=())
    result = dispatch_authorized(
        operation, {action: lambda value: calls.append(value.action) or "ok"})
    assert result == "ok" and calls == [action]


def test_downstream_failure_is_fixed_and_carries_no_exception_text():
    operation = AuthorizedOperation.for_test(
        action="agent.run", operation=OPERATIONS["agent.run"], scopes=())
    with pytest.raises(GatewayDispatchError) as failure:
        dispatch_authorized(operation, {
            "agent.run": lambda _value: (_ for _ in ()).throw(
                RuntimeError("synthetic-marker-123456"))})
    assert failure.value.code == "EXTERNAL_ACTION_FAILED"
    assert "synthetic-marker" not in str(failure.value)
    body, status = fixed_external_failure()
    assert status == 502
    assert body == {"schema": "flywheel.evidence-transport-error/v1",
                    "error": {"code": "EXTERNAL_ACTION_FAILED",
                              "message": "authorized external action failed"}}


@pytest.mark.parametrize("action", OPERATIONS)
def test_every_action_consumes_one_exact_grant_before_one_dispatch(
        tmp_path, action):
    owner = "owner_" + "a" * 32
    journey = "jrn_" + "a" * 32
    now = "2026-08-15T12:00:00Z"
    head = JourneyStore(tmp_path).create(MutationCommand(
        owner, journey, None, "create-1", "intake",
        {"legacy_label": None, "goal": "bounded", "intake": {},
         "occurred_at": now})).event_head_sha256
    prepare = {"schema": "flywheel.gateway-operation/v1",
               "journey_ref": journey, "expected_event_head": head,
               "client_request_id": "request-1",
               "operation": OPERATIONS[action]}
    proposal, status = gateway_grant_post(
        f"/api/gateway-grants/prepare/{action}", json.dumps(prepare).encode(),
        owner_ref=owner, state_root=tmp_path, clock=lambda: now)
    assert status == 200
    approval, status = gateway_grant_post(
        "/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": proposal["proposal_ref"]}).encode(),
        owner_ref=owner, state_root=tmp_path, clock=lambda: now)
    assert status == 200
    final = {key: value for key, value in prepare.items() if key != "operation"}
    final.update(OPERATIONS[action]); final["grant_ref"] = approval["grant_ref"]
    authorized = authorize_gateway_operation(
        action, json.dumps(final).encode(), owner_ref=owner,
        state_root=tmp_path, clock=lambda: now)
    calls = []
    assert dispatch_authorized(
        authorized, {action: lambda op: calls.append(op.action) or "ok"}) == "ok"
    assert calls == [action]


def _final_body(root, action, *, approve=True):
    owner, journey = "owner_" + "a" * 32, "jrn_" + "a" * 32
    now = "2026-08-15T12:00:00Z"
    state = root / "state"
    head = JourneyStore(state).create(MutationCommand(
        owner, journey, None, "create-1", "intake",
        {"legacy_label": None, "goal": "bounded", "intake": {},
         "occurred_at": now})).event_head_sha256
    prepare = {"schema": "flywheel.gateway-operation/v1",
               "journey_ref": journey, "expected_event_head": head,
               "client_request_id": "request-1",
               "operation": OPERATIONS[action]}
    proposal, _ = gateway_grant_post(
        f"/api/gateway-grants/prepare/{action}", json.dumps(prepare).encode(),
        owner_ref=owner, state_root=state, clock=lambda: now)
    grant = proposal["planned_grant_ref"]
    if approve:
        approval, _ = gateway_grant_post(
            "/api/gateway-grants/approve-once",
            json.dumps({"proposal_ref": proposal["proposal_ref"]}).encode(),
            owner_ref=owner, state_root=state, clock=lambda: now)
        grant = approval["grant_ref"]
    final = {key: value for key, value in prepare.items() if key != "operation"}
    final.update(OPERATIONS[action]); final["grant_ref"] = grant
    return owner, now, final


def _different(action, body):
    field, value = {
        "chat.complete": ("model", "other"),
        "agent.run": ("goal", "other"),
        "workflow.run": ("goal", "other"),
        "plugin.probe": ("name", "forum"),
        "plugin.call": ("tool", "query"),
        "plugin.register": ("command", ["other"]),
        "plugin.toggle": ("enabled", False),
        "plugin.remove": ("name", "other"),
        "marketplace.install": ("name", "filesystem"),
        "marketplace.add": ("command", ["other"]),
        "marketplace.remove": ("name", "filesystem"),
    }[action]
    return {**body, field: value}


def _handler_post(root, path, owner, now, body):
    raw, sent = json.dumps(body).encode(), {}
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path, handler.owner_ref = path, owner
    handler.flywheel_home = handler.root = handler.run_root = root
    handler.clock, handler.serve_url = lambda: now, "http://local.invalid"
    handler.headers = type("Headers", (), {"get": lambda _, key, default=None:
        str(len(raw)) if key == "Content-Length" else default})()
    handler.rfile, handler.wfile = io.BytesIO(raw), io.BytesIO()
    handler.send_response = lambda code: sent.update(code=code)
    handler.send_header = handler.end_headers = handler._cors = lambda *_: None
    handler._post()
    return sent["code"], json.loads(handler.wfile.getvalue())


@pytest.mark.parametrize("action,path", ROUTES.items())
def test_every_http_final_route_refuses_without_burn_and_dispatches_once(
        tmp_path, monkeypatch, action, path):
    calls = []
    monkeypatch.setattr(
        "harness.gateway_actions.dispatch_builtin",
        lambda operation: (calls.append(operation.action) or ({"ok": True}, 200)))
    owner, now, body = _final_body(tmp_path, action)
    absent = {**body, "grant_ref": "gnt_" + "f" * 32}
    for denied in (absent, _different(action, body)):
        status, _ = _handler_post(tmp_path, path, owner, now, denied)
        assert status in {403, 422} and calls == []
    pending_root = tmp_path / "pending"
    other_owner, other_now, pending = _final_body(
        pending_root, action, approve=False)
    status, _ = _handler_post(
        pending_root, path, other_owner, other_now, pending)
    assert status == 403 and calls == []
    status, result = _handler_post(tmp_path, path, owner, now, body)
    assert status == 200 and result == {"ok": True} and calls == [action]
    status, _ = _handler_post(tmp_path, path, owner, now, body)
    assert status == 403 and calls == [action]


@pytest.mark.parametrize("action", [
    "chat.complete", "agent.run", "workflow.run"])
def test_guarded_provider_failures_are_fixed_and_never_persist_raw_text(
        tmp_path, monkeypatch, action):
    marker = "synthetic-provider-marker-123456"
    owner, now, body = _final_body(tmp_path, action)
    if action == "chat.complete":
        monkeypatch.setattr(gateway, "openai_chat", lambda *_args: (
            {"error": {"message": marker}}, 502, None, None, None))
    elif action == "agent.run":
        monkeypatch.setattr("harness.router_agent.run_router_agent",
                            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                                RuntimeError(marker)))
    else:
        monkeypatch.setattr("harness.workflows.run_workflow",
                            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                                RuntimeError(marker)))
    status, response = _handler_post(tmp_path, ROUTES[action], owner, now, body)
    assert status == 502 and response == fixed_external_failure()[0]
    assert marker not in b"".join(p.read_bytes() for p in tmp_path.rglob("*.*")).decode(
        "utf-8", errors="ignore")


def test_legacy_training_loop_failure_keeps_its_bounded_diagnostic(monkeypatch):
    monkeypatch.setattr(
        "harness.train_surface.loop_status",
        lambda: (_ for _ in ()).throw(RuntimeError("safe diagnostic")))
    sent = []
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path = "/api/train/loop"
    handler._json = lambda body, code=200: sent.append((body, code))
    handler._get()
    assert sent == [({"error": "RuntimeError: safe diagnostic"}, 502)]


def test_guarded_agent_sse_failure_is_fixed_in_stream_and_history(
        tmp_path, monkeypatch):
    marker = "synthetic-sse-marker-123456"
    monkeypatch.setattr(
        "harness.router_agent.run_router_agent",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(marker)))
    handler = gateway._Handler.__new__(gateway._Handler)
    handler._gateway_guarded = True
    handler.root = handler.run_root = tmp_path
    handler.wfile = io.BytesIO()
    handler.send_response = lambda *_: None
    handler.send_header = handler.end_headers = handler._cors = lambda *_: None
    handler._sse_agent({"goal": "inspect"}, "inspect", "local")
    public = handler.wfile.getvalue().decode()
    persisted = b"".join(path.read_bytes() for path in tmp_path.rglob("*.*"))
    assert marker not in public and marker.encode() not in persisted
    assert "EXTERNAL_ACTION_FAILED" in public and "[DONE]" in public


def test_persisted_plugin_and_marketplace_plans_refuse_raw_credentials(
        tmp_path, monkeypatch):
    from harness import marketplace, plugins
    marker = "synthetic-registry-marker-123456"
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    raw = {"name": "unsafe", "command": ["tool", "--token", marker],
           "detail": "unsafe", "enabled": True, "requires": [],
           "credential_refs": []}
    assert plugins.register_mcp(
        "unsafe", raw["command"], raw["detail"], requires=[],
        credential_refs=[]) == {"code": "PERMISSION_REQUIRED",
                                "error": "permission required"}
    assert not (tmp_path / "plugins.json").exists()
    assert marketplace.add_user_entry(
        "unsafe", raw["command"], raw["detail"], requires=[],
        credential_refs=[]) == {"code": "PERMISSION_REQUIRED",
                                "error": "permission required"}
    assert not (tmp_path / "catalog.json").exists()
    (tmp_path / "plugins.json").write_text(
        json.dumps({"schema": "flywheel.plugins/v1", "mcp": [raw]}),
        encoding="utf-8")
    (tmp_path / "catalog.json").write_text(
        json.dumps({"entries": [raw]}), encoding="utf-8")
    assert marker not in json.dumps(plugins.plugin_roster())
    assert marker not in json.dumps(marketplace.marketplace_catalog())
    with pytest.raises(plugins.PluginPermissionError):
        plugins.plugin_credentials("unsafe")
    with pytest.raises(plugins.PluginPermissionError):
        marketplace.marketplace_credentials("unsafe")
    calls = []
    result = plugins.probe_plugin(
        "unsafe", client_factory=lambda *_a, **_k: calls.append("constructed"))
    assert result == {"code": "PERMISSION_REQUIRED",
                      "error": "permission required"}
    assert calls == []
