"""Controls for the concurrency fixture's clock scope and timeout evidence."""
from concurrent.futures import Future
import json
import threading
import time
from types import SimpleNamespace

import pytest

import harness.journey_lock as locks


def test_controlled_clock_ends_before_held_work_and_nested_acquisitions(tmp_path, monkeypatch):
    from continuation_contention_probe import AcquisitionClock

    outer, inner = tmp_path / "outer.lock", tmp_path / "inner.lock"
    clock = AcquisitionClock()
    real_acquire, real_try = locks.ExclusiveJourneyLock.acquire, locks._try_lock
    observations = []

    def observe(stream):
        observations.append((stream.name, clock.monotonic()))
        return real_try(stream)

    monkeypatch.setattr(locks, "_try_lock", observe)
    before = time.monotonic()
    with clock.acquire(real_acquire, outer, outer_path=outer):
        assert clock.monotonic() >= before
        with clock.acquire(real_acquire, inner, outer_path=outer):
            assert clock.monotonic() >= before
    assert observations[0] == (str(outer), 0.0)
    assert observations[1][0] == str(inner) and observations[1][1] >= before
    assert clock.monotonic() >= before


def test_controlled_clock_is_restored_when_acquisition_raises(tmp_path):
    from contextlib import contextmanager
    from continuation_contention_probe import AcquisitionClock

    clock = AcquisitionClock()

    @contextmanager
    def refused(_path, _timeout):
        assert clock.monotonic() == 0.0
        clock.expire()
        assert clock.monotonic() == 3.0
        raise locks.JourneyLockBusy()
        yield  # pragma: no cover

    before = time.monotonic()
    with pytest.raises(locks.JourneyLockBusy):
        with clock.acquire(refused, tmp_path, outer_path=tmp_path):
            pytest.fail("a refused acquisition cannot enter held work")
    assert clock.monotonic() >= before


def test_nested_busy_lock_keeps_real_deadline_while_outer_guard_is_held(tmp_path, monkeypatch):
    from continuation_contention_probe import AcquisitionClock

    outer, inner = tmp_path / "outer.lock", tmp_path / "inner.lock"
    clock = AcquisitionClock()
    real_acquire, real_try = locks.ExclusiveJourneyLock.acquire, locks._try_lock
    entered, release = threading.Event(), threading.Event()
    attempts = []

    def owner():
        with real_acquire(inner):
            entered.set()
            assert release.wait(10)

    thread = threading.Thread(target=owner)
    thread.start()
    try:
        assert entered.wait(10)
        before = time.monotonic()

        def observe(stream):
            acquired = real_try(stream)
            if stream.name == str(inner) and not acquired:
                attempts.append(clock.monotonic())
                assert attempts[-1] >= before, "nested lock inherited frozen outer time"
            return acquired

        monkeypatch.setattr(locks, "_try_lock", observe)
        monkeypatch.setattr(locks, "time", SimpleNamespace(
            monotonic=clock.monotonic, sleep=time.sleep))
        with clock.acquire(real_acquire, outer, outer_path=outer):
            with pytest.raises(locks.JourneyLockBusy):
                with clock.acquire(real_acquire, inner, .025, outer_path=outer):
                    pytest.fail("held inner lock was acquired")
        assert attempts and time.monotonic() - before >= .025
    finally:
        release.set()
        thread.join(timeout=10)
    assert not thread.is_alive()


def test_watchdog_failure_reports_actual_pending_phase_and_stack(capsys):
    from continuation_contention_probe import ContentionProbe, collect_results

    probe = ContentionProbe()
    probe.record("create.running", caller=3)
    completed, pending = Future(), Future()
    completed.set_result(({}, 200))
    with pytest.raises(AssertionError, match="continuation contention timed out") as failure:
        collect_results([completed, pending], timeout=0, probe=probe)
    assert capsys.readouterr().err.strip() == str(failure.value)
    report = json.loads(str(failure.value).split(": ", 1)[1])
    assert report["completed"] == 1 and report["total"] == 2
    assert report["events"][-1]["phase"] == "create.running"
    assert report["threads"][0]["caller"] == 3
    assert any("test_watchdog_failure_reports_actual_pending_phase_and_stack" in frame
               for frame in report["threads"][0]["stack"])


@pytest.mark.parametrize("error", [ValueError, TimeoutError])
def test_worker_error_is_not_relabelled(error):
    from continuation_contention_probe import ContentionProbe, collect_results

    failed = Future()
    failed.set_exception(error("synthetic worker failure"))
    with pytest.raises(error, match="synthetic worker failure"):
        collect_results([failed], timeout=0, probe=ContentionProbe())
