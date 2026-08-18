import json
import threading
import pytest

from harness.evidence_json import canonical_bytes, canonical_sha256
import harness.gateway_operation_route as operation_route
from harness.gateway_operation_recovery import (
    LIFECYCLE, recover_gateway_operations, validate_history,
)
from harness.gateway_operation_route import OperationEventBus
from harness.gateway_operation_process import WorkerOutcome
from harness.gateway_operations import GatewayOperations, OperationSnapshot
from harness.journey_store import JourneyStore, MutationCommand


NOW = "2026-08-16T12:00:00Z"
OWNER = "owner_" + "a" * 32
JOURNEY = "jrn_" + "a" * 32
OPERATION = "op_" + "a" * 32


def _append(root, head, request, event_type, payload):
    return JourneyStore(root).append(MutationCommand(
        OWNER, JOURNEY, head, request, event_type,
        {"occurred_at": NOW, "payload": payload}))


def _queued(root, **changes):
    head = JourneyStore(root).create(MutationCommand(
        OWNER, JOURNEY, None, "genesis", "intake",
        {"legacy_label": None, "goal": "recover", "intake": {},
         "occurred_at": NOW})).event_head_sha256
    payload = {
        "operation_ref": OPERATION, "client_request_id": "agent-1",
        "action": "agent.run", "tool": "agent.run",
        "authorization_sha256": "a" * 64, "operation_sha256": "b" * 64,
        "arguments_sha256": "c" * 64, "grant_ref_sha256": "d" * 64,
        "execution_plan_sha256": "e" * 64,
    }
    payload.update(changes)
    return _append(root, head, "queue", "operation_queued", payload)


def _started(root, queued):
    return _append(root, queued.event_head_sha256, "start", "operation_started", {
        "operation_ref": OPERATION, "queued_event_sha256": queued.event_sha256,
        "control_class": "windows_job_v1"})


def _events(root):
    directory = root / "journeys" / "v2" / "owners" / OWNER / JOURNEY / "events"
    return [json.loads(path.read_bytes()) for path in sorted(directory.glob("*.json"))]


def test_recovery_closes_exact_queued_running_and_cancel_requested(tmp_path):
    for state in ("queued", "running", "cancel_requested"):
        root = tmp_path / state
        queued = _queued(root)
        head, basis = queued.event_head_sha256, queued.event_sha256
        if state != "queued":
            started = _append(root, head, "start", "operation_started", {
                "operation_ref": OPERATION,
                "queued_event_sha256": queued.event_sha256,
                "control_class": "windows_job_v1"})
            head, basis = started.event_head_sha256, started.event_sha256
        if state == "cancel_requested":
            cancel = _append(root, head, "cancel", "cancel_requested", {
                "operation_ref": OPERATION,
                "started_event_sha256": basis,
                "client_request_id": "stop-1",
                "authorization_sha256": "f" * 64, "timeout_ms": 5000})
            basis = cancel.event_sha256

        result = recover_gateway_operations(root, now=NOW)

        terminals = [event for event in _events(root)
                     if event["event_type"] == "operation_failed"]
        assert result["closed"] == 1 and result["ambiguous"] == 0
        assert len(terminals) == 1
        assert terminals[0]["payload"]["reason"] == "OPERATION_INTERRUPTED"
        assert terminals[0]["payload"]["basis_event_sha256"] == basis


def test_recovery_diagnoses_ambiguous_grammar_without_terminal(tmp_path):
    queued = _queued(tmp_path)
    _append(tmp_path, queued.event_head_sha256, "duplicate", "operation_queued",
            queued_payload := queued_event_payload(tmp_path))

    result = recover_gateway_operations(tmp_path, now=NOW)

    assert result["closed"] == 0 and result["ambiguous"] == 1
    assert result["diagnostic_refs"]
    assert not any(event["event_type"].startswith("operation_") and
                   event["event_type"] in {"operation_failed",
                                            "operation_completed",
                                            "operation_cancelled"}
                   for event in _events(tmp_path))


