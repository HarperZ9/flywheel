from dataclasses import replace
import json
import threading

import pytest

from harness.gateway_operation import AuthorizedOperation, thaw_operation
from harness.gateway_envelope import parse_gateway_envelope
from harness.gateway_operation_process import WorkerOutcome
from harness.gateway_operations import (
    GatewayOperations, cancel_operation, start_operation,
)
from harness.gateway_provider_adapter import ExecutionPlan
from harness.journey_store import JourneyStore, MutationCommand

NOW = "2026-08-16T12:00:00Z"
OWNER = "owner_" + "a" * 32
OTHER = "owner_" + "b" * 32
JOURNEY = "jrn_" + "a" * 32

def _events(root):
    directory = root / "journeys" / "v2" / "owners" / OWNER / JOURNEY / "events"
    return [json.loads(path.read_bytes()) for path in sorted(directory.glob("*.json"))]

def _authorized(root, *, request="agent-1", operation=None):
    operation = operation or {
        "goal": "inspect", "endpoint": "local", "max_steps": 2,
        "allow_write": False, "allow_exec": False, "stream": True,
        "data_refs": [], "credential_refs": [],
    }
    store = JourneyStore(root)
    if not store.list(OWNER):
        head = store.create(MutationCommand(
            OWNER, JOURNEY, None, "genesis", "intake",
            {"legacy_label": None, "goal": "terminal stop", "intake": {},
             "occurred_at": NOW})).event_head_sha256
    else:
        head = store.load(OWNER, JOURNEY)["event_head_sha256"]
    base = AuthorizedOperation.for_test(
        action="agent.run", operation=operation,
        scopes=("network",))
    return replace(
        base, owner_ref=OWNER, journey_ref=JOURNEY,
        expected_event_head=head, client_request_id=request,
        execution_plan=ExecutionPlan("c" * 64, (), ()),
        credential_bindings={})


class Process:
    control_class = "windows_job_v1"
    def __init__(self, outcome=None, *, signal=True, confirm=True):
        self.outcome = outcome
        self.signal_result = signal
        self.confirm = confirm
        self.resume_calls = self.signal_calls = 0
        self.wait_calls = []
        self.ready = threading.Event()
    def resume(self):
        self.resume_calls += 1
        return True
    def signal_tree(self):
        self.signal_calls += 1
        if self.signal_result and self.confirm and self.outcome is None:
            self.outcome = WorkerOutcome("cancelled", {"stopped": True})
            self.ready.set()
        return self.signal_result
    def wait(self, timeout_s):
        self.wait_calls.append(timeout_s)
        self.ready.wait(timeout_s)
        return self.outcome
    def close(self):
        self.signal_tree()

class Factory:
    def __init__(self, process, root, gate=None):
        self.process, self.root, self.gate = process, root, gate
        self.calls = 0
        self.created = threading.Event()
    def create(self, authorized, progress):
        self.calls += 1
        assert _events(self.root)[-1]["event_type"] == "operation_queued"
        self.created.set()
        if self.gate is not None:
            self.gate.wait(2)
        return self.process

def _cancel_raw(snapshot, operation_ref, *, request="stop-1", grant="gnt_" + "d" * 32,
                timeout=5000):
    return json.dumps({
        "schema": "flywheel.gateway-operation/v1", "journey_ref": JOURNEY,
        "expected_event_head": snapshot.event_head_sha256,
        "client_request_id": request, "grant_ref": grant,
        "operation_ref": operation_ref, "timeout_ms": timeout,
        "data_refs": [], "credential_refs": [],
    }).encode()

def _authorize_action(action, raw, *, owner_ref, **_):
    envelope = parse_gateway_envelope(action, raw)
    operation = envelope.operation
    base = AuthorizedOperation.for_test(
        action=action, operation=thaw_operation(operation.operation),
        scopes=operation.scopes)
    return replace(
        base, owner_ref=owner_ref, journey_ref=envelope.journey_ref,
        expected_event_head=envelope.expected_event_head,
        client_request_id=envelope.client_request_id,
        grant_ref=envelope.grant_ref,
        execution_plan=ExecutionPlan("f" * 64, (), ()),
        credential_bindings={})

