import pytest
import io
import json

from harness import gateway, plugins
from harness.gateway_actions import (
    GatewayDispatchError, dispatch_authorized, dispatch_builtin,
)
from harness.gateway_grant_route import gateway_grant_post
from harness.gateway_operation import AuthorizedOperation
from harness.journey_store import JourneyStore, MutationCommand


NOW = "2026-08-15T12:00:00Z"
OWNER = "owner_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
JOURNEY = "jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _operation(action, body):
    return AuthorizedOperation.for_test(
        action=action, operation=body,
        scopes={
            "plugin.probe": ("exec", "network", "plugin"),
            "plugin.call": ("write", "exec", "network", "plugin"),
            "plugin.register": ("write", "plugin"),
            "plugin.toggle": ("write", "plugin"),
            "plugin.remove": ("write", "plugin"),
        }[action])


@pytest.mark.parametrize("action", [
    "plugin.probe", "plugin.call", "plugin.register",
    "plugin.toggle", "plugin.remove",
])
def test_plugin_dispatch_invokes_only_the_exact_selected_adapter(action):
    calls = []
    handlers = {name: (lambda op, name=name: calls.append(
        (name, dict(op.operation))) or {"ok": name}) for name in [
            "plugin.probe", "plugin.call", "plugin.register",
            "plugin.toggle", "plugin.remove"]}
    result = dispatch_authorized(_operation(action, {"name": "bounded"}),
                                 handlers)
    assert result == {"ok": action}
    assert calls == [(action, {"name": "bounded"})]


def test_missing_or_wrong_adapter_cannot_fall_through_to_plugin_start():
    calls = []
    operation = _operation("plugin.probe", {"name": "bounded"})
    with pytest.raises(GatewayDispatchError) as failure:
        dispatch_authorized(operation, {"plugin.call": lambda _: calls.append(1)})
    assert failure.value.code == "INVALID_REQUEST"
    assert calls == []


def test_plugin_failure_is_fixed_and_never_echoes_exception():
    def fail(_):
        raise OSError("C:/private/secret")
    with pytest.raises(GatewayDispatchError) as failure:
        dispatch_authorized(_operation("plugin.call", {
            "name": "bounded", "tool": "run", "arguments": {},
            "credential_refs": []}), {"plugin.call": fail})
    assert failure.value.code == "STORE_COMMIT_FAILED"
    assert "private" not in str(failure.value)


def test_gateway_probe_adapter_removes_internal_stderr(monkeypatch):
    monkeypatch.setattr(plugins, "probe_plugin", lambda _name: {
        "name": "bounded", "kind": "lane", "status": "unreachable",
        "detail": "server stderr: C:/private/secret",
    })
    result, status = dispatch_builtin(
        _operation("plugin.probe", {"name": "bounded"}))
    assert status == 200
    assert result == {"name": "bounded", "kind": "lane",
                      "status": "unreachable",
                      "detail": "plugin probe is unavailable"}


def _handler(tmp_path, body):
    raw, sent = json.dumps(body).encode(), {}
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path, handler.owner_ref = "/api/plugins/probe", OWNER
    handler.flywheel_home, handler.clock = tmp_path, lambda: NOW
    handler.headers = type("Headers", (), {"get": lambda _, key, default=None:
        str(len(raw)) if key == "Content-Length" else default})()
    handler.rfile = io.BytesIO(raw)
    handler._json = lambda value, code=200: sent.update(body=value, code=code)
    handler._post()
    return sent


def test_gateway_plugin_route_dispatches_only_after_exact_one_use_grant(
        tmp_path, monkeypatch):
    head = JourneyStore(tmp_path / "state").create(MutationCommand(
        OWNER, JOURNEY, None, "create-1", "intake",
        {"legacy_label": None, "goal": "plugin", "intake": {},
         "occurred_at": NOW})).event_head_sha256
    prepare = {"schema": "flywheel.gateway-operation/v1",
               "journey_ref": JOURNEY, "expected_event_head": head,
               "client_request_id": "request-1",
               "operation": {"name": "gather"}}
    proposal, _ = gateway_grant_post(
        "/api/gateway-grants/prepare/plugin.probe", json.dumps(prepare).encode(),
        owner_ref=OWNER, state_root=tmp_path / "state", clock=lambda: NOW)
    approval, _ = gateway_grant_post(
        "/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": proposal["proposal_ref"]}).encode(),
        owner_ref=OWNER, state_root=tmp_path / "state", clock=lambda: NOW)
    calls = []
    monkeypatch.setattr(plugins, "probe_plugin", lambda name: calls.append(name)
                        or {"status": "live"})
    final = {key: prepare[key] for key in prepare if key != "operation"}
    final.update(prepare["operation"]); final["grant_ref"] = approval["grant_ref"]
    assert _handler(tmp_path, final)["code"] == 200
    assert calls == ["gather"]
    assert _handler(tmp_path, final)["code"] == 403
    assert calls == ["gather"]


def test_dispatch_exception_burns_consumed_grant(tmp_path, monkeypatch):
    head = JourneyStore(tmp_path / "state").create(MutationCommand(
        OWNER, JOURNEY, None, "create-1", "intake",
        {"legacy_label": None, "goal": "plugin", "intake": {},
         "occurred_at": NOW})).event_head_sha256
    prepare = {"schema": "flywheel.gateway-operation/v1",
               "journey_ref": JOURNEY, "expected_event_head": head,
               "client_request_id": "request-1",
               "operation": {"name": "gather"}}
    proposal, _ = gateway_grant_post(
        "/api/gateway-grants/prepare/plugin.probe", json.dumps(prepare).encode(),
        owner_ref=OWNER, state_root=tmp_path / "state", clock=lambda: NOW)
    approval, _ = gateway_grant_post(
        "/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": proposal["proposal_ref"]}).encode(),
        owner_ref=OWNER, state_root=tmp_path / "state", clock=lambda: NOW)
    calls = []
    monkeypatch.setattr(plugins, "probe_plugin", lambda name: calls.append(name)
                        or (_ for _ in ()).throw(OSError()))
    final = {key: prepare[key] for key in prepare if key != "operation"}
    final.update(prepare["operation"]); final["grant_ref"] = approval["grant_ref"]
    assert _handler(tmp_path, final)["code"] == 500
    assert _handler(tmp_path, final)["code"] == 403
    assert calls == ["gather"]
