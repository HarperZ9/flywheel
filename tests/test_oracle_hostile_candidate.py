"""Hostile-candidate liveness contract (found live 2026-07-09).

A model-generated candidate with an infinite loop at import time wedged the
difficulty screen for 10+ minutes: subprocess.run(shell=True, timeout=) on
Windows kills only cmd.exe, the pytest grandchild survives holding the stdout
pipe, and run()'s post-kill drain blocks forever. The contract: a hostile
candidate costs AT MOST timeout + kill grace, returns rc=124, and never
wedges the harness. The old implementation fails this test by hanging.
"""
import time
from pathlib import Path

from harness.oracle import PytestOracle
from harness.task import load_task

TASK_DIR = Path(__file__).parent.parent / "tasks" / "example_pass"

HOSTILE = (
    "import time\n"
    "def add(a, b):\n"
    "    return a + b\n"
    "while True:\n"
    "    time.sleep(0.05)\n"
)


def test_infinite_loop_candidate_times_out_without_wedging(tmp_path):
    oracle = PytestOracle(timeout=5)
    task = load_task(TASK_DIR, workdir=tmp_path / "w")
    started = time.monotonic()
    result = oracle.verify(HOSTILE, task)
    elapsed = time.monotonic() - started
    assert elapsed < 45, (
        f"oracle took {elapsed:.0f}s for a 5s-timeout hostile candidate — "
        "the tree-kill did not take; the harness would wedge on this input")
    assert result.rc == 124, f"expected timeout rc=124, got {result.rc}"
    assert result.passed is False
