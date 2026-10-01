"""_tree_wait.py -- wait for a killed process tree to disappear, then say what is left.

Shared by the tree-kill tests in test_exec_oracle.py. Linux reads /proc; a
host without /proc falls back to signal 0.
"""
import os
import time


def _pid_alive(pid: int) -> bool:
    """True if `pid` is a live, non-zombie process. A zombie (state Z, dead
    but not yet reaped by its parent) still answers os.kill(pid, 0) as if it
    existed, which would make this probe flaky right around the reap window;
    reading /proc/<pid>/stat lets a zombie count as gone, since it has
    already stopped running and cannot resume the sleep this test plants."""
    try:
        with open(f"/proc/{pid}/stat") as f:
            stat = f.read()
    except (FileNotFoundError, ProcessLookupError):
        return False
    # comm is "(name)" and may itself contain ')'; state is the first field
    # after the LAST ')'.
    state = stat.rsplit(")", 1)[1].split()[0]
    return state not in _DEAD_STATES


#: Z is a zombie, X and x are a task the kernel is tearing down. None of them
#: runs again, so none of them is a survivor.
_DEAD_STATES = ("Z", "X", "x")

#: How long the tree may take to disappear after the kill. The wait returns as
#: soon as the tree is gone, so a green run pays nothing for the length. The
#: old fixed 5 s window failed once on a loaded ubuntu runner (run
#: 36886773490, attempt 1): the probe said alive, and the read for the failure
#: message one line later found /proc/<pid> already gone.
TREE_GONE_BUDGET = 30.0


def _proc_table() -> dict:
    """One pass over /proc: pid -> (state, ppid, pgrp, session).

    Every decision and every failure message below comes from one table, so a
    survivor is reported with the facts that made it a survivor, never with a
    second read taken after it died.
    """
    table = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat") as f:
                fields = f.read().rsplit(")", 1)[1].split()
        except OSError:
            continue
        table[int(entry)] = tuple(fields[:4])
    return table


def _tree_survivors(pgid: int, pid: int) -> dict:
    """Live members of process group `pgid`, plus `pid` if it left the group."""
    if not os.path.isdir("/proc"):
        # No /proc (macOS): signal 0 answers for the group and the pid. A
        # zombie answers too, so this branch is stricter, never looser.
        alive = {}
        for probe, target in ((os.killpg, pgid), (os.kill, pid)):
            try:
                probe(target, 0)
                alive[target] = ("?", "?", str(pgid), "?")
            except ProcessLookupError:
                pass
            except PermissionError:
                alive[target] = ("?", "?", str(pgid), "?")
        return alive
    return {p: f for p, f in _proc_table().items()
            if f[0] not in _DEAD_STATES and (p == pid or int(f[2]) == pgid)}


def _await_tree_gone(pgid: int, pid: int, budget: float = TREE_GONE_BUDGET) -> dict:
    """Poll until group `pgid` has no live member and `pid` is gone.

    Returns the survivors from the last snapshot: empty on success. A bounded
    poll replaces the fixed sleep, so a slow teardown on a loaded host costs
    time, not a false failure, and a real leak still fails at the deadline.
    """
    deadline = time.monotonic() + budget
    while True:
        survivors = _tree_survivors(pgid, pid)
        if not survivors or time.monotonic() >= deadline:
            return survivors
        time.sleep(0.05)


def _describe(survivors: dict) -> str:
    return "; ".join(f"pid={p} state={f[0]} ppid={f[1]} pgrp={f[2]} session={f[3]}"
                     for p, f in sorted(survivors.items()))


# The candidate both tree tests run: it records its grandchild's pid and the
# process group the oracle built, then outlives any timeout.
def _tree_candidate(pidfile) -> str:
    return (
        "import os, subprocess, sys, time\n"
        "p = subprocess.Popen([sys.executable, '-c', "
        "'import time; time.sleep(60)'])\n"
        f"open({str(pidfile)!r}, 'w').write(f'{{p.pid}} {{os.getpgid(p.pid)}}')\n"
        "time.sleep(60)\n"
    )


def _read_tree_ids(text_once_written, pidfile) -> tuple:
    pid, pgid = text_once_written(
        pidfile, timeout=5.0,
        why="candidate never reached the point of recording its "
            "grandchild's pid -- the test setup itself is broken, "
            "not the fix").split()
    return int(pid), int(pgid)
