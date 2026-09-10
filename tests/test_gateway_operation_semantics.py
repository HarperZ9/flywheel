"""Operation semantics use the real controller without thread scheduling delays."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

import harness.gateway_operations as operations
from harness.gateway_operation import GatewayOperationError
from harness.gateway_operation_process import WorkerOutcome
from test_gateway_operations import Factory, NOW, OWNER, Process, _authorized, _events


class InlineThread:
    def __init__(self, *, target, args, daemon):
        assert daemon is True
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


@pytest.fixture
def inline_controller(monkeypatch):
    # Patch only this module's scheduler reference, never threading.Thread globally.
    # Real-thread lifecycle, cancellation, and sealing checks remain in their suite.
    monkeypatch.setattr(operations, "threading", SimpleNamespace(Thread=InlineThread))


def test_identical_start_replays_but_changed_identity_is_mismatch(tmp_path, inline_controller):
    process = Process(WorkerOutcome("completed", {"ok": True}))
    process.ready.set()
    service = operations.GatewayOperations(tmp_path, clock=lambda: NOW)
    authorized = _authorized(tmp_path)
    factory = Factory(process, tmp_path)
    first = operations.start_operation(
        authorized=authorized, service=service, process_factory=factory)
    assert service.snapshot(OWNER, first.operation_ref).state == "completed"
    assert service.result(OWNER, first.operation_ref)["result"] == {"ok": True}
    before = _events(tmp_path)

    replay = operations.start_operation(
        authorized=authorized, service=service, process_factory=factory)
    assert replay.state == "completed"
    assert replay.operation_ref == first.operation_ref
    changed = replace(authorized, operation_sha256="e" * 64)
    with pytest.raises(GatewayOperationError) as failure:
        operations.start_operation(
            authorized=changed, service=service, process_factory=factory)
    assert failure.value.code == "IDEMPOTENCY_MISMATCH"
    assert factory.calls == process.resume_calls == 1
    assert _events(tmp_path) == before
    assert sum(event["event_type"] == "operation_completed" for event in before) == 1


def test_worker_cannot_claim_cancelled_without_durable_cancel_request(tmp_path, inline_controller):
    process = Process(WorkerOutcome("cancelled", {"stopped": True}))
    process.ready.set()
    service = operations.GatewayOperations(tmp_path, clock=lambda: NOW)
    factory = Factory(process, tmp_path)
    queued = operations.start_operation(
        authorized=_authorized(tmp_path), service=service, process_factory=factory)
    assert service.snapshot(OWNER, queued.operation_ref).state == "failed"
    assert service.result(OWNER, queued.operation_ref)["result"] == {
        "reason": "EXTERNAL_ACTION_FAILED"}
    kinds = [event["event_type"] for event in _events(tmp_path)]
    assert "cancel_requested" not in kinds
    assert "operation_cancelled" not in kinds
    assert kinds.count("operation_failed") == 1
    assert factory.calls == process.resume_calls == 1
