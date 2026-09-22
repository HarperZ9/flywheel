from __future__ import annotations

import json
import threading
import time

from harness.evidence_json import canonical_sha256
from harness.gateway_operation_route import operation_ref_for, route_gateway_operation
from harness.provider_session_approval_broker import ProviderApprovalBroker
from harness.provider_session_contract import (
    ProviderApprovalRequest,
    ProviderOperationOutcome,
    ProviderRuntimeBinding,
)

from provider_session_fixtures import (
    OWNER, JOURNEY, dispatch, operation_result, provider_factory,
    service_with_journey, turn_raw,
)


class ApprovalAdapter:
    provider = "codex"

    def __init__(self):
        self.decision = None
        self.calls = 0

    def current_binding(self):
        return ProviderRuntimeBinding("codex", "workspace-a", "cfg-a", "cap-a")

    def start_turn(self, request, *, emit, request_approval, cancelled):
        self.calls += 1
        emit.native("native_binding", provider="codex", native_session_id="s1",
                    native_thread_id="t1", native_turn_id="turn1",
                    config_digest="cfg-a", capability_digest="cap-a")
        self.decision = request_approval(ProviderApprovalRequest(
            provider="codex",
            native_request_id="approval-1",
            tool="item/commandExecution/requestApproval",
            payload_sha256=canonical_sha256({"command": "git status"}),
            native_session_id="s1",
            native_thread_id="t1",
            native_turn_id="turn1",
            native_item_id="item1"))
        return ProviderOperationOutcome.completed({
            "provider_session": {
                "provider": "codex", "native_session_id": "s1",
                "native_thread_id": "t1", "native_turn_id": "turn1",
                "last_provider_event_id": "event-1",
                "config_digest": "cfg-a", "capability_digest": "cap-a"},
            "approval_behavior": self.decision.behavior,
            "approval_updated_input": self.decision.updated_input,
            "history_status": "complete",
            "side_effect_status": "input_sent",
        })

    def resume(self, request, *, emit):
        raise AssertionError("resume not used")

    def reconcile(self, request, *, emit):
        raise AssertionError("reconcile not used")


def _approval_raw(head, ref, identity, *, request_id="approval-response-1",
                  decision="allow", updated_input=None):
    operation = {
        "operation_ref": ref,
        "native_request_id": "approval-1",
        "request_identity": identity,
        "decision": decision,
        "client_response_id": request_id,
        "data_refs": [],
        "credential_refs": [],
    }
    if updated_input is not None:
        operation["updated_input"] = updated_input
    body = {
        "schema": "flywheel.gateway-operation/v1",
        "journey_ref": JOURNEY,
        "expected_event_head": head,
        "client_request_id": request_id,
        "grant_ref": "gnt_" + "c" * 32,
        **operation,
    }
    return json.dumps(body, separators=(",", ":")).encode()


def _wait_pending(broker, ref):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        rows = broker.pending(owner_ref=OWNER, operation_ref=ref)
        if rows:
            return rows[0]
        time.sleep(0.01)
    raise AssertionError("pending approval did not appear")


def _wait_result(service, ref):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            return operation_result(service, ref)
        except Exception:
            time.sleep(0.01)
    return operation_result(service, ref)


def test_live_approval_read_and_respond_sends_one_provider_decision(tmp_path):
    service, head = service_with_journey(tmp_path)
    adapter = ApprovalAdapter()
    broker = ProviderApprovalBroker(default_timeout_s=2)
    factory = provider_factory(adapters={"codex": adapter}, approval_broker=broker)
    ref = operation_ref_for(OWNER, JOURNEY, "turn-1")
    raw = turn_raw(head, permission_scope={
        "mode": "manual",
        "approval_policy": {
            "allow_tools": ["item/commandExecution/requestApproval"],
            "updated_input_keys": {"item/commandExecution/requestApproval": ["decision"]},
        },
    })

    response = route_gateway_operation(
        "POST", "/api/provider-sessions/turn", owner_ref=OWNER,
        service=service, process_factory=factory, raw=raw,
        content_type="application/json")
    assert response.status == 200
    pending = _wait_pending(broker, ref)

    read = route_gateway_operation(
        "GET", "/api/provider-sessions/approvals", owner_ref=OWNER,
        service=service, process_factory=factory,
        query=f"operation_ref={ref}")
    assert read.status == 200
    assert read.body["pending"][0]["request_identity"] == pending["request_identity"]
    assert read.body["pending"][0]["payload_sha256"] == pending["payload_sha256"]

    respond = route_gateway_operation(
        "POST", "/api/provider-sessions/approvals/respond", owner_ref=OWNER,
        service=service, process_factory=factory,
        raw=_approval_raw(service.snapshot(OWNER, ref).event_head_sha256, ref,
                          pending["request_identity"],
                          updated_input={"decision": "accept"}),
        content_type="application/json")
    assert respond.status == 200

    duplicate = route_gateway_operation(
        "POST", "/api/provider-sessions/approvals/respond", owner_ref=OWNER,
        service=service, process_factory=factory,
        raw=_approval_raw(service.snapshot(OWNER, ref).event_head_sha256, ref,
                          pending["request_identity"], request_id="approval-response-2",
                          updated_input={"decision": "decline"}),
        content_type="application/json")
    assert duplicate.status != 200

    result = _wait_result(service, ref)
    assert result["approval_behavior"] == "allow"
    assert result["approval_updated_input"] == {"decision": "accept"}
    assert adapter.calls == 1