def _service(root):
    return GatewayOperations(
        root, clock=lambda: NOW, authorizer=_authorize_action,
        credential_resolver=lambda value, _root: value)

def test_start_orders_queue_create_start_resume_and_seals_one_terminal(tmp_path):
    gate = threading.Event()
    process = Process(WorkerOutcome("completed", {"final": "answer"}))
    process.ready.set()
    service = GatewayOperations(tmp_path, clock=lambda: NOW)
    factory = Factory(process, tmp_path, gate)
    queued = start_operation(
        authorized=_authorized(tmp_path), service=service,
        process_factory=factory)
    assert queued.state == "queued" and factory.created.wait(1)
    assert process.resume_calls == 0
    gate.set()
    terminal = service.wait_terminal(OWNER, queued.operation_ref, 2)
    kinds = [event["event_type"] for event in _events(tmp_path)]
    assert kinds[-3:] == ["operation_queued", "operation_started",
                          "operation_completed"]
    assert process.resume_calls == 1 and terminal.state == "completed"
    assert service.result(OWNER, queued.operation_ref)["result"] == {
        "final": "answer"}
    assert kinds.count("operation_completed") == 1

def test_identical_start_replays_but_changed_identity_is_mismatch(tmp_path):
    process = Process(WorkerOutcome("completed", {"ok": True}))
    process.ready.set()
    service = GatewayOperations(tmp_path, clock=lambda: NOW)
    authorized = _authorized(tmp_path)
    factory = Factory(process, tmp_path)
    first = start_operation(
        authorized=authorized, service=service, process_factory=factory)
    service.wait_terminal(OWNER, first.operation_ref, 2)

    replay = start_operation(
        authorized=authorized, service=service, process_factory=factory)
    assert replay.state == "completed" and factory.calls == 1
    changed = replace(authorized, operation_sha256="e" * 64)
    with pytest.raises(Exception) as failure:
        start_operation(
            authorized=changed, service=service, process_factory=factory)
    assert getattr(failure.value, "code", None) == "IDEMPOTENCY_MISMATCH"

def test_worker_cannot_claim_cancelled_without_durable_cancel_request(tmp_path):
    process = Process(WorkerOutcome("cancelled", {"stopped": True}))
    process.ready.set()
    service = GatewayOperations(tmp_path, clock=lambda: NOW)
    queued = start_operation(
        authorized=_authorized(tmp_path), service=service,
        process_factory=Factory(process, tmp_path))
    terminal = service.wait_terminal(OWNER, queued.operation_ref, 2)
    assert terminal.state == "failed"
    assert service.result(OWNER, queued.operation_ref)["result"] == {
        "reason": "EXTERNAL_ACTION_FAILED"}
    kinds = [event["event_type"] for event in _events(tmp_path)]
    assert "operation_cancelled" not in kinds

def test_oversized_result_seals_one_fixed_result_failure(tmp_path):
    process = Process(WorkerOutcome("completed", {"value": "x" * 1_048_576}))
    process.ready.set()
    service = GatewayOperations(tmp_path, clock=lambda: NOW)
    queued = start_operation(
        authorized=_authorized(tmp_path), service=service,
        process_factory=Factory(process, tmp_path))

    terminal = service.wait_terminal(OWNER, queued.operation_ref, 2)
    sealed = service.result(OWNER, queued.operation_ref)

    assert terminal.state == "failed"
    assert sealed["result"] == {"reason": "RESULT_SEAL_FAILED"}
    assert [event["event_type"] for event in _events(tmp_path)].count(
        "operation_failed") == 1

