from __future__ import annotations

import json

from harness.evidence_json import canonical_sha256
from harness.gateway_grant_route import authorize_gateway_operation
from harness.gateway_grant_route import gateway_grant_post
from harness.gateway_operation_route import route_gateway_operation

from provider_session_fixtures import OWNER, JOURNEY, NOW, create_journey, turn_raw


class BindingRegistry:
    def __init__(self, *, config="cfg-derived", cap="cap-derived", admitted=True):
        self.calls = []
        self.config = config
        self.cap = cap
        self.admitted = admitted

    def binding_snapshot(self, **kwargs):
        self.calls.append(kwargs)
        op = kwargs["operation"]
        material = {
            "owner_ref": kwargs["owner_ref"],
            "journey_ref": kwargs["journey_ref"],
            "event_head": kwargs["expected_event_head"],
            "provider": op["provider"],
            "workspace_ref": op["workspace_ref"],
            "config_digest": self.config,
            "capability_digest": self.cap,
        }
        return {
            "schema": "flywheel.provider-session-runtime-binding/v1",
            "provider": op["provider"],
            "owner_ref": kwargs["owner_ref"],
            "journey_ref": kwargs["journey_ref"],
            "workspace_ref": op["workspace_ref"],
            "model": op.get("model", ""),
            "permission_scope_sha256": canonical_sha256(op.get("permission_scope", {})),
            "config_digest": self.config,
            "capability_digest": self.cap,
            "provider_binding_ref": "psb_" + canonical_sha256(material)[:32],
            "admitted": self.admitted,
            "reason": "admitted" if self.admitted else "AGENT_NATIVE_RUNTIME_DISABLED",
            "limitations": [],
            "runtime_kind": "fake",
            "observed_at_event_head": kwargs["expected_event_head"],
        }


def binding_body(head, **changes):
    body = {
        "schema": "flywheel.provider-session-binding-request/v1",
        "journey_ref": JOURNEY,
        "expected_event_head": head,
        "provider": "codex",
        "workspace_ref": "workspace-a",
        "model": "model-a",
        "permission_scope": {"mode": "manual"},
        "config_digest": "caller-forged",
        "capability_digest": "caller-forged",
    }
    body.update(changes)
    return json.dumps(body, separators=(",", ":")).encode()


def test_binding_route_returns_gateway_derived_digest_and_owner_journey(tmp_path):
    head = create_journey(tmp_path)
    registry = BindingRegistry()
    response = route_gateway_operation(
        "POST", "/api/provider-sessions/binding", owner_ref=OWNER,
        service=type("S", (), {"state_root": tmp_path})(),
        process_factory=type("F", (), {"provider_session_registry": registry})(),
        raw=binding_body(head), content_type="application/json")

    assert response.status == 200
    assert response.body["config_digest"] == "cfg-derived"
    assert response.body["capability_digest"] == "cap-derived"
    assert response.body["provider_binding_ref"].startswith("psb_")
    assert "caller-forged" not in json.dumps(response.body)
    assert registry.calls[0]["owner_ref"] == OWNER
    assert registry.calls[0]["journey_ref"] == JOURNEY
    assert registry.calls[0]["expected_event_head"] == head


def test_binding_route_rejects_wrong_journey_head_before_registry(tmp_path):
    create_journey(tmp_path)
    registry = BindingRegistry()
    response = route_gateway_operation(
        "POST", "/api/provider-sessions/binding", owner_ref=OWNER,
        service=type("S", (), {"state_root": tmp_path})(),
        process_factory=type("F", (), {"provider_session_registry": registry})(),
        raw=binding_body("0" * 64), content_type="application/json")

    assert response.status != 200
    assert registry.calls == []


def _grant_request(head, operation):
    return json.dumps({
        "schema": "flywheel.gateway-operation/v1",
        "journey_ref": JOURNEY,
        "expected_event_head": head,
        "client_request_id": "grant-1",
        "operation": operation,
    }, separators=(",", ":")).encode()


def _authorized_raw(head, operation, grant_ref):
    body = {
        "schema": "flywheel.gateway-operation/v1",
        "journey_ref": JOURNEY,
        "expected_event_head": head,
        "client_request_id": "grant-1",
        "grant_ref": grant_ref,
        **operation,
    }
    return json.dumps(body, separators=(",", ":")).encode()