def test_recovery_diagnoses_invalid_operation_identity_without_closure(tmp_path):
    for name, changes in {
        "ref": {"operation_ref": "op_bad"},
        "action": {"action": "plugin.call"},
        "request": {"client_request_id": "../unsafe"},
    }.items():
        root = tmp_path / name
        _queued(root, **changes)

        result = recover_gateway_operations(root, now=NOW)

        assert result["closed"] == 0 and result["ambiguous"] == 1
        assert not any(event["event_type"] in {
            "operation_failed", "operation_completed", "operation_cancelled"}
            for event in _events(root))


def test_review_w9_missing_queue_is_diagnosed_without_phase_one_mutation(
        tmp_path):
    head = JourneyStore(tmp_path).create(MutationCommand(
        OWNER, JOURNEY, None, "genesis", "intake",
        {"legacy_label": None, "goal": "check", "intake": {},
         "occurred_at": NOW})).event_head_sha256
    _append(tmp_path, head, "check-cancel", "cancel_requested", {
        "operation_ref": OPERATION, "started_event_sha256": "a" * 64,
        "timeout_s": 1.0})

    result = recover_gateway_operations(tmp_path, now=NOW)

    assert result["closed"] == 0 and result["ambiguous"] == 1
    assert len(result["diagnostic_refs"]) == 1
    assert not any(event["event_type"].startswith("operation_")
                   for event in _events(tmp_path))


def queued_event_payload(root):
    return next(event["payload"] for event in _events(root)
                if event["event_type"] == "operation_queued")


def test_recovery_leaves_existing_terminal_and_detects_result_tamper(tmp_path):
    queued = _queued(tmp_path)
    started = _started(tmp_path, queued)
    wrong = {
        "schema": "wrong", "operation_ref": OPERATION,
        "action": "agent.run", "state": "completed", "result": {"ok": True}}
    digest = canonical_sha256(wrong)
    result_dir = (tmp_path / "gateway-operations" / "v1" / "owners" /
                  OWNER / "results")
    result_dir.mkdir(parents=True)
    result_path = result_dir / f"{digest}.json"
    result_path.write_bytes(canonical_bytes(wrong))
    terminal = _append(tmp_path, started.event_head_sha256, "terminal",
                       "operation_completed", {
        "operation_ref": OPERATION,
        "basis_event_sha256": started.event_sha256,
        "result_sha256": digest})

    result = recover_gateway_operations(tmp_path, now=NOW)

    assert terminal.event_sha256 in {
        event["event_sha256"] for event in _events(tmp_path)}
    assert result["closed"] == 0 and result["ambiguous"] == 1


def _completed(root, result=None):
    queued = _queued(root)
    started = _started(root, queued)
    service = GatewayOperations(root, clock=lambda: NOW)
    result = result or {"final": "answer"}
    digest = service._seal(OWNER, OPERATION, "agent.run", "completed", result)
    _append(root, started.event_head_sha256, "terminal", "operation_completed", {
        "operation_ref": OPERATION, "basis_event_sha256": started.event_sha256,
        "result_sha256": digest})
    return service, service.snapshot(OWNER, OPERATION), digest


def test_review_w4_terminal_replay_revalidates_durable_result(tmp_path):
    service, snapshot, digest = _completed(tmp_path)
    cached = service.result(OWNER, OPERATION)
    bus = OperationEventBus()
    bus.publish(OWNER, OPERATION, "terminal", {
        "snapshot": snapshot.as_json(), "result": cached})
    (service._result_dir(OWNER) / f"{digest}.json").unlink()

    stream = bus.watch(service, OWNER, OPERATION, 0)
    with pytest.raises(Exception) as failure:
        next(stream)
    assert getattr(failure.value, "code", None) == "STORE_COMMIT_FAILED"
    assert bus._subscribers == {}


