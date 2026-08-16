import json
import threading
import time

import pytest

import harness.gateway_operation_route as operation_route
from harness.evidence_json import canonical_bytes
from harness.gateway_envelope import parse_gateway_envelope
from harness.gateway_grant_route import authorize_gateway_operation, gateway_grant_post
from harness.gateway_operation import AuthorizedOperation
from harness.gateway_operation_process import WorkerOutcome
from harness.gateway_operation_route import (
    OperationEventBus, _frame, authorization_sha256,
    replay_authorization_sha256, route_gateway_operation,
)
from harness.gateway_operations import GatewayOperations
from harness.gateway_provider_adapter import freeze_execution_plan
from harness.journey_store import JourneyStore, MutationCommand

NOW = "2026-08-16T12:00:00Z"
OWNER = "owner_" + "a" * 32
JOURNEY = "jrn_" + "a" * 32

class Process:
    control_class = "windows_job_v1"
    def __init__(self, outcome):
        self.outcome, self.resume_calls = outcome, 0
    def resume(self): self.resume_calls += 1; return True
    def signal_tree(self): return True
    def wait(self, _timeout): return self.outcome
    def close(self): pass

class Factory:
    def __init__(self, process): self.process, self.calls = process, 0
    def create(self, _authorized, progress):
        self.calls += 1
        progress({"type": "assistant", "text": "bounded"})
        return self.process

def _setup(root, *, stream=True, authorize_calls=None):
    head = JourneyStore(root).create(MutationCommand(
        OWNER, JOURNEY, None, "genesis", "intake",
        {"legacy_label": None, "goal": "route", "intake": {},
         "occurred_at": NOW})).event_head_sha256
    operation = {"goal": "inspect", "endpoint": "local", "max_steps": 2,
                 "allow_write": False, "allow_exec": False, "stream": stream,
                 "data_refs": [], "credential_refs": []}

    def authorize(action, raw, **_):
        if authorize_calls is not None: authorize_calls.append(action)
        envelope = parse_gateway_envelope(action, raw)
        canonical = envelope.operation
        return AuthorizedOperation(
            canonical.action, canonical.tool, canonical.destination,
            canonical.operation, canonical.operation_sha256,
            canonical.arguments_sha256, canonical.scopes, canonical.data_refs,
            canonical.credential_refs, OWNER, JOURNEY,
            envelope.expected_event_head, envelope.client_request_id,
            envelope.grant_ref, "2026-08-16T12:02:00Z",
            freeze_execution_plan(canonical), {})

    service = GatewayOperations(
        root, clock=lambda: NOW, authorizer=authorize,
        credential_resolver=lambda value, _root: value)
    raw = json.dumps({"schema": "flywheel.gateway-operation/v1",
                      "journey_ref": JOURNEY, "expected_event_head": head,
                      "client_request_id": "agent-1", "grant_ref": "gnt_" + "a" * 32,
                      **operation}).encode()
    return service, raw

def test_nonstream_agent_waits_for_durable_terminal_and_returns_legacy_result(tmp_path):
    service, raw = _setup(tmp_path, stream=False)
    factory = Factory(Process(WorkerOutcome("completed", {"final": "answer"})))
    response = route_gateway_operation(
        "POST", "/api/agent", owner_ref=OWNER, raw=raw,
        content_type="application/json", service=service,
        process_factory=factory)
    assert response.status == 200 and response.body == {"final": "answer"}
    assert response.stream is None and factory.calls == 1

def test_stream_frames_snapshot_progress_terminal_then_done_with_crlf(tmp_path):
    service, raw = _setup(tmp_path)
    factory = Factory(Process(WorkerOutcome("completed", {"final": "answer"})))
    response = route_gateway_operation(
        "POST", "/api/agent", owner_ref=OWNER, raw=raw,
        content_type="application/json", service=service,
        process_factory=factory)
    wire = b"".join(response.stream or ())
    assert response.status == 200 and response.body is None
    assert b"event: snapshot\r\n" in wire
    assert b"event: progress\r\n" in wire
    assert b"event: terminal\r\n" in wire
    assert wire.endswith(b"data: [DONE]\r\n\r\n")
    ids = [int(line[4:]) for line in wire.split(b"\r\n")
           if line.startswith(b"id: ")]
    assert ids == sorted(set(ids))