def test_updated_input_outside_turn_envelope_is_rejected_without_answering(tmp_path):
    service, head = service_with_journey(tmp_path)
    adapter = ApprovalAdapter()
    broker = ProviderApprovalBroker(default_timeout_s=2)
    factory = provider_factory(adapters={"codex": adapter}, approval_broker=broker)
    ref = operation_ref_for(OWNER, JOURNEY, "turn-1")
    response = route_gateway_operation(
        "POST", "/api/provider-sessions/turn", owner_ref=OWNER,
        service=service, process_factory=factory,
        raw=turn_raw(head, permission_scope={
            "mode": "manual",
            "approval_policy": {
                "allow_tools": ["item/commandExecution/requestApproval"],
                "updated_input_keys": {"item/commandExecution/requestApproval": ["decision"]},
            },
        }), content_type="application/json")
    assert response.status == 200
    pending = _wait_pending(broker, ref)

    bad = route_gateway_operation(
        "POST", "/api/provider-sessions/approvals/respond", owner_ref=OWNER,
        service=service, process_factory=factory,
        raw=_approval_raw(service.snapshot(OWNER, ref).event_head_sha256, ref,
                          pending["request_identity"], updated_input={"command": "rm -rf ."}),
        content_type="application/json")
    assert bad.status != 200
    assert broker.pending(owner_ref=OWNER, operation_ref=ref)[0]["state"] == "pending"

    denied = route_gateway_operation(
        "POST", "/api/provider-sessions/approvals/respond", owner_ref=OWNER,
        service=service, process_factory=factory,
        raw=_approval_raw(service.snapshot(OWNER, ref).event_head_sha256, ref,
                          pending["request_identity"], request_id="deny-1",
                          decision="deny"),
        content_type="application/json")
    assert denied.status == 200
    result = _wait_result(service, ref)
    assert result["approval_behavior"] == "deny"


def test_concurrent_duplicate_approval_responses_serialize_to_one_decision(tmp_path):
    service, head = service_with_journey(tmp_path)
    adapter = ApprovalAdapter()
    broker = ProviderApprovalBroker(default_timeout_s=2)
    factory = provider_factory(adapters={"codex": adapter}, approval_broker=broker)
    ref = operation_ref_for(OWNER, JOURNEY, "turn-1")
    response = route_gateway_operation(
        "POST", "/api/provider-sessions/turn", owner_ref=OWNER,
        service=service, process_factory=factory,
        raw=turn_raw(head, permission_scope={
            "mode": "manual",
            "approval_policy": {
                "allow_tools": ["item/commandExecution/requestApproval"],
                "updated_input_keys": {"item/commandExecution/requestApproval": ["decision"]},
            },
        }), content_type="application/json")
    assert response.status == 200
    pending = _wait_pending(broker, ref)
    statuses = []
    lock = threading.Lock()

    def respond_once(request_id, decision):
        route = route_gateway_operation(
            "POST", "/api/provider-sessions/approvals/respond",
            owner_ref=OWNER, service=service, process_factory=factory,
            raw=_approval_raw(service.snapshot(OWNER, ref).event_head_sha256,
                              ref, pending["request_identity"],
                              request_id=request_id,
                              updated_input={"decision": decision}),
            content_type="application/json")
        with lock:
            statuses.append(route.status)

    threads = [
        threading.Thread(target=respond_once, args=("race-a", "accept")),
        threading.Thread(target=respond_once, args=("race-b", "decline")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert statuses.count(200) == 1
    result = _wait_result(service, ref)
    assert result["approval_behavior"] == "allow"
    assert result["approval_updated_input"] in (
        {"decision": "accept"}, {"decision": "decline"})


def test_broker_timeout_closes_pending_without_allow(tmp_path):
    service, head = service_with_journey(tmp_path)
    adapter = ApprovalAdapter()
    broker = ProviderApprovalBroker(default_timeout_s=0.05)
    factory = provider_factory(adapters={"codex": adapter}, approval_broker=broker)
    ref = operation_ref_for(OWNER, JOURNEY, "turn-1")

    dispatch(service, turn_raw(head), factory)
    result = operation_result(service, ref)

    assert result["approval_behavior"] == "deny"
    assert broker.pending(owner_ref=OWNER, operation_ref=ref) == []

