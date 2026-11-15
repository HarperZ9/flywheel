"""Parallel tool calls, but only the safe subset.

A turn that emits several side-effect-free reads runs them concurrently; the moment
a write or exec is in the batch, the whole turn runs sequentially and in order, so
the gate and the ledger ordering are never weakened.
"""
import threading
import time

from relay.local_loop import _execute_calls


class _Res:
    def __init__(self, ok, output):
        self.ok = ok
        self.output = output


class _RecordingExecutor:
    def __init__(self, delay=0.03):
        self.delay = delay
        self._active = 0
        self.max_active = 0
        self._lock = threading.Lock()
        self.start_order = []

    def execute(self, name, args):
        with self._lock:
            self._active += 1
            self.max_active = max(self.max_active, self._active)
            self.start_order.append(name)
        time.sleep(self.delay)
        with self._lock:
            self._active -= 1
        return _Res(True, f"{name}:{args.get('path', args.get('cmd', ''))}")


def test_all_read_batch_runs_concurrently_results_in_order():
    ex = _RecordingExecutor()
    calls = [("read_file", {"path": f"{i}.py"}) for i in range(4)]
    results = _execute_calls(ex, calls)
    assert ex.max_active > 1                                   # genuinely concurrent
    assert [r.output for r in results] == [f"read_file:{i}.py" for i in range(4)]  # order kept


def test_batch_with_a_write_runs_sequentially_in_order():
    ex = _RecordingExecutor()
    calls = [("read_file", {"path": "a.py"}),
             ("write_file", {"path": "b.py"}),
             ("read_file", {"path": "c.py"})]
    results = _execute_calls(ex, calls)
    assert ex.max_active == 1                                  # never concurrent with a write
    assert ex.start_order == ["read_file", "write_file", "read_file"]
    assert [r.output for r in results] == ["read_file:a.py", "write_file:b.py", "read_file:c.py"]


def test_a_run_tool_forces_sequential():
    ex = _RecordingExecutor()
    _execute_calls(ex, [("read_file", {"path": "a.py"}), ("run", {"cmd": "ls"})])
    assert ex.max_active == 1


def test_single_read_is_not_parallelized():
    ex = _RecordingExecutor()
    _execute_calls(ex, [("read_file", {"path": "x.py"})])
    assert ex.max_active == 1
