import json

from harness.claude_provider_session import ClaudeProviderSessionAdapter
from harness.evidence_json import canonical_sha256
from harness.gateway_grant_route import gateway_grant_post
from harness.gateway_operation_route import operation_ref_for
from harness.gateway_operations import GatewayOperations
from harness.provider_session_contract import ProviderRuntimeBinding

from provider_session_fixtures import (
    JOURNEY,
    NOW,
    OWNER,
    create_journey,
    dispatch,
    provider_factory,
)
from test_claude_provider_session_support import FakeClient, result_event


class ClaudeGrantRegistry:
    def __init__(self, client):
        self.client = client
        self.launch_configs = []

    def binding_snapshot(self, **kwargs):
        operation = kwargs["operation"]
        material = {
            "owner_ref": kwargs["owner_ref"],
            "journey_ref": kwargs["journey_ref"],
            "event_head": kwargs["expected_event_head"],
            "provider": "claude",
            "workspace_ref": operation["workspace_ref"],
        }
        return {
            "schema": "flywheel.provider-session-runtime-binding/v1",
            "provider": "claude",
            "owner_ref": kwargs["owner_ref"],
            "journey_ref": kwargs["journey_ref"],
            "workspace_ref": operation["workspace_ref"],
            "model": operation.get("model", ""),
            "permission_scope_sha256": canonical_sha256(
                operation.get("permission_scope", {})),
            "config_digest": "cfg-a",
            "capability_digest": "cap-a",
            "provider_binding_ref": "psb_" + canonical_sha256(material)[:32],
            "admitted": True,
            "reason": "admitted",
            "limitations": [],
            "runtime_kind": "fake-claude",
            "observed_at_event_head": kwargs["expected_event_head"],
        }

    def adapter_for(self, **_):
        def client_supplier(config):
            self.launch_configs.append(config)
            return self.client

        return ClaudeProviderSessionAdapter(
            client_supplier=client_supplier,
            runtime_binding_supplier=lambda: ProviderRuntimeBinding(
                "claude", "workspace-a", "cfg-a", "cap-a"),
            idle_timeout_s=0.01,
            max_events=8,
        )


class NoPermissionCustodyClient:
    def __init__(self):
        self.sent = []
        self.events = [result_event()]
        self.recovery_needed = False

    def send_text(self, text):
        self.sent.append(("text", text))

    def next_event(self, timeout=None):
        return self.events.pop(0) if self.events else None

    def next_control_request(self, timeout=None):
        return None

    def next_protocol_event(self, timeout=None):
        return None

    def has_pending_control_requests(self):
        return False

    def mark_recovery_needed(self):
        self.recovery_needed = True


def test_auto_permission_scope_launches_claude_with_manual_permission_mode(tmp_path):
    client = FakeClient(events=[result_event()])
    service, registry, ref = _dispatch_auto_grant(tmp_path, client)

    result = service.result(OWNER, ref)["result"]

    assert result["history_status"] == "missing_native_history"
    assert client.sent == [("text", "hello")]
    assert registry.launch_configs[0].permission_mode == "manual"


def test_auto_permission_scope_still_requires_manual_permission_custody(tmp_path):
    client = NoPermissionCustodyClient()
    service, registry, ref = _dispatch_auto_grant(tmp_path, client)

    result = service.result(OWNER, ref)["result"]

    assert result["reason"] == "AGENT_NATIVE_PROTOCOL_ERROR"
    assert result["surface_error"] == "missing_permission_response_surface"
    assert client.sent == []
    assert registry.launch_configs[0].permission_mode == "manual"


def _dispatch_auto_grant(tmp_path, client):
    head = create_journey(tmp_path)
    operation = _operation("auto")
    registry = ClaudeGrantRegistry(client)
    snapshot = registry.binding_snapshot(
        owner_ref=OWNER, journey_ref=JOURNEY, expected_event_head=head,
        operation=operation)
    operation.update({
        "config_digest": snapshot["config_digest"],
        "capability_digest": snapshot["capability_digest"],
        "provider_binding_ref": snapshot["provider_binding_ref"],
    })
    prepared, status = gateway_grant_post(
        "/api/gateway-grants/prepare/provider.session.turn",
        _grant_request(head, operation), owner_ref=OWNER,
        state_root=tmp_path, clock=lambda: NOW,
        provider_session_registry=registry)
    assert status == 200, prepared
    approved, approved_status = gateway_grant_post(
        "/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": prepared["proposal_ref"]}).encode(),
        owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW)
    assert approved_status == 200, approved
    service = GatewayOperations(tmp_path, clock=lambda: NOW)
    factory = provider_factory(registry=registry)
    raw = _authorized_raw(head, operation, approved["grant_ref"])

    response = dispatch(service, raw, factory)

    assert response.status == 200
    return service, registry, operation_ref_for(OWNER, JOURNEY, "turn-auto")


def _operation(mode):
    return {
        "provider": "claude",
        "workspace_ref": "workspace-a",
        "permission_scope": {"mode": mode},
        "input": "hello",
        "stream": True,
        "resume_policy": "new_thread",
        "data_refs": [],
        "credential_refs": [],
        "timeout_s": 1,
    }


def _grant_request(head, operation):
    return json.dumps({
        "schema": "flywheel.gateway-operation/v1",
        "journey_ref": JOURNEY,
        "expected_event_head": head,
        "client_request_id": "turn-auto",
        "operation": operation,
    }, separators=(",", ":")).encode()


def _authorized_raw(head, operation, grant_ref):
    return json.dumps({
        "schema": "flywheel.gateway-operation/v1",
        "journey_ref": JOURNEY,
        "expected_event_head": head,
        "client_request_id": "turn-auto",
        "grant_ref": grant_ref,
        **operation,
    }, separators=(",", ":")).encode()
