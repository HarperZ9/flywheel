import hashlib
import json

from harness.claude_provider_session import ClaudeProviderSessionAdapter
from harness.evidence_json import canonical_sha256
from harness.gateway_operation_route import operation_ref_for
from harness.provider_session_contract import ProviderRuntimeBinding

from provider_session_fixtures import (
    JOURNEY,
    OWNER,
    dispatch,
    operation_result,
    provider_factory,
    reconcile_raw,
    service_with_journey,
    turn_raw,
)
from test_claude_provider_session_support import (
    FakeClient,
    binding,
    result_event,
)


class RuntimeEvidenceRegistry:
    def __init__(self, *, pin=True):
        self.pin = pin
        self.calls = []

    def reconcile_evidence(self, *, source_context, operation_ref,
                           state_root, **_):
        self.calls.append(dict(source_context))
        history = [
            {"type": "user", "uuid": "u1"},
            {"type": "assistant", "uuid": "a1"},
        ]
        folder = state_root / "runtime-evidence"
        folder.mkdir()
        history_raw = "\n".join(json.dumps(record) for record in history).encode()
        history_path = folder / f"{operation_ref}-history.jsonl"
        history_path.write_bytes(history_raw)
        terminal = {
            "provider": "claude",
            "native_session_id": source_context["provider_session"]["native_session_id"],
            "source_operation_ref": source_context["operation_ref"],
            "last_provider_event_id": source_context["provider_session"]["last_provider_event_id"],
            "input_sha256": source_context["input_sha256"],
            "terminal_result_sha256": "terminal-hash",
            "source_input_receipt_sha256": source_context["input_receipt_sha256"],
            "source_result_sha256": source_context["result_sha256"],
            "source_terminal_event_sha256": source_context["terminal_event_sha256"],
            "source_trace_head_sha256": source_context["trace_head_sha256"],
            "history_store_head_sha256": canonical_sha256(history),
        }
        terminal_raw = json.dumps(terminal, separators=(",", ":")).encode()
        terminal_path = folder / f"{operation_ref}-terminal.json"
        terminal_path.write_bytes(terminal_raw)
        evidence = {
            "owned_history": {
                "type": "jsonl",
                "path": f"runtime-evidence/{operation_ref}-history.jsonl",
                "sha256": hashlib.sha256(history_raw).hexdigest(),
            },
            "terminal_observation": {
                "type": "json",
                "path": f"runtime-evidence/{operation_ref}-terminal.json",
                "sha256": hashlib.sha256(terminal_raw).hexdigest(),
            },
        }
        if not self.pin:
            del evidence["owned_history"]["sha256"]
            del evidence["terminal_observation"]["sha256"]
        return evidence


def test_gateway_reconcile_uses_runtime_evidence_not_request_fields(tmp_path):
    service, head = service_with_journey(tmp_path)
    registry = RuntimeEvidenceRegistry()
    client = FakeClient(events=[result_event("session-a")])
    adapter = ClaudeProviderSessionAdapter(
        client_supplier=lambda: client,
        transport_supplier=lambda: client,
        runtime_binding_supplier=binding,
        idle_timeout_s=0.01,
        max_events=8,
    )
    factory = provider_factory(adapters={"claude": adapter}, registry=registry)

    dispatch(service, turn_raw(head, provider="claude", input="hello"), factory)
    source_ref = operation_ref_for(OWNER, JOURNEY, "turn-1")
    head = service.snapshot(OWNER, source_ref).event_head_sha256
    dispatch(
        service,
        reconcile_raw(head, provider="claude", target_operation_ref=source_ref),
        factory,
        path="/api/provider-sessions/reconcile",
    )

    proof_ref = operation_ref_for(OWNER, JOURNEY, "reconcile-1")
    proof = operation_result(service, proof_ref)
    assert proof["history_status"] == "complete"
    assert proof["side_effect_status"] == "native_terminal_observed"
    assert proof["source_operation_ref"] == source_ref
    assert proof["source_input_sha256"] == registry.calls[0]["input_sha256"]


def test_gateway_reconcile_rejects_unpinned_runtime_evidence(tmp_path):
    service, head = service_with_journey(tmp_path)
    registry = RuntimeEvidenceRegistry(pin=False)
    client = FakeClient(events=[result_event("session-a")])
    adapter = ClaudeProviderSessionAdapter(
        client_supplier=lambda: client,
        transport_supplier=lambda: client,
        runtime_binding_supplier=binding,
        idle_timeout_s=0.01,
        max_events=8,
    )
    factory = provider_factory(adapters={"claude": adapter}, registry=registry)

    dispatch(service, turn_raw(head, provider="claude", input="hello"), factory)
    source_ref = operation_ref_for(OWNER, JOURNEY, "turn-1")
    head = service.snapshot(OWNER, source_ref).event_head_sha256
    dispatch(
        service,
        reconcile_raw(head, provider="claude", target_operation_ref=source_ref),
        factory,
        path="/api/provider-sessions/reconcile",
    )

    proof_ref = operation_ref_for(OWNER, JOURNEY, "reconcile-1")
    proof = operation_result(service, proof_ref)
    assert proof["reason"] == "AGENT_BINDING_DRIFT"
    assert proof["detail_code"] == "missing_owned_pointer_sha256"


def test_gateway_rejects_browser_authored_claude_reconcile_evidence(tmp_path):
    service, head = service_with_journey(tmp_path)
    response = dispatch(
        service,
        reconcile_raw(
            head,
            provider="claude",
            owned_history=[],
            terminal_observation={},
        ),
        provider_factory(adapters={}),
        path="/api/provider-sessions/reconcile",
    )

    assert response.status == 422
    assert response.body["error"]["code"] == "INVALID_REQUEST"