def test_exact_start_replay_precedes_authorization_and_second_worker(tmp_path):
    calls = []
    service, raw = _setup(tmp_path, authorize_calls=calls)
    process = Process(WorkerOutcome("completed", {"ok": True}))
    factory = Factory(process)
    first = route_gateway_operation(
        "POST", "/api/agent", owner_ref=OWNER, raw=raw,
        content_type="application/json", service=service,
        process_factory=factory)
    b"".join(first.stream or ())
    replay = route_gateway_operation(
        "POST", "/api/agent", owner_ref=OWNER, raw=raw,
        content_type="application/json", service=service,
        process_factory=factory)
    b"".join(replay.stream or ())
    changed = json.loads(raw)
    changed["expected_event_head"] = "e" * 64
    mismatch = route_gateway_operation(
        "POST", "/api/agent", owner_ref=OWNER,
        raw=json.dumps(changed).encode(), content_type="application/json",
        service=service, process_factory=factory)
    assert calls == ["agent.run"] and factory.calls == 1
    assert mismatch.status == 409
    assert mismatch.body["error"]["code"] == "IDEMPOTENCY_MISMATCH"

def test_route_rejects_method_query_content_type_and_unknown_fields(tmp_path):
    service, raw = _setup(tmp_path)
    factory = Factory(Process(WorkerOutcome("completed", {})))
    cases = [
        ("PUT", "/api/agent", "", "application/json", raw),
        ("POST", "/api/agent", "extra=1", "application/json", raw),
        ("POST", "/api/agent", "", "text/plain", raw),
        ("POST", "/api/agent", "", "application/json", raw[:-1] + b',"x":1}'),
    ]
    for method, path, query, content, body in cases:
        response = route_gateway_operation(
            method, path, query=query, content_type=content,
            owner_ref=OWNER, raw=body, service=service,
            process_factory=factory)
        assert response.status in {405, 422}
        assert response.body["error"]["code"] == "INVALID_REQUEST"
    assert factory.calls == 0

def test_snapshot_result_and_watch_are_owner_only_and_strict(tmp_path):
    service, raw = _setup(tmp_path, stream=False)
    factory = Factory(Process(WorkerOutcome("completed", {"ok": True})))
    route_gateway_operation(
        "POST", "/api/agent", owner_ref=OWNER, raw=raw,
        content_type="application/json", service=service,
        process_factory=factory)
    operation_ref = next(iter(service.operation_refs(OWNER)))
    snapshot = route_gateway_operation(
        "GET", f"/api/operations/{operation_ref}", owner_ref=OWNER,
        service=service, process_factory=factory)
    result = route_gateway_operation(
        "GET", f"/api/operations/{operation_ref}/result", owner_ref=OWNER,
        service=service, process_factory=factory)
    hidden = route_gateway_operation(
        "GET", f"/api/operations/{operation_ref}",
        owner_ref="owner_" + "b" * 32, service=service,
        process_factory=factory)
    resumed = route_gateway_operation(
        "GET", f"/api/operations/{operation_ref}/events",
        query="after=4", owner_ref=OWNER, service=service,
        process_factory=factory)
    resumed_wire = b"".join(resumed.stream or ())
    oversized = route_gateway_operation(
        "GET", f"/api/operations/{operation_ref}/events",
        query="after=" + "9" * 5000, owner_ref=OWNER,
        service=service, process_factory=factory)
    assert snapshot.status == result.status == 200
    assert snapshot.body["state"] == "completed"
    assert result.body["schema"] == "flywheel.gateway-operation-result/v1"
    assert hidden.status == 404 and hidden.body["error"]["code"] == "NOT_FOUND"
    assert b"id: 5\r\nevent: terminal\r\n" in resumed_wire
    assert resumed_wire.endswith(b"id: 6\r\nevent: terminal\r\ndata: [DONE]\r\n\r\n")
    assert oversized.status == 422
    assert oversized.body["error"]["code"] == "INVALID_REQUEST"

def test_sse_line_and_buffer_bounds_reject_before_retaining_overflow(
        monkeypatch):
    line_value = {"value": "x" * 262_130}
    assert len(canonical_bytes(line_value)) <= 262_144
    with pytest.raises(Exception) as line_failure:
        _frame(1, "progress", line_value)
    assert getattr(line_failure.value, "code", None) == "EXTERNAL_ACTION_FAILED"
    bus = OperationEventBus()
    buffered = {"value": "x" * 210_000}
    for sequence in range(4):
        bus.publish(OWNER, f"op_{sequence:032x}", "progress", buffered)
    ref = "op_" + "f" * 32
    for _ in range(4):
        bus.publish(OWNER, ref, "progress", buffered)
    with pytest.raises(Exception) as buffer_failure:
        bus.publish(OWNER, ref, "progress", buffered)
    assert getattr(buffer_failure.value, "code", None) == "EXTERNAL_ACTION_FAILED"

    monkeypatch.setattr(operation_route, "_MAX_BUFFER_BYTES", 512)
    tiny_bus = OperationEventBus()
    with pytest.raises(Exception) as framing_failure:
        for sequence in range(20):
            tiny_bus.publish(OWNER, ref, "progress", {"step": sequence})
    assert getattr(framing_failure.value, "code", None) == "EXTERNAL_ACTION_FAILED"