def test_grant_prepare_freezes_provider_binding_and_rejects_tampering(tmp_path):
    head = create_journey(tmp_path)
    registry = BindingRegistry()
    snapshot = registry.binding_snapshot(
        owner_ref=OWNER, journey_ref=JOURNEY, expected_event_head=head,
        operation={"provider": "codex", "workspace_ref": "workspace-a",
                   "model": "model-a", "permission_scope": {"mode": "manual"}})
    operation = {
        "provider": "codex",
        "workspace_ref": "workspace-a",
        "model": "model-a",
        "config_digest": snapshot["config_digest"],
        "capability_digest": snapshot["capability_digest"],
        "provider_binding_ref": snapshot["provider_binding_ref"],
        "permission_scope": {"mode": "manual"},
        "input": [{"type": "input_text", "text": "hi"}],
        "stream": True,
        "resume_policy": "new_thread",
        "data_refs": [],
        "credential_refs": [],
    }

    prepared, status = gateway_grant_post(
        "/api/gateway-grants/prepare/provider.session.turn",
        _grant_request(head, operation), owner_ref=OWNER, state_root=tmp_path,
        clock=lambda: NOW, provider_session_registry=registry)

    assert status == 200
    review = prepared["summary"]["provider_session"]
    assert review["provider_binding_ref"] == snapshot["provider_binding_ref"]
    assert review["config_digest"] == "cfg-derived"
    assert review["capability_digest"] == "cap-derived"
    approved, approved_status = gateway_grant_post(
        "/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": prepared["proposal_ref"]}).encode(),
        owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW)
    assert approved_status == 200
    authorized = authorize_gateway_operation(
        "provider.session.turn",
        _authorized_raw(head, operation, approved["grant_ref"]),
        owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW,
        provider_session_registry=registry)
    assert authorized.execution_plan.provider_session_binding is not None

    tampered = {**operation, "config_digest": "cfg-forged"}
    denied, denied_status = gateway_grant_post(
        "/api/gateway-grants/prepare/provider.session.turn",
        _grant_request(head, tampered), owner_ref=OWNER, state_root=tmp_path,
        clock=lambda: NOW, provider_session_registry=registry)

    assert denied_status != 200
    assert denied["error"]["code"] in {"AGENT_BINDING_DRIFT", "PERMISSION_DENIED"}


def test_grant_authorize_rejects_provider_binding_drift_before_dispatch(tmp_path):
    head = create_journey(tmp_path)
    registry = BindingRegistry()
    snapshot = registry.binding_snapshot(
        owner_ref=OWNER, journey_ref=JOURNEY, expected_event_head=head,
        operation={"provider": "codex", "workspace_ref": "workspace-a",
                   "permission_scope": {"mode": "manual"}})
    operation = {
        "provider": "codex",
        "workspace_ref": "workspace-a",
        "config_digest": snapshot["config_digest"],
        "capability_digest": snapshot["capability_digest"],
        "provider_binding_ref": snapshot["provider_binding_ref"],
        "permission_scope": {"mode": "manual"},
        "input": "hi",
        "stream": True,
        "resume_policy": "new_thread",
        "data_refs": [],
        "credential_refs": [],
    }
    prepared, status = gateway_grant_post(
        "/api/gateway-grants/prepare/provider.session.turn",
        _grant_request(head, operation), owner_ref=OWNER, state_root=tmp_path,
        clock=lambda: NOW, provider_session_registry=registry)
    assert status == 200
    approved, approved_status = gateway_grant_post(
        "/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": prepared["proposal_ref"]}).encode(),
        owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW)
    assert approved_status == 200
    registry.config = "cfg-drift"

    try:
        authorize_gateway_operation(
            "provider.session.turn",
            _authorized_raw(head, operation, approved["grant_ref"]),
            owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW,
            provider_session_registry=registry)
    except Exception as exc:
        assert getattr(exc, "code", "") == "AGENT_BINDING_DRIFT"
    else:
        raise AssertionError("provider binding drift was accepted")


def test_grant_prepare_rejects_wrong_head_before_registry_call(tmp_path):
    create_journey(tmp_path)
    registry = BindingRegistry()
    operation = {
        "provider": "codex",
        "workspace_ref": "workspace-a",
        "config_digest": "cfg-derived",
        "capability_digest": "cap-derived",
        "provider_binding_ref": "psb_" + "a" * 32,
        "permission_scope": {"mode": "manual"},
        "input": "hi",
        "stream": True,
        "resume_policy": "new_thread",
        "data_refs": [],
        "credential_refs": [],
    }

    response, status = gateway_grant_post(
        "/api/gateway-grants/prepare/provider.session.turn",
        _grant_request("0" * 64, operation), owner_ref=OWNER,
        state_root=tmp_path, clock=lambda: NOW,
        provider_session_registry=registry)

    assert status != 200
    assert response["error"]["code"] == "HEAD_CONFLICT"
    assert registry.calls == []


def test_provider_binding_ref_is_required_for_provider_turn(tmp_path):
    head = create_journey(tmp_path)
    raw = turn_raw(head, provider_binding_ref=None)
    response = route_gateway_operation(
        "POST", "/api/provider-sessions/turn", owner_ref=OWNER,
        service=type("S", (), {"state_root": tmp_path, "clock": lambda: NOW})(),
        process_factory=type("F", (), {})(), raw=raw,
        content_type="application/json")

    assert response.status == 422
    assert response.body["error"]["code"] == "INVALID_REQUEST"
