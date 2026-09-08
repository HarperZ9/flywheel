from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

import harness.gateway_operation_route as operation_route
from harness.gateway_operation import GatewayOperationError
from harness.gateway_operation_process import WorkerOutcome
from harness.gateway_operation_route import (
    OperationEventBus, operation_ref_for, route_gateway_operation)
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
    process = BlockingProcess()
    response = route_gateway_operation(
        "POST", "/api/agent", owner_ref=OWNER, raw=raw,
        content_type="application/json", service=service,
        process_factory=Factory(process))
    ref = operation_ref_for(OWNER, JOURNEY, "agent-1")
    busy_seen = Event()
    original_snapshot = service.snapshot

    def snapshot(*args):
        try:
            return original_snapshot(*args)
        except GatewayOperationError as exc:
            if exc.code == "STORE_BUSY":
                busy_seen.set()
            raise

    def read_first_frame():
        stream_response = route_gateway_operation(
            "GET", f"/api/operations/{ref}/events", query="after=999",
            owner_ref=OWNER, service=service, process_factory=Factory(process))
        assert stream_response.status == 200
        return next(stream_response.stream)

    monkeypatch.setattr(service, "snapshot", snapshot)
    lock_path = tmp_path / "journeys" / "v2" / "owners" / OWNER / JOURNEY / ".lock"
    executor = ThreadPoolExecutor(max_workers=1)
    future = None
    try:
        with ExclusiveJourneyLock.acquire(lock_path):
            future = executor.submit(read_first_frame)
            assert busy_seen.wait(1)
            assert not future.done()
        service.events.wake()
        assert b"event: snapshot\r\n" in future.result(timeout=1)
    finally:
        process.release.set()
        executor.shutdown(wait=True)
        if response.stream is not None:
            response.stream.close()


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
