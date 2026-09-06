"""proc_kill.py -- spawn a subprocess whose whole tree can be reaped later.

Every oracle in this harness runs somebody else's code under a timeout, so the
timeout is only worth as much as the kill behind it. A candidate that spawns a
child and exits leaves that child holding the output pipe, and the drain that
follows the timeout then wedges on a process nobody is waiting for. The pair
here is the contract: spawn through `spawn_killable`, kill through
`_kill_tree`, and the precondition each needs from the other holds by
construction rather than by every caller remembering it.

`oracle.py` re-exports both names, because six modules imported them from
there before this file existed.
"""
from __future__ import annotations

import os
import signal
import subprocess

#: Where `spawn_killable` records the process group it created, so `_kill_tree`
#: does not have to ask the kernel for it later. See `_kill_tree` for why the
#: later question is the one that can fail.
_PGID_ATTR = "_flywheel_pgid"


def spawn_killable(*args, **kwargs) -> subprocess.Popen:
    """Popen whose whole descendant tree `_kill_tree` can actually reap.

    On POSIX the child leads a fresh session, so `os.killpg` targets that tree
    instead of the process group the child would otherwise share with the
    pytest parent. Without it, a hostile candidate's infinite loop is a
    grandchild in pytest's own group: the kill either misses it (it survives
    holding the pipe and the drain wedges) or, worse, signals pytest itself.
    Windows reaps via `taskkill /T` and needs nothing extra.

    A session leader is a group leader, so its pgid is its pid. Recording that
    here rather than looking it up at kill time is what lets `_kill_tree`
    address the group after the leader itself is gone.
    """
    if os.name != "nt":
        kwargs.setdefault("start_new_session", True)
    proc = subprocess.Popen(*args, **kwargs)
    if os.name != "nt" and kwargs.get("start_new_session"):
        setattr(proc, _PGID_ATTR, proc.pid)
    return proc


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill a process AND its descendants.

    `proc.kill()` alone is insufficient for shell=True on Windows: it
    terminates cmd.exe while the real workload (pytest running a hostile
    candidate) survives and holds the output pipes.

    On POSIX the group is addressed by the id `spawn_killable` stamped at
    spawn time rather than by `os.getpgid(proc.pid)`. The two agree while the
    leader is alive and unreaped, and they stop agreeing the moment it is not:
    `getpgid` on a reaped leader raises, and the fallback was `proc.kill()` on
    that same reaped pid, which reaps nothing at all. A process group outlives
    its leader for as long as any member is still in it, so the stamped id
    keeps working in the one case the lookup gives up on.

    SIGSTOP precedes SIGKILL because a stopped process cannot fork, so the
    group cannot gain a member between the two signals. Read that as a
    narrowing and not as the repair of a measured leak: 4,100 forks across ten
    rounds of a candidate spawning a child every 2ms left zero survivors under
    a plain SIGKILL on Linux 6.6, so the window is real in the standard and
    was not observable there.

    The lookup is refused when it answers with our own group. A plain `Popen`
    child inherits the caller's process group, so `getpgid` on it returns the
    group the harness is sitting in, and SIGSTOP on that group stops the
    process that issued the kill. A stopped process runs no handler and no
    alarm, so nothing resumes it and nothing reports it: the run wedges until
    something outside kills the job. `proc.kill()` is the honest reply. It
    reaps the process and not its descendants, which is a narrower kill than
    the caller wanted and the widest one available without a group of our own
    to address.
    """
    if os.name == "nt":
        subprocess.run(f"taskkill /T /F /PID {proc.pid}", shell=True,
                       capture_output=True, timeout=15)
        return
    pgid = getattr(proc, _PGID_ATTR, None)
    if pgid is None:
        try:
            pgid = os.getpgid(proc.pid)
        except Exception:
            proc.kill()
            return
        if pgid == os.getpgid(0):
            proc.kill()
            return
    try:
        # SIGSTOP and SIGKILL are the two signals a process cannot catch,
        # block or ignore, which is why the pair works on a hostile candidate.
        os.killpg(pgid, signal.SIGSTOP)
    except Exception:
        pass
    try:
        os.killpg(pgid, signal.SIGKILL)
    except Exception:
        proc.kill()
