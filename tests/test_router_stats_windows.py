"""test_router_stats_windows.py -- the stats store under Windows file semantics.

Split out of `test_router_stats.py`, which covers the routing arithmetic and
the JSON round-trip on every platform. What lives here needs an open handle
that denies delete-share, or several real processes writing at once. Both are
Windows-specific enough that they carried their own ctypes helpers and skip
markers through a file that otherwise has neither.

Success criteria:
  - a reader holding the file without delete-share yields STORE_BUSY, bounded,
    and leaks no host PermissionError detail to the caller.
  - a reader that lets go is retried rather than failed on immediately.
  - separate processes serialize their updates and leave no private temp file.
"""
import multiprocessing, os, queue, threading, time
from pathlib import Path

import pytest

import harness.router_stats as router_stats
from harness.router_stats import RouterStats
from tests.test_router_stats import _assert_no_stats_temp_leftovers


#: How long one writer waits for the file lock before giving up.
#:
#: Measured on an idle Windows box at four writers, this test's count: the
#: worst single acquisition was 1.3s, and 3.3s at twelve writers. The cost is
#: what the lock is held for, a reload plus a JSON write plus an fsync per
#: record, so the wait tracks writer count and disk speed. It is not lock
#: unfairness. Replacing the flat 10ms poll with a spread-out backoff made the
#: worst wait slightly longer across three paired runs at twelve writers.
#:
#: CI runs four pytest shards at once on a two-core Windows runner, where
#: every hold is slower than anything measurable here, and ten seconds has
#: gone busy there more than once. Nothing below asserts elapsed time. The
#: claim is that separate processes serialize, so the budget sits well clear
#: of the measurement and `join` bounds a hang.
WRITER_LOCK_BUDGET_S = 60.0


def _record_many(path_text, endpoint, count, result_queue):
    try:
        stats = RouterStats(Path(path_text), lock_timeout_s=WRITER_LOCK_BUDGET_S)
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


@pytest.mark.skipif(os.name != "nt", reason="Windows open-handle semantics")
def test_held_windows_reader_contention_is_typed_and_bounded(tmp_path):
    """A reader denying delete-share must not leak host PermissionError detail."""
    p = tmp_path / "stats.json"
    RouterStats(p).record("seed", True)
    release, thread = _start_windows_reader_without_delete_share(p)
    blocked_stats = RouterStats(p, lock_timeout_s=0.05)
    started = time.monotonic()
    try:
        with pytest.raises(router_stats.RouterStatsError) as failure:
            blocked_stats.record("blocked", True)
    finally:
        operation_elapsed = time.monotonic() - started
        cleanup_started = time.monotonic()
        release.set()
        thread.join(2)
        cleanup_elapsed = time.monotonic() - cleanup_started
    assert not thread.is_alive(), f"reader cleanup incomplete after {cleanup_elapsed:.6f}s"
    assert failure.value.code == str(failure.value) == "STORE_BUSY"
    assert operation_elapsed < 1.0, (
        f"record took {operation_elapsed:.6f}s; reader cleanup took {cleanup_elapsed:.6f}s"
    )
    persisted = RouterStats(p)
    assert "blocked" not in blocked_stats.stats
    assert "blocked" not in persisted.stats
    assert blocked_stats.snapshot() == persisted.snapshot()
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
        process.join(2 * WRITER_LOCK_BUDGET_S)
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
