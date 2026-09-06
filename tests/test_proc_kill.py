"""proc_kill falsifier -- the timeout is worth exactly what the kill is worth.

Every oracle here runs somebody else's code under a timeout. A timeout that
kills the shell and leaves the tree behind reports a clean stop while the
candidate keeps running, holding the output pipe the next drain will wait on.
These tests plant that tree and check it is gone.
"""
import os
import subprocess
import sys
import time

import pytest

from harness.proc_kill import _PGID_ATTR, _kill_tree, spawn_killable

posix_only = pytest.mark.skipif(
    os.name == "nt",
    reason="process groups are POSIX; the Windows path reaps via taskkill /T "
           "and is covered by tests/test_oracle_hostile_candidate.py")


def _alive(pid: int) -> bool:
    """Live and not a zombie.

    A zombie still answers `os.kill(pid, 0)`, so the cheap probe would call a
    reaped process alive for as long as its parent took to wait on it. Reading
    the state field costs one open and removes the whole race.
    """
    try:
        with open(f"/proc/{pid}/stat") as fh:
            raw = fh.read()
    except OSError:
        return _kill_probe(pid)
    # comm is "(name)" and may contain ')', so the state is the first field
    # after the LAST one.
    return raw.rsplit(")", 1)[1].split()[0] != "Z"


def _kill_probe(pid: int) -> bool:
    """Fallback for a host without /proc, which is macOS."""
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _wait_until_gone(pid: int, seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + seconds
    while _alive(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    return not _alive(pid)


def _leader_that_orphans_a_sleeper(tmp_path, sleep_for: int = 90):
    """A leader that spawns a long sleeper, prints its pid, and exits at once.

    The exit is the point. It is what makes the leader reapable while the tree
    it left behind is still running.
    """
    script = tmp_path / "leader.py"
    script.write_text(
        "import subprocess, sys\n"
        "p = subprocess.Popen([sys.executable, '-c', "
        f"'import time; time.sleep({sleep_for})'])\n"
        "print(p.pid, flush=True)\n",
        encoding="utf-8")
    proc = spawn_killable([sys.executable, str(script)],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc


@posix_only
def test_spawn_killable_records_the_group_it_created(tmp_path):
    """The stamp has to be the group, not a number that resembles one."""
    proc = spawn_killable([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert getattr(proc, _PGID_ATTR) == proc.pid, (
            "a session leader is a group leader, so its pgid is its pid; "
            "a stamp that disagrees would send the kill somewhere else")
        assert os.getpgid(proc.pid) == proc.pid, (
            "start_new_session did not take effect, so the child is still in "
            "the pytest process group and killing that group kills pytest")
    finally:
        _kill_tree(proc)
        proc.wait(timeout=10)


@posix_only
def test_the_group_outlives_its_leader_and_is_still_reachable(tmp_path):
    """The case `os.getpgid` cannot answer and the stamp can.

    A leader that spawns a child and exits is the ordinary shape of a shell
    that backgrounds something. Once that leader is reaped, `getpgid` on its
    pid raises, and the old fallback was `proc.kill()` on the same reaped pid,
    which reaps nothing: the sleeper below would still be running. A process
    group outlives its leader while any member remains, so the id recorded at
    spawn time still addresses the tree.
    """
    proc = _leader_that_orphans_a_sleeper(tmp_path)
    # readline and wait, never communicate. The sleeper inherited the pipe's
    # write end, so a drain here waits for an EOF that arrives when the
    # sleeper exits, which is the wedge this whole module exists to prevent.
    sleeper = int(proc.stdout.readline().decode().strip())
    proc.wait(timeout=30)
    # wait() reaped the leader, so the lookup the old kill relied on now
    # raises. Measured: 5 of 5 rounds leaked the sleeper before this change.
    with pytest.raises(ProcessLookupError):
        os.getpgid(proc.pid)
    try:
        assert _alive(sleeper), (
            "the sleeper died before the kill under test ran, so this asserts "
            "nothing about the kill")
        _kill_tree(proc)
        assert _wait_until_gone(sleeper), (
            f"sleeper {sleeper} outlived _kill_tree on a reaped leader, which "
            "is the leak the stamped pgid exists to close")
    finally:
        if _alive(sleeper):
            os.kill(sleeper, 9)


@posix_only
def test_a_process_not_spawned_here_still_gets_killed(tmp_path, monkeypatch):
    """No stamp means fall back to the lookup, never fall through to nothing.

    `_kill_tree` is documented as taking a `spawn_killable` process. A caller
    that forgets is a bug, and the kill still has to happen: silently doing
    nothing would turn a forgotten import into a leaked process tree.

    The second assertion is where the kill must not go. A plain `Popen` child
    inherits the caller's process group, so the lookup answers with the group
    pytest is running in, and SIGSTOP on it stops pytest. Nothing resumes a
    stopped process and no alarm fires inside one, so this ran for fifteen
    minutes on an Ubuntu runner and ended when the runner was recycled, with
    no test named in the log.

    `os.killpg` is replaced rather than watched so a build with that bug fails
    here instead of taking the run down and reporting nothing.
    """
    issued = []
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: issued.append((pgid, sig)))
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    assert not hasattr(proc, _PGID_ATTR)
    try:
        assert os.getpgid(proc.pid) == os.getpgid(0), (
            "the child is in its own group, so this host does not reproduce "
            "the case under test and the assertion below proves nothing")
        _kill_tree(proc)
        assert issued == [], (
            f"_kill_tree signalled its caller's own process group: {issued}")
        assert _wait_until_gone(proc.pid), "the unstamped process survived"
    finally:
        if _alive(proc.pid):
            os.kill(proc.pid, 9)
        proc.wait(timeout=10)


@posix_only
def test_the_kill_does_not_reach_the_process_that_issued_it():
    """The failure mode worse than a leak.

    Without a fresh session the child shares pytest's process group, and
    `killpg` on that group ends the test run itself. This asserts the two
    groups differ, which is the property that makes the kill safe to issue.
    """
    proc = spawn_killable([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert getattr(proc, _PGID_ATTR) != os.getpgid(0), (
            "the child's group is pytest's own group; killing it would take "
            "the test run with it")
    finally:
        _kill_tree(proc)
        proc.wait(timeout=10)