def test_review_w4_terminal_row_refetches_snapshot_after_publish():
    entered, release, rows = threading.Event(), threading.Event(), []
    running = OperationSnapshot(
        OPERATION, JOURNEY, "a" * 64, "running", True)
    terminal = OperationSnapshot(
        OPERATION, JOURNEY, "b" * 64, "completed", False,
        "c" * 64, "d" * 64)

    class Service:
        terminal_states = {"completed", "failed", "cancelled"}
        calls = 0
        def snapshot(self, _owner, _ref):
            self.calls += 1
            if self.calls == 1:
                entered.set(); assert release.wait(1)
                return running
            return terminal
        def result(self, _owner, _ref):
            return {"state": "completed"}

    bus, stream = OperationEventBus(), None
    service = Service()
    stream = bus.watch(service, OWNER, OPERATION, 0)
    thread = threading.Thread(target=lambda: rows.append(next(stream)))
    thread.start(); assert entered.wait(1)
    bus.publish(OWNER, OPERATION, "terminal", {"durable": True})
    release.set(); thread.join(1)
    try:
        assert not thread.is_alive()
        assert rows[0]["data"]["snapshot"]["state"] == "completed"
    finally:
        stream.close()


def test_review_w3_publish_retry_replays_exact_terminal_digest(tmp_path):
    queued = _queued(tmp_path)
    _started(tmp_path, queued)
    service = GatewayOperations(tmp_path, clock=lambda: NOW)
    original, seals = service._seal, []

    def seal(*args):
        seals.append((args[3], args[4]))
        return original(*args)

    service._seal = seal
    service._publish = lambda *_args: (_ for _ in ()).throw(OSError("publish"))
    outcome = WorkerOutcome("completed", {"final": "answer"})
    with pytest.raises(OSError, match="publish"):
        service._terminal(OWNER, OPERATION, outcome)
    committed = service.snapshot(OWNER, OPERATION)
    replay = service._terminal(OWNER, OPERATION, outcome)
    terminals = [event for event in _events(tmp_path)
                 if event["event_type"] == "operation_completed"]
    assert replay == committed and len(terminals) == 1
    assert seals == [("completed", {"final": "answer"})]


def test_review_w7_result_and_buffer_always_leave_terminal_representable(
        monkeypatch, tmp_path):
    service = GatewayOperations(tmp_path, clock=lambda: NOW)
    with pytest.raises(Exception) as oversized:
        service._seal(OWNER, OPERATION, "agent.run", "completed",
                      {"final": "x" * 300_000})
    assert getattr(oversized.value, "code", None) == "STORE_COMMIT_FAILED"

    monkeypatch.setattr(operation_route, "_MAX_BUFFER_BYTES", 300)
    monkeypatch.setattr(operation_route, "_MAX_GATEWAY_BUFFER_BYTES", 300)
    bus = OperationEventBus()
    for index in range(20):
        try:
            bus.publish(OWNER, "op_" + "b" * 32,
                        "progress", {"step": index})
        except Exception:
            break
    bus.publish(OWNER, OPERATION, "terminal", {"durable": True})
    assert (OWNER, OPERATION) not in bus._rows
    terminal = {"snapshot": {"result_sha256": "a" * 64},
                "result": {"result": {"final": "x" * 249_000}}}
    assert operation_route._frame(1, "terminal", terminal)


def test_review_w8_terminal_type_is_bound_to_lifecycle_basis(tmp_path):
    queued = _queued(tmp_path)
    _append(tmp_path, queued.event_head_sha256, "terminal",
            "operation_completed", {
                "operation_ref": OPERATION,
                "basis_event_sha256": queued.event_sha256,
                "result_sha256": "f" * 64})
    history = [event for event in _events(tmp_path)
               if event["event_type"] in LIFECYCLE]
    with pytest.raises(ValueError, match="ambiguous"):
        validate_history(history, OPERATION)


def test_review_w15_completed_event_rows_obey_gateway_wide_cap(
        monkeypatch):
    monkeypatch.setattr(operation_route, "_MAX_GATEWAY_BUFFER_BYTES", 400,
                        raising=False)
    bus = OperationEventBus()
    for index in range(10):
        bus.publish(OWNER, f"op_{index:032x}", "terminal", {"done": index})
    assert sum(bus._bytes.values()) <= 400
    assert bus._rows == {}
