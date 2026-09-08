from threading import Event

import pytest

import harness.gateway_operation_route as operation_route
from harness.gateway_operation import GatewayOperationError
from harness.gateway_operation_process import WorkerOutcome
from harness.gateway_operation_route import (
    OperationEventBus, operation_ref_for, queued_payload,
    route_gateway_operation)
from harness.gateway_operation_route_reads import read_after_store_busy
from harness.journey_lock import ExclusiveJourneyLock
from gateway_route_fixtures import JOURNEY, OWNER, Factory, _setup


class Snapshot:
    def __init__(self, state):
        self.state = state

    def as_json(self):
        return {"state": self.state}


class BusySnapshotService:
    terminal_states = frozenset()

    def __init__(self):
        self.events = OperationEventBus()

    def snapshot(self, *_args):
        raise GatewayOperationError("STORE_BUSY")

    def watch(self, *args):
        return self.events.watch(self, *args)


class FlakyService(BusySnapshotService):
    terminal_states = frozenset({"completed"})

    def __init__(self, *, snapshot_code="STORE_BUSY", result_code=None):
        super().__init__()
        self.snapshot_code = snapshot_code
        self.result_code = result_code
        self.snapshot_calls = 0
        self.result_calls = 0

    def snapshot(self, *_args):
        self.snapshot_calls += 1
        if self.snapshot_calls == 1 and self.snapshot_code:
            raise GatewayOperationError(self.snapshot_code)
        return Snapshot("completed" if self.result_code else "running")

    def result(self, *_args):
        self.result_calls += 1
        if self.result_calls == 1 and self.result_code:
            raise GatewayOperationError(self.result_code)
        return {"result": {"final": "answer"}}


class TerminalAfterFirstSnapshot:
    terminal_states = frozenset({"completed"})

    def __init__(self, ref):
        self.events = OperationEventBus()
        self.ref = ref
        self.snapshot_calls = 0

    def snapshot(self, *_args):
        self.snapshot_calls += 1
        if self.snapshot_calls == 1:
            self.events.publish(OWNER, self.ref, "terminal", {})
            return Snapshot("running")
        return Snapshot("completed")

    def result(self, *_args):
        return {"result": {"final": "answer"}}

    def watch(self, *args):
        return self.events.watch(self, *args)


class BlockingProcess:
    control_class = "windows_job_v1"

    def __init__(self):
        self.release = Event()

    def resume(self):
        return True

    def signal_tree(self):
        self.release.set()
        return True

    def wait(self, timeout):
        if not self.release.wait(min(float(timeout), 0.05)):
            return None
        return WorkerOutcome("completed", {"final": "done"})

    def close(self):
        self.release.set()


class ReleaseLockOnWait:
    def __init__(self, release):
        self.release = release
        self.waits = 0

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def wait(self, _wait_s):
        self.waits += 1
        self.release()
        return True

    def notify_all(self):
        return None

def _queue_operation(service, raw):
    authorized = service.authorizer(
        "agent.run", raw, owner_ref=OWNER, state_root=service.state_root,
        clock=service.clock)
    journey = service._journey(OWNER)
    head = journey.resume(JOURNEY)["event_head_sha256"]
    journey._append_lifecycle(
        journey_ref=JOURNEY, expected_event_head=head,
        client_request_id=authorized.client_request_id,
        operation="operation_queued", payload=queued_payload(authorized))
    return operation_ref_for(OWNER, JOURNEY, authorized.client_request_id)

def test_watch_yields_buffered_progress_when_snapshot_is_busy():
    service, ref = BusySnapshotService(), "op_" + "1" * 32
    service.events.publish(OWNER, ref, "progress", {"step": "ready"})
    watcher = service.events.watch(service, OWNER, ref, 0)
    try:
        assert next(watcher) == {
            "sequence": 1, "event": "progress", "data": {"step": "ready"}}
    finally:
        watcher.close()


def test_watch_still_surfaces_busy_without_buffered_events():
    service, ref = BusySnapshotService(), "op_" + "2" * 32
    with pytest.raises(GatewayOperationError) as failure:
        next(service.events.watch(service, OWNER, ref, 0))
    assert failure.value.code == "STORE_BUSY"


def test_watch_waits_for_real_journey_lock_release_before_retry(tmp_path, monkeypatch):
    service, raw = _setup(tmp_path, lock_timeout_s=0.01)
    ref = _queue_operation(service, raw)
    lock_path = tmp_path / "journeys" / "v2" / "owners" / OWNER / JOURNEY / ".lock"
    original_history = service._history
    held_lock = None
    locked_once = False

    def release_lock():
        nonlocal held_lock
        if held_lock is not None:
            held_lock.__exit__(None, None, None)
            held_lock = None

    def history_then_lock(*args):
        nonlocal held_lock, locked_once
        history = original_history(*args)
        if not locked_once:
            locked_once = True
            held_lock = ExclusiveJourneyLock.acquire(lock_path)
            held_lock.__enter__()
        return history

    condition = ReleaseLockOnWait(release_lock)
    monkeypatch.setattr(service, "_history", history_then_lock)
    monkeypatch.setattr(service.events, "_condition", condition)
    stream = None
    try:
        response = route_gateway_operation(
            "GET", f"/api/operations/{ref}/events", query="after=999",
            owner_ref=OWNER, service=service,
            process_factory=Factory(BlockingProcess()))
        assert response.status == 200 and response.stream is not None
        stream = response.stream
        assert b"event: snapshot\r\n" in next(stream)
        assert locked_once and condition.waits == 1
    finally:
        release_lock()
        if stream is not None:
            stream.close()