def test_restart_watch_replays_durable_terminal_after_requested_sequence(tmp_path):
    service, raw = _setup(tmp_path, stream=False)
    factory = Factory(Process(WorkerOutcome("completed", {"ok": True})))
    route_gateway_operation(
        "POST", "/api/agent", owner_ref=OWNER, raw=raw,
        content_type="application/json", service=service,
        process_factory=factory)
    operation_ref = next(iter(service.operation_refs(OWNER)))
    restarted = GatewayOperations(tmp_path, clock=lambda: NOW)

    response = route_gateway_operation(
        "GET", f"/api/operations/{operation_ref}/events",
        query="after=7", owner_ref=OWNER, service=restarted,
        process_factory=factory)
    wire = b"".join(response.stream or ())

    assert b"id: 8\r\nevent: snapshot\r\n" in wire
    assert b"id: 9\r\nevent: terminal\r\n" in wire
    assert wire.endswith(b"id: 10\r\nevent: terminal\r\ndata: [DONE]\r\n\r\n")

def test_cancel_grant_is_exact_one_use_and_replay_digest_is_pure(tmp_path):
    head = JourneyStore(tmp_path).create(MutationCommand(
        OWNER, JOURNEY, None, "genesis", "intake",
        {"legacy_label": None, "goal": "cancel", "intake": {},
         "occurred_at": NOW})).event_head_sha256
    ref = "op_" + "c" * 32
    operation = {"operation_ref": ref, "timeout_ms": 5_000,
                 "data_refs": [], "credential_refs": []}
    prepared, status = gateway_grant_post(
        "/api/gateway-grants/prepare/operation.cancel",
        json.dumps({"schema": "flywheel.gateway-operation/v1",
                    "journey_ref": JOURNEY, "expected_event_head": head,
                    "client_request_id": "cancel-1",
                    "operation": operation}).encode(), owner_ref=OWNER,
        state_root=tmp_path, clock=lambda: NOW)
    approved, approved_status = gateway_grant_post(
        "/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": prepared["proposal_ref"]}).encode(),
        owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW)
    final = json.dumps({"schema": "flywheel.gateway-operation/v1",
                        "journey_ref": JOURNEY, "expected_event_head": head,
                        "client_request_id": "cancel-1",
                        "grant_ref": approved["grant_ref"], **operation}).encode()
    authorized = authorize_gateway_operation(
        "operation.cancel", final, owner_ref=OWNER,
        state_root=tmp_path, clock=lambda: NOW)

    assert status == approved_status == 200
    assert prepared["destination"] == {"kind": "operation", "ref": ref}
    assert prepared["tool"] == "operation.cancel"
    assert prepared["scopes"] == ["exec"]
    assert replay_authorization_sha256(
        parse_gateway_envelope("operation.cancel", final), OWNER,
        tmp_path) == authorization_sha256(authorized)
    changed = json.loads(final)
    changed["grant_ref"] = "gnt_" + "b" * 32
    with pytest.raises(Exception) as mismatch:
        replay_authorization_sha256(
            parse_gateway_envelope(
                "operation.cancel", json.dumps(changed).encode()),
            OWNER, tmp_path)
    assert getattr(mismatch.value, "code", None) == "IDEMPOTENCY_MISMATCH"
    with pytest.raises(Exception) as reused:
        authorize_gateway_operation(
            "operation.cancel", final, owner_ref=OWNER,
            state_root=tmp_path, clock=lambda: NOW)
    assert getattr(reused.value, "code", None) == "APPROVAL_EXPIRED"

def test_concurrent_exact_start_replays_before_second_authorization(tmp_path):
    calls = []
    service, raw = _setup(tmp_path, authorize_calls=calls)
    authorize = service.authorizer

    def slow_authorize(*args, **kwargs):
        time.sleep(.1)
        return authorize(*args, **kwargs)

    service.authorizer = slow_authorize
    factory = Factory(Process(WorkerOutcome("completed", {"ok": True})))
    gate, statuses = threading.Barrier(3), []

    def request():
        gate.wait()
        response = route_gateway_operation(
            "POST", "/api/agent", owner_ref=OWNER, raw=raw,
            content_type="application/json", service=service,
            process_factory=factory)
        b"".join(response.stream or ())
        statuses.append(response.status)

    threads = [threading.Thread(target=request) for _ in range(2)]
    for thread in threads: thread.start()
    gate.wait()
    for thread in threads: thread.join(2)

    assert statuses == [200, 200]
    assert calls == ["agent.run"] and factory.calls == 1
