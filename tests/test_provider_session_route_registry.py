from __future__ import annotations

import json

from harness.evidence_json import canonical_sha256
from harness.gateway_grant_route import gateway_grant_post
from harness.gateway_operation_route import route_gateway_operation
from harness.gateway_operations import GatewayOperations
from harness.provider_session_contract import (
    ProviderOperationOutcome,
    ProviderRuntimeBinding,
)

from provider_session_fixtures import OWNER, JOURNEY, NOW, create_journey


class RouteAdapter:
    provider = "codex"

    def __init__(self, *, config: str, cap: str):
        self.config = config
        self.cap = cap
        self.calls = 0

    def current_binding(self):
        return ProviderRuntimeBinding("codex", "workspace-a", self.config, self.cap)

    def start_turn(self, request, *, emit, request_approval, cancelled):
        self.calls += 1
        emit.native("native_binding", provider="codex",
                    native_session_id="s-route",
                    native_thread_id="t-route",
                    native_turn_id="turn-route",
                    config_digest=self.config, capability_digest=self.cap)
        return ProviderOperationOutcome.completed({
            "provider_session": {
                "provider": "codex",
                "native_session_id": "s-route",
                "native_thread_id": "t-route",
                "native_turn_id": "turn-route",
                "last_provider_event_id": "event-route",
                "config_digest": self.config,
                "capability_digest": self.cap,
            },
            "route_registry": self.config,
            "history_status": "complete",
            "side_effect_status": "input_sent",
        })

    def resume(self, request, *, emit):
        raise AssertionError("resume not used")

    def reconcile(self, request, *, emit):
        raise AssertionError("reconcile not used")


class RouteRegistry:
    def __init__(self, *, config: str = "cfg-route", cap: str = "cap-route"):
        self.config = config
        self.cap = cap
        self.calls = []
        self.adapter = RouteAdapter(config=config, cap=cap)

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
            "permission_scope_sha256": canonical_sha256(
                op.get("permission_scope", {})),
            "config_digest": self.config,
            "capability_digest": self.cap,
            "provider_binding_ref": "psb_" + canonical_sha256(material)[:32],
            "admitted": True,
            "reason": "admitted",
            "limitations": [],
            "runtime_kind": "fake",
            "observed_at_event_head": kwargs["expected_event_head"],
        }

    def adapter_for(self, *, authorized, operation_ref):
        return self.adapter


def _operation(registry: RouteRegistry, head: str) -> dict:
    seed = {
        "provider": "codex",
        "workspace_ref": "workspace-a",
        "model": "model-a",
        "permission_scope": {"mode": "manual"},
    }
    binding = registry.binding_snapshot(
        owner_ref=OWNER, journey_ref=JOURNEY, expected_event_head=head,
        operation=seed)
    registry.calls.clear()
    return {
        **seed,
        "config_digest": binding["config_digest"],
        "capability_digest": binding["capability_digest"],
        "provider_binding_ref": binding["provider_binding_ref"],
        "input": [{"type": "input_text", "text": "hi"}],
        "stream": False,
        "resume_policy": "new_thread",
        "data_refs": [],
        "credential_refs": [],
        "timeout_s": 1,
    }


def _grant_request(head: str, operation: dict, *, request_id: str) -> bytes:
    return json.dumps({
        "schema": "flywheel.gateway-operation/v1",
        "journey_ref": JOURNEY,
        "expected_event_head": head,
        "client_request_id": request_id,
        "operation": operation,
    }, separators=(",", ":")).encode()


def _authorized_raw(head: str, operation: dict, grant_ref: str, *,
                    request_id: str) -> bytes:
    return json.dumps({
        "schema": "flywheel.gateway-operation/v1",
        "journey_ref": JOURNEY,
        "expected_event_head": head,
        "client_request_id": request_id,
        "grant_ref": grant_ref,
        **operation,
    }, separators=(",", ":")).encode()


def _prepare_and_approve(tmp_path, registry: RouteRegistry, head: str,
                         operation: dict, *, request_id: str) -> str:
    prepared, status = gateway_grant_post(
        "/api/gateway-grants/prepare/provider.session.turn",
        _grant_request(head, operation, request_id=request_id),
        owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW,
        provider_session_registry=registry)
    assert status == 200
    approved, approved_status = gateway_grant_post(
        "/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": prepared["proposal_ref"]}).encode(),
        owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW)
    assert approved_status == 200
    return approved["grant_ref"]


def _factory(registry: RouteRegistry):
    return type("Factory", (), {"provider_session_registry": registry})()


def test_real_grant_backed_provider_session_route_uses_runtime_registry(tmp_path):
    head = create_journey(tmp_path)
    registry = RouteRegistry()
    operation = _operation(registry, head)
    grant_ref = _prepare_and_approve(
        tmp_path, registry, head, operation, request_id="route-turn")
    service = GatewayOperations(tmp_path, clock=lambda: NOW)

    response = route_gateway_operation(
        "POST", "/api/provider-sessions/turn", owner_ref=OWNER,
        service=service, process_factory=_factory(registry),
        raw=_authorized_raw(head, operation, grant_ref, request_id="route-turn"),
        content_type="application/json")

    assert response.status == 200
    assert response.body["route_registry"] == "cfg-route"
    assert registry.adapter.calls == 1


def test_real_grant_backed_provider_session_route_rejects_wrong_registry(tmp_path):
    head = create_journey(tmp_path)
    prepared_registry = RouteRegistry(config="cfg-prepared")
    operation = _operation(prepared_registry, head)
    grant_ref = _prepare_and_approve(
        tmp_path, prepared_registry, head, operation, request_id="route-drift")
    dispatch_registry = RouteRegistry(config="cfg-dispatch")
    service = GatewayOperations(tmp_path, clock=lambda: NOW)

    response = route_gateway_operation(
        "POST", "/api/provider-sessions/turn", owner_ref=OWNER,
        service=service, process_factory=_factory(dispatch_registry),
        raw=_authorized_raw(head, operation, grant_ref, request_id="route-drift"),
        content_type="application/json")

    assert response.status == 409
    assert response.body["error"]["code"] == "AGENT_BINDING_DRIFT"
    assert dispatch_registry.calls
    assert dispatch_registry.adapter.calls == 0