def test_snapshot_load_busy_after_history_read_retries_through_route_reader(tmp_path, monkeypatch):
    service, raw = _setup(tmp_path, lock_timeout_s=0.01)
    ref = _queue_operation(service, raw)
    lock_path = tmp_path / "journeys" / "v2" / "owners" / OWNER / JOURNEY / ".lock"
    original_history = service._history
    held_lock = None
    locked_once = False

    def release_lock():
        nonlocal held_lock
        if held_lock is not None:
            held_lock.__exit__(None, None, None)
            held_lock = None
            service.events.wake()

    def history_then_lock(*args):
        nonlocal held_lock, locked_once
        history = original_history(*args)
        if not locked_once:
            locked_once = True
            held_lock = ExclusiveJourneyLock.acquire(lock_path)
            held_lock.__enter__()
        return history

    condition = ReleaseLockOnWait(release_lock)
    monkeypatch.setattr(service, "_history", history_then_lock)
    try:
        snapshot = read_after_store_busy(
            lambda: service.snapshot(OWNER, ref), condition)
        assert snapshot.operation_ref == ref
        assert locked_once and condition.waits == 1
    finally:
        release_lock()


def test_snapshot_load_nonbusy_after_history_read_does_not_retry(tmp_path, monkeypatch):
    service, raw = _setup(tmp_path, lock_timeout_s=0.01)
    ref = _queue_operation(service, raw)
    original_history = service._history
    corrupted_once = False

    def history_then_corrupt(*args):
        nonlocal corrupted_once
        history = original_history(*args)
        if not corrupted_once:
            corrupted_once = True
            projection_path = (
                tmp_path / "journeys" / "v2" / "owners" / OWNER
                / JOURNEY / "projection.json")
            projection_path.write_bytes(b'{"wrong":true}')
        return history

    condition = ReleaseLockOnWait(lambda: None)
    monkeypatch.setattr(service, "_history", history_then_corrupt)
    with pytest.raises(GatewayOperationError) as failure:
        read_after_store_busy(lambda: service.snapshot(OWNER, ref), condition)
    assert failure.value.code == "STORE_COMMIT_FAILED"
    assert corrupted_once and condition.waits == 0


def test_watch_retries_transient_busy_before_synthetic_snapshot():
    service, ref = FlakyService(), "op_" + "3" * 32
    row = next(service.events.watch(service, OWNER, ref, 0))
    assert row["event"] == "snapshot" and service.snapshot_calls == 2


def test_terminal_row_refreshes_snapshot_after_terminal_publish_interleaving():
    ref = "op_" + "4" * 32
    service = TerminalAfterFirstSnapshot(ref)
    row = next(service.events.watch(service, OWNER, ref, 0))
    assert row["event"] == "terminal"
    assert row["data"]["snapshot"]["state"] == "completed"
    assert service.snapshot_calls == 2


def test_stream_retries_transient_busy_while_hydrating_terminal_and_done():
    service = FlakyService(snapshot_code=None, result_code="STORE_BUSY")
    ref = "op_" + "5" * 32
    service.events.publish(OWNER, ref, "terminal", {"ignored": True})
    wire = b"".join(operation_route._stream(service, OWNER, ref, after=0))
    assert b"event: terminal\r\n" in wire
    assert wire.endswith(b"data: [DONE]\r\n\r\n")
    assert service.result_calls == 2


def test_stream_surfaces_permanent_busy_before_terminal_done():
    service, ref = BusySnapshotService(), "op_" + "6" * 32
    service.terminal_states = frozenset({"completed"})
    with service.events._condition:
        service.events._subscribers[(OWNER, ref)] = 1
    service.events.publish(OWNER, ref, "terminal", {"ignored": True})
    with pytest.raises(GatewayOperationError) as failure:
        b"".join(operation_route._stream(service, OWNER, ref, after=0))
    assert failure.value.code == "STORE_BUSY"


def test_watch_surfaces_non_busy_snapshot_failure():
    service, ref = FlakyService(snapshot_code="NOT_FOUND"), "op_" + "7" * 32
    with pytest.raises(GatewayOperationError) as failure:
        next(service.events.watch(service, OWNER, ref, 0))
    assert failure.value.code == "NOT_FOUND"
