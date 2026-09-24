import json
from types import SimpleNamespace

from harness.gateway_envelope import parse_gateway_envelope
from harness.gateway_operation import AuthorizedOperation
from harness.gateway_operations import GatewayOperations
from harness.gateway_operation_route import route_gateway_operation
from harness.gateway_provider_adapter import freeze_execution_plan
from harness.journey_store import JourneyStore, MutationCommand


NOW = "2026-09-16T12:00:00Z"
OWNER = "owner_" + "a" * 32
JOURNEY = "jrn_" + "a" * 32


def create_journey(root, *, journey_ref=JOURNEY, request_id="genesis"):
    return JourneyStore(root).create(MutationCommand(
        OWNER, journey_ref, None, request_id, "intake",
        {"legacy_label": None, "goal": "provider session", "intake": {},
         "occurred_at": NOW})).event_head_sha256


def service_with_journey(root, *, authorize=True, journey_ref=JOURNEY):
    head = create_journey(root, journey_ref=journey_ref)
    # The production lock budget. A 0.5 s wait expired on a loaded Windows
    # runner while the operation's worker held the journey lock, and the
    # stream reported STORE_BUSY for a store that was only contended.
    kwargs = {"clock": lambda: NOW}
    if authorize:
        kwargs["authorizer"] = _authorizer(root)
        kwargs["credential_resolver"] = lambda value, _root: value
    return GatewayOperations(root, **kwargs), head


def _authorizer(root):
    def authorize(action, raw, **_):
        envelope = parse_gateway_envelope(action, raw)
        canonical = envelope.operation
        return AuthorizedOperation(
            canonical.action, canonical.tool, canonical.destination,
            canonical.operation, canonical.operation_sha256,
            canonical.arguments_sha256, canonical.scopes, canonical.data_refs,
            canonical.credential_refs, OWNER, envelope.journey_ref,
            envelope.expected_event_head, envelope.client_request_id,
            envelope.grant_ref, "2026-09-16T12:05:00Z",
            freeze_execution_plan(
                canonical, owner_ref=OWNER, state_root=root, workspace_root=root),
            {},
        )
    return authorize


def provider_factory(*, adapters=None, approval_resolver=None, approval_broker=None, registry=None):
    return SimpleNamespace(
        provider_session_adapters=dict(adapters or {}),
        provider_session_approval_resolver=approval_resolver,
        provider_session_approval_broker=approval_broker,
        provider_session_registry=registry,
    )


def turn_raw(head, *, request_id="turn-1", grant=None, journey_ref=JOURNEY,
             **changes):
    operation = {
        "provider": "codex",
        "workspace_ref": "workspace-a",
        "config_digest": "cfg-a",
        "permission_scope": {"mode": "manual"},
        "input": [{"type": "input_text", "text": "hi"}],
        "stream": True,
        "resume_policy": "new_thread",
        "data_refs": [],
        "credential_refs": [],
        "capability_digest": "cap-a",
        "provider_binding_ref": "psb_" + "a" * 32,
        "timeout_s": 1,
    }
    operation.update(changes)
    return _raw(head, request_id, grant, operation, journey_ref=journey_ref)


def resume_raw(head, *, request_id="resume-1", grant=None, journey_ref=JOURNEY,
               **changes):
    operation = {
        "provider": "codex",
        "source_operation_ref": "op_" + "b" * 32,
        "workspace_ref": "workspace-a",
        "config_digest": "cfg-a",
        "data_refs": [],
        "credential_refs": [],
        "history_limit": 20,
        "provider_binding_ref": "psb_" + "a" * 32,
        "stream": True,
        "timeout_s": 1,
    }
    operation.update(changes)
    return _raw(head, request_id, grant, operation, journey_ref=journey_ref)


def reconcile_raw(head, *, request_id="reconcile-1", grant=None,
                  journey_ref=JOURNEY, **changes):
    operation = {
        "provider": "codex",
        "target_operation_ref": "op_" + "b" * 32,
        "workspace_ref": "workspace-a",
        "config_digest": "cfg-a",
        "reason": "disconnect_after_effect",
        "data_refs": [],
        "credential_refs": [],
        "history_limit": 20,
        "provider_binding_ref": "psb_" + "a" * 32,
        "stream": True,
        "timeout_s": 1,
    }
    operation.update(changes)
    return _raw(head, request_id, grant, operation, journey_ref=journey_ref)


def dispatch(service, raw, factory, path="/api/provider-sessions/turn"):
    response = route_gateway_operation(
        "POST", path, owner_ref=OWNER, raw=raw, content_type="application/json",
        service=service, process_factory=factory)
    if response.stream is not None:
        b"".join(response.stream)
    return response


def only_operation_ref(service):
    refs = service.operation_refs(OWNER)
    assert len(refs) == 1
    return next(iter(refs))


def operation_result(service, operation_ref=None):
    ref = only_operation_ref(service) if operation_ref is None else operation_ref
    return service.result(OWNER, ref)["result"]


def _raw(head, request_id, grant, operation, *, journey_ref=JOURNEY):
    body = {
        "schema": "flywheel.gateway-operation/v1",
        "journey_ref": journey_ref,
        "expected_event_head": head,
        "client_request_id": request_id,
        "grant_ref": grant or "gnt_" + "a" * 32,
        **operation,
    }
    return json.dumps(body, separators=(",", ":")).encode()

