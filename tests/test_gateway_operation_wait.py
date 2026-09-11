from __future__ import annotations

from threading import Condition, Event, current_thread, main_thread

import pytest

from harness.gateway_operation import GatewayOperationError
from harness.gateway_operation_wait import wait_for_terminal
from harness.gateway_operation_process import WorkerOutcome
from harness.gateway_operation_route import operation_ref_for, route_gateway_operation
from harness.journey_service import JourneyService
from harness.journey_lock import ExclusiveJourneyLock
from harness.journey_store import JourneyStore
from harness.operation_grants import GrantStore

from gateway_route_fixtures import JOURNEY, OWNER, Factory, Process, _setup


TERMINALS = frozenset(("completed", "failed", "cancelled"))


class Snapshot:
    def __init__(self, state):
        self.state = state


class ManualClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def monotonic(self):
        return self.now

    def advance(self, seconds):
        assert seconds >= 0
        self.now += seconds


class AdvancingCondition:
    def __init__(self, clock):
        self.clock = clock
        self.waits = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def wait(self, wait_s):
        self.waits.append(wait_s)
        self.clock.advance(wait_s)
        return True

    def notify_all(self):
        return None


class ReleaseLockOnWait:
    def __init__(self, release):
        self.release = release
        self._condition = Condition()
        self._released = False
        self.waits = 0
        self.wait_durations = []

    def __enter__(self):
        return self._condition.__enter__()

    def __exit__(self, *_exc):
        return self._condition.__exit__(*_exc)

    def wait(self, wait_s):
        self.waits += 1
        self.wait_durations.append(wait_s)
        if not self._released:
            self._released = True
            self.release()
        return self._condition.wait(wait_s)

    def notify_all(self):
        self._condition.notify_all()


class ControlledFactory(Factory):
    def __init__(self, process):
        super().__init__(process)
        self.entered = Event()
        self.release = Event()

    def create(self, authorized, progress):
        self.entered.set()
        assert self.release.wait(2.0), "worker factory was not released"
        return super().create(authorized, progress)


def test_non_stream_route_waits_through_transient_real_journey_lock(
        tmp_path, monkeypatch):
    authorize_calls = []
    service, raw = _setup(tmp_path, stream=False, lock_timeout_s=2.0,
                          authorize_calls=authorize_calls)
    process = Process(WorkerOutcome("completed", {"final": "done"}))
    factory = ControlledFactory(process)
    original_start = service.start
    original_journey = service._journey
    held_lock = None
    lock_path = (
        tmp_path / "journeys" / "v2" / "owners" / OWNER / JOURNEY / ".lock")

    def release_lock():
        nonlocal held_lock
        if held_lock is not None:
            held_lock.__exit__(None, None, None)
            held_lock = None

    condition = ReleaseLockOnWait(release_lock)

    def journey_with_short_main_thread_reads(owner_ref):
        if current_thread() is main_thread():
            return JourneyService(
                owner_ref=owner_ref,
                store=JourneyStore(service.state_root, lock_timeout_s=0.01),
                grants=GrantStore(service.state_root, clock=service.clock),
                clock=service.clock)
        return original_journey(owner_ref)

    def start_then_hold_lock(*args, **kwargs):
        nonlocal held_lock
        snapshot = original_start(*args, **kwargs)
        assert factory.entered.wait(2.0), "worker factory was not entered"
        held_lock = ExclusiveJourneyLock.acquire(lock_path)
        held_lock.__enter__()
        factory.release.set()
        return snapshot

    monkeypatch.setattr(service.events, "_condition", condition)
    monkeypatch.setattr(service, "_journey", journey_with_short_main_thread_reads)
    monkeypatch.setattr(service, "start", start_then_hold_lock)
    try:
        response = route_gateway_operation(
            "POST", "/api/agent", owner_ref=OWNER, raw=raw,
            content_type="application/json", service=service,
            process_factory=factory)
    finally:
        release_lock()
    ref = operation_ref_for(OWNER, JOURNEY, "agent-1")

    assert factory.calls == 1
    assert authorize_calls == ["agent.run"]
    assert response.status == 200
    assert response.body == {"final": "done"}
    assert condition.waits >= 1
    terminal = service.wait_terminal(OWNER, ref, 2)
    assert terminal.state == "completed"
    assert service.result(OWNER, ref)["result"] == {"final": "done"}


@pytest.mark.parametrize("state", ("completed", "failed", "cancelled"))
def test_wait_helper_returns_terminal_snapshots_without_waiting(state):
    clock = ManualClock()
    condition = AdvancingCondition(clock)
    snapshot = Snapshot(state)

    result = wait_for_terminal(
        lambda: snapshot, TERMINALS, condition, 30, clock=clock)

    assert result is snapshot
    assert condition.waits == []
    assert clock.now == 0.0


def test_wait_helper_expires_persistent_store_busy_as_typed_busy():
    clock = ManualClock()
    condition = AdvancingCondition(clock)
    calls = 0

    def read_snapshot():
        nonlocal calls
        calls += 1
        if calls > 5:
            pytest.fail("busy wait deadline was reset or not enforced")
        raise GatewayOperationError("STORE_BUSY")

    with pytest.raises(GatewayOperationError) as failure:
        wait_for_terminal(
            read_snapshot, TERMINALS, condition, 0.12, clock=clock)

    assert failure.value.code == "STORE_BUSY"
    assert calls >= 2
    assert condition.waits
    assert max(condition.waits) <= 0.05
    assert clock.now == pytest.approx(0.12)


def test_wait_helper_preserves_non_busy_gateway_error_without_waiting():
    clock = ManualClock()
    condition = AdvancingCondition(clock)
    calls = 0

    def read_snapshot():
        nonlocal calls
        calls += 1
        raise GatewayOperationError("STORE_COMMIT_FAILED")

    with pytest.raises(GatewayOperationError) as failure:
        wait_for_terminal(
            read_snapshot, TERMINALS, condition, 30, clock=clock)

    assert failure.value.code == "STORE_COMMIT_FAILED"
    assert calls == 1
    assert condition.waits == []
    assert clock.now == 0.0


def test_wait_helper_keeps_nonterminal_deadline_as_timeout_error():
    clock = ManualClock()
    condition = AdvancingCondition(clock)
    calls = 0

    def read_snapshot():
        nonlocal calls
        calls += 1
        if calls > 5:
            pytest.fail("nonterminal wait deadline was reset or not enforced")
        return Snapshot("running")

    with pytest.raises(TimeoutError, match="gateway operation did not become terminal"):
        wait_for_terminal(
            read_snapshot, TERMINALS, condition, 0.11, clock=clock)

    assert calls >= 2
    assert condition.waits
    assert max(condition.waits) <= 0.05
    assert clock.now == pytest.approx(0.11)
