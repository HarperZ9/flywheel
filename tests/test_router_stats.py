"""test_router_stats.py — cost/quality-aware routing is correct and persisted.

Success criteria:
  - record updates the table; a success resets the failure streak.
  - score prefers higher success rate and cheaper cost; unseen gets an optimistic prior.
  - the circuit breaker opens after N consecutive failures and closes on a success.
  - order() puts the best provider first and circuit-open ones last.
  - stats persist across instances (JSON round-trip).
"""
import multiprocessing
import os
from pathlib import Path
import queue
import threading
import time

import pytest

import harness.router_stats as router_stats
from harness.router_stats import RouterStats


def _assert_no_stats_temp_leftovers(directory):
    assert not (directory / "stats.tmp").exists()
    assert list(directory.glob(".*.tmp")) == []


def _record_many(path_text, endpoint, count, result_queue):
    try:
        stats = RouterStats(Path(path_text))
        for _ in range(count):
            stats.record(endpoint, True, 0.001)
    except BaseException as exc:
        result_queue.put((endpoint, type(exc).__name__, str(exc)))
    else:
        result_queue.put((endpoint, "ok", ""))


def _hold_windows_reader_without_delete_share(path, release, opened):
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = (
        ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
        ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
    )
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    handle = kernel32.CreateFileW(str(path), 0x80000000, 0x00000001, None, 3,
                                  0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        opened.set()
        release.wait(5)
    finally:
        kernel32.CloseHandle(handle)


def _start_windows_reader_without_delete_share(path):
    release = threading.Event()
    opened = threading.Event()
    errors = []

    def run():
        try:
            _hold_windows_reader_without_delete_share(path, release, opened)
        except BaseException as exc:
            errors.append(exc)
            opened.set()

    thread = threading.Thread(target=run)
    thread.start()
    assert opened.wait(2)
    if errors:
        raise errors[0]
    return release, thread


def test_record_and_success_rate():
    rs = RouterStats()
    rs.record("a", True, latency=0.5)
    rs.record("a", False, latency=1.5)
    s = rs.stats["a"]
    assert s.attempts == 2 and s.successes == 1 and s.failures == 1
    assert s.success_rate == 0.5 and s.mean_latency == 1.0


def test_success_resets_failure_streak():
    rs = RouterStats(circuit_threshold=3)
    for _ in range(2):
        rs.record("a", False)
    assert rs.stats["a"].consecutive_failures == 2
    rs.record("a", True)
    assert rs.stats["a"].consecutive_failures == 0


def test_unseen_provider_is_optimistic_and_cost_matters():
    rs = RouterStats(cost={"cheap": 1.0, "pricey": 2.0})
    assert rs.score("never-seen") == 1.0                 # optimistic prior at cost 1
    # equal outcomes, cheaper wins
    for _ in range(5):
        rs.record("cheap", True)
        rs.record("pricey", True)
    assert rs.score("cheap") > rs.score("pricey")


def test_score_prefers_higher_success_rate():
    rs = RouterStats()
    for _ in range(10):
        rs.record("good", True)
    for _ in range(10):
        rs.record("bad", False)
    assert rs.score("good") > rs.score("bad")


def test_circuit_breaker_opens_and_closes():
    rs = RouterStats(circuit_threshold=3)
    assert not rs.is_circuit_open("a")
    for _ in range(3):
        rs.record("a", False)
    assert rs.is_circuit_open("a")
    rs.record("a", True)
    assert not rs.is_circuit_open("a")


def test_order_best_first_and_tripped_last():
    rs = RouterStats(circuit_threshold=3)
    for _ in range(10):
        rs.record("b", True)
    for _ in range(10):
        rs.record("c", True)
    for _ in range(2):
        rs.record("c", False)          # c degraded but stays below the circuit threshold
    for _ in range(3):
        rs.record("a", False)          # a circuit-open
    order = rs.order(["a", "b", "c"])
    assert order == ["b", "c", "a"]    # best first, degraded next, circuit-open last


def test_stats_persist_across_instances(tmp_path):
    p = tmp_path / "router_stats.json"
    rs = RouterStats(p)
    rs.record("a", True)
    rs.record("a", False)
    reloaded = RouterStats(p)
    assert reloaded.stats["a"].attempts == 2
    assert reloaded.snapshot()["providers"]["a"]["success_rate"] == 0.5


def test_private_temp_files_are_unique_and_cleaned_up(tmp_path, monkeypatch):
    """Reusing one temp path would let one writer move another writer's file."""
    p = tmp_path / "stats.json"
    sources = []
    real_replace = router_stats.os.replace

    def capture_source(source, target):
        if Path(target) == p:
            sources.append(Path(source).name)
        return real_replace(source, target)

    monkeypatch.setattr(router_stats.os, "replace", capture_source)
    RouterStats(p).record("a", True)
    RouterStats(p).record("b", True)

    assert len(sources) == 2
    assert len(set(sources)) == 2
    assert all(name.startswith(".stats.json.") and name.endswith(".tmp")
               for name in sources)
    assert "stats.tmp" not in sources
    reloaded = RouterStats(p)
    assert reloaded.stats["a"].attempts == 1
    assert reloaded.stats["b"].attempts == 1
    _assert_no_stats_temp_leftovers(tmp_path)


@pytest.mark.skipif(os.name != "nt", reason="Windows open-handle semantics")
def test_held_windows_reader_contention_is_typed_and_bounded(tmp_path):
    """A reader denying delete-share must not leak host PermissionError detail."""
    p = tmp_path / "stats.json"
    RouterStats(p).record("seed", True)
    release, thread = _start_windows_reader_without_delete_share(p)
    started = time.monotonic()
    try:
        with pytest.raises(router_stats.RouterStatsError) as failure:
            RouterStats(p, lock_timeout_s=0.05).record("blocked", True)
    finally:
        release.set()
        thread.join(2)
    assert failure.value.code == str(failure.value) == "STORE_BUSY"
    assert time.monotonic() - started < 1.0
    assert "blocked" not in RouterStats(p).stats
    _assert_no_stats_temp_leftovers(tmp_path)


@pytest.mark.skipif(os.name != "nt", reason="Windows open-handle semantics")
def test_released_windows_reader_allows_record_without_unnecessary_failure(tmp_path):
    """A bounded transient reader must be retried instead of failing immediately."""
    p = tmp_path / "stats.json"
    RouterStats(p).record("seed", True)
    release, thread = _start_windows_reader_without_delete_share(p)
    timer = threading.Timer(0.05, release.set)
    timer.start()
    try:
        RouterStats(p, lock_timeout_s=1.0).record("after", True)
    finally:
        release.set()
        timer.cancel()
        thread.join(2)
    reloaded = RouterStats(p)
    assert reloaded.stats["seed"].attempts == 1
    assert reloaded.stats["after"].attempts == 1
    _assert_no_stats_temp_leftovers(tmp_path)


@pytest.mark.skipif(os.name != "nt", reason="Windows multiprocess regression")
def test_windows_multiprocess_writers_converge_without_leftover_temps(tmp_path):
    """Separate processes must serialize updates and leave no private temp files."""
    p = tmp_path / "stats.json"
    ctx = multiprocessing.get_context("spawn")
    result_queue = ctx.Queue()
    writers, count = 4, 25
    processes = [
        ctx.Process(target=_record_many, args=(str(p), f"p{i}", count, result_queue))
        for i in range(writers)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(20)
    for process in processes:
        if process.is_alive():
            process.terminate()
            process.join(2)
    assert [process.exitcode for process in processes] == [0] * writers
    results = sorted(result_queue.get(timeout=2) for _ in range(writers))
    assert results == [(f"p{i}", "ok", "") for i in range(writers)]
    reloaded = RouterStats(p)
    assert sum(s.attempts for s in reloaded.stats.values()) == writers * count
    for i in range(writers):
        assert reloaded.stats[f"p{i}"].attempts == count
    with pytest.raises(queue.Empty):
        result_queue.get_nowait()
    _assert_no_stats_temp_leftovers(tmp_path)


def test_lock_contention_has_a_fixed_retryable_failure(tmp_path, monkeypatch):
    """A busy cross-process stats writer must surface STORE_BUSY without host detail."""
    def busy(*_args, **_kwargs):
        raise router_stats.JourneyLockBusy()

    monkeypatch.setattr(router_stats.ExclusiveJourneyLock, "acquire", busy)
    with pytest.raises(router_stats.RouterStatsError) as failure:
        RouterStats(tmp_path / "stats.json").record("a", True)
    assert failure.value.code == str(failure.value) == "STORE_BUSY"


def test_persistence_is_atomic_and_thread_safe(tmp_path):
    import threading
    from harness.router_stats import RouterStats
    rs = RouterStats(path=tmp_path / "stats.json")
    def hammer(name):
        for _ in range(50):
            rs.record(name, True, 0.01)
    threads = [threading.Thread(target=hammer, args=(f"p{i%4}",)) for i in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()
    # the file is always valid JSON (atomic replace, never a torn write)
    import json
    reloaded = RouterStats(path=tmp_path / "stats.json")
    assert sum(s.attempts for s in reloaded.stats.values()) == 400
    # no stray temp file left behind
    assert not (tmp_path / "stats.json.tmp").exists()


def test_corrupt_stats_file_is_quarantined_not_fatal(tmp_path):
    from harness.router_stats import RouterStats
    p = tmp_path / "stats.json"
    p.write_text("{ this is not valid json", encoding="utf-8")
    rs = RouterStats(path=p)        # must not raise
    assert rs.stats == {}
    assert p.with_suffix(".corrupt").exists()


def test_one_success_does_not_outrank_a_proven_provider():
    from harness.router_stats import RouterStats
    rs = RouterStats()
    # a provider with a single minted success
    rs.record("fresh", True)
    # a provider proven over 1000 attempts at 99.9%
    for _ in range(999):
        rs.record("proven", True)
    rs.record("proven", False)
    # the proven provider must not be outranked by one lucky/minted success:
    # the score uses a lower confidence bound, so thin evidence cannot leap
    # ahead of a long track record
    assert rs.score("proven") > rs.score("fresh"), (
        rs.score("proven"), rs.score("fresh"))
    # an entirely unseen provider still gets an optimistic prior (exploration)
    assert rs.score("unseen") >= rs.score("proven") * 0.5