def test_stop_signals_once_and_replay_never_consumes_or_signals_again(tmp_path):
    process = Process()
    authorizations = []

    def authorize(action, raw, **kwargs):
        authorizations.append(raw)
        return _authorize_action(action, raw, **kwargs)

    service = GatewayOperations(
        tmp_path, clock=lambda: NOW, authorizer=authorize,
        credential_resolver=lambda value, _root: value)
    factory = Factory(process, tmp_path)
    running = start_operation(
        authorized=_authorized(tmp_path), service=service,
        process_factory=factory)
    factory.created.wait(1)
    while service.snapshot(OWNER, running.operation_ref).state != "running":
        pass
    raw = _cancel_raw(
        service.snapshot(OWNER, running.operation_ref), running.operation_ref)

    first = cancel_operation(
        action="operation.cancel", raw=raw, owner_ref=OWNER, service=service)
    replay = cancel_operation(
        action="operation.cancel", raw=raw, owner_ref=OWNER, service=service)

    assert first.state == replay.state == "cancelled"
    assert len(authorizations) == 1 and process.signal_calls == 1
    kinds = [event["event_type"] for event in _events(tmp_path)]
    assert kinds.count("cancel_requested") == 1
    assert kinds.count("operation_cancelled") == 1


def test_natural_completion_racing_stop_is_never_coerced_to_cancelled(tmp_path):
    class CompletionWins(Process):
        def signal_tree(self):
            self.signal_calls += 1
            self.outcome = WorkerOutcome("completed", {"final": "natural"})
            self.ready.set()
            return True

    process = CompletionWins()
    service = _service(tmp_path)
    running = start_operation(
        authorized=_authorized(tmp_path), service=service,
        process_factory=Factory(process, tmp_path))
    while service.snapshot(OWNER, running.operation_ref).state != "running":
        pass
    raw = _cancel_raw(
        service.snapshot(OWNER, running.operation_ref), running.operation_ref)

    terminal = cancel_operation(
        action="operation.cancel", raw=raw, owner_ref=OWNER, service=service)

    kinds = [event["event_type"] for event in _events(tmp_path)]
    assert terminal.state == "completed" and process.signal_calls == 1
    assert kinds.count("operation_completed") == 1
    assert kinds.count("operation_cancelled") == 0


@pytest.mark.parametrize("signal,confirm", ((False, True), (True, False)))
def test_unconfirmed_stop_stays_cancel_requested(tmp_path, signal, confirm):
    process = Process(signal=signal, confirm=confirm)
    service = _service(tmp_path)
    running = start_operation(
        authorized=_authorized(tmp_path), service=service,
        process_factory=Factory(process, tmp_path))
    while service.snapshot(OWNER, running.operation_ref).state != "running":
        pass
    raw = _cancel_raw(
        service.snapshot(OWNER, running.operation_ref), running.operation_ref,
        timeout=1)

    with pytest.raises(Exception) as failure:
        cancel_operation(
            action="operation.cancel", raw=raw, owner_ref=OWNER,
            service=service)

    assert getattr(failure.value, "code", None) == "CANCEL_UNAVAILABLE"
    assert service.snapshot(OWNER, running.operation_ref).state == (
        "cancel_requested")
    assert not any(event["event_type"] == "operation_cancelled"
                   for event in _events(tmp_path))
    changed = json.loads(raw)
    changed["expected_event_head"] = "e" * 64
    with pytest.raises(Exception) as mismatch:
        cancel_operation(
            action="operation.cancel", raw=json.dumps(changed).encode(),
            owner_ref=OWNER, service=service)
    assert getattr(mismatch.value, "code", None) == "IDEMPOTENCY_MISMATCH"


def test_cross_owner_stop_is_non_enumerating_and_observer_close_is_inert(tmp_path):
    process = Process()
    service = _service(tmp_path)
    started = start_operation(
        authorized=_authorized(tmp_path), service=service,
        process_factory=Factory(process, tmp_path))
    while service.snapshot(OWNER, started.operation_ref).state != "running":
        pass
    observer = service.watch(OWNER, started.operation_ref, 0)
    next(observer)
    observer.close()
    before = [event["event_sha256"] for event in _events(tmp_path)]
    raw = _cancel_raw(
        service.snapshot(OWNER, started.operation_ref), started.operation_ref)

    with pytest.raises(Exception) as failure:
        cancel_operation(
            action="operation.cancel", raw=raw, owner_ref=OTHER,
            service=service)

    assert getattr(failure.value, "code", None) == "CANCEL_UNAVAILABLE"
    assert [event["event_sha256"] for event in _events(tmp_path)] == before
    assert process.signal_calls == 0
