"""The bounded tree wait the exec_oracle tree-kill tests rely on."""
import os
import subprocess as sp
import sys
import threading
import time

import pytest

from tests._tree_wait import _await_tree_gone, _describe


@pytest.mark.skipif(os.name == "nt", reason="POSIX process groups")
def test_tree_wait_outlasts_a_teardown_slower_than_the_old_window():
    """The fixed 5 s window test_exec_oracle.py used to sleep through called a tree that
    was still dying a survivor. A group whose last member exits at 5.5 s is
    not a leak; the bounded poll waits it out and still answers promptly."""
    proc = sp.Popen([sys.executable, "-c", "import time; time.sleep(5.5)"],
                    start_new_session=True)
    reaper = threading.Thread(target=proc.wait, daemon=True)
    reaper.start()
    try:
        started = time.monotonic()
        survivors = _await_tree_gone(proc.pid, proc.pid)
        elapsed = time.monotonic() - started
        assert survivors == {}, _describe(survivors)
        assert 5.0 < elapsed < 15.0, elapsed
    finally:
        if proc.poll() is None:
            proc.kill()
        reaper.join(timeout=5)


@pytest.mark.skipif(os.name == "nt", reason="POSIX process groups")
def test_tree_wait_still_reports_a_real_survivor():
    """The false-success control: a live group member must come back named."""
    proc = sp.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                    start_new_session=True)
    try:
        survivors = _await_tree_gone(proc.pid, proc.pid, budget=0.3)
        assert proc.pid in survivors, survivors
    finally:
        proc.kill()
        proc.wait(timeout=10)
