"""Long-lived lane sessions (WP10): one child per lane for the tools that outlive a call.

A background relay run or index router job lives in the lane child that started
it. A per-call child is killed after its one call, so start, status and result
sent as three calls used to reach three different children. The control test
below shows that failure with the per-call path; the session tests show the
same three calls reaching one child and returning the same run.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from harness.lane_session import LaneSessionPool, is_session_tool, session_tools
from harness.mcp_client import LaunchSpec

FAKE = Path(__file__).with_name("fake_session_mcp.py")
ROOT = Path(__file__).resolve().parents[1]


def pid_alive(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return not _zombie(pid)
    import ctypes
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFO
    if not handle:
        return False
    code = ctypes.c_ulong()
    try:
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)
    return code.value == 259  # STILL_ACTIVE


def _zombie(pid: int) -> bool:
    """A killed child the pool has not reaped yet still answers kill(pid, 0),
    until the pool polls it on the next call. Its state is Z: it has exited.
    Same reading as test_exec_oracle; ps covers a host with no /proc."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        out = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip().startswith("Z")
    return stat.rsplit(")", 1)[1].split()[0] == "Z"


def wait_dead(pid: int, seconds: float = 10.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            return True
        time.sleep(0.1)
    return False


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _launch(tmp_path: Path, **env: str) -> LaunchSpec:
    base = {"FAKE_PID_LOG": str(tmp_path / "pids.log"),
            "FAKE_CALL_LOG": str(tmp_path / "calls.log"), **env}
    return LaunchSpec((sys.executable, str(FAKE)), cwd=str(tmp_path),
                      env_overrides=tuple(sorted(base.items())), inherit_env=True)


def _pids(tmp_path: Path) -> list[int]:
    log = tmp_path / "pids.log"
    return [int(x) for x in log.read_text().split()] if log.exists() else []


@pytest.fixture
def pool():
    made = LaneSessionPool(idle_timeout_s=60, busy_cap_s=600, clock=Clock(), reaper=False)
    yield made
    made.close_all()


def _until_done(pool, launch, run_id):
    for _ in range(50):
        status = pool.call("relay", "local_agent_status", launch, {"run_id": run_id}, 10)
        if status.get("state") == "done":
            return status
        time.sleep(0.05)
    raise AssertionError(status)


def test_the_session_tools_are_relay_runs_and_index_router_jobs():
    assert session_tools("relay") == ("local_agent_start", "local_agent_status",
                                      "local_agent_result", "local_agent_runs")
    assert session_tools("index") == tuple(f"index.router.job.{a}" for a in (
        "start", "status", "result", "cancel", "resume"))
    assert is_session_tool("relay", "local_agent_status")
    assert not is_session_tool("relay", "local_agent_run")
    assert session_tools("gather") == ()


def test_control_a_per_call_child_loses_the_run(tmp_path):
    from harness.lane_caller import _call
    launch = _launch(tmp_path)
    started = _call("relay", "local_agent_start", launch, {"goal": "g"}, 10)
    status = _call("relay", "local_agent_status", launch, {"run_id": started["run_id"]}, 10)
    assert "unknown run_id" in status["error"]
    assert len(_pids(tmp_path)) == 2


def test_start_status_and_result_as_three_calls_return_the_same_run(pool, tmp_path):
    launch = _launch(tmp_path)
    started = pool.call("relay", "local_agent_start", launch, {"goal": "g"}, 10)
    assert started["state"] == "running"
    status = _until_done(pool, launch, started["run_id"])
    result = pool.call("relay", "local_agent_result", launch, {"run_id": started["run_id"]}, 10)
    assert status["run_id"] == result["run_id"] == started["run_id"]
    assert result == {"run_id": started["run_id"], "state": "done",
                      "result": {"final": "did g"}}
    assert len(_pids(tmp_path)) == 1


def test_idle_timeout_kills_the_child(pool, tmp_path):
    launch = _launch(tmp_path)
    pool.call("relay", "local_agent_runs", launch, {}, 10)
    pid = _pids(tmp_path)[0]
    pool._clock.now += 59
    assert pool.reap() == []
    pool._clock.now += 2
    assert pool.reap() == ["relay"]
    assert wait_dead(pid)
    assert pool.describe() == {}


def test_a_busy_session_outlives_the_idle_timeout_until_its_run_ends(pool, tmp_path):
    launch = _launch(tmp_path, FAKE_RUN_SECONDS="0.6")
    started = pool.call("relay", "local_agent_start", launch, {"goal": "g"}, 10)
    pid = _pids(tmp_path)[0]
    pool._clock.now += 120
    assert pool.reap() == []            # the run is still running, so the child stays
    assert pid_alive(pid)
    time.sleep(1.0)
    assert pool.reap() == ["relay"]     # the run finished; nothing holds the child now
    assert wait_dead(pid)
    assert started["run_id"].endswith(str(pid))


def test_a_busy_session_is_ended_at_the_busy_cap(pool, tmp_path):
    launch = _launch(tmp_path)
    pool.call("relay", "local_agent_start", launch, {"goal": "hold"}, 10)
    pid = _pids(tmp_path)[0]
    pool._clock.now += 120
    assert pool.reap() == []
    pool._clock.now += 600
    assert pool.reap() == ["relay"]
    assert wait_dead(pid)


def test_a_changed_launch_replaces_the_session(pool, tmp_path):
    pool.call("relay", "local_agent_runs", _launch(tmp_path), {}, 10)
    first = _pids(tmp_path)[0]
    pool.call("relay", "local_agent_runs", _launch(tmp_path, EXTRA="1"), {}, 10)
    assert len(_pids(tmp_path)) == 2
    assert wait_dead(first)


def test_a_dead_child_is_replaced_on_the_next_call(pool, tmp_path):
    launch = _launch(tmp_path)
    pool.call("relay", "local_agent_runs", launch, {}, 10)
    subprocess.run(["taskkill", "/PID", str(_pids(tmp_path)[0]), "/F"] if os.name == "nt"
                   else ["kill", "-9", str(_pids(tmp_path)[0])], capture_output=True)
    assert wait_dead(_pids(tmp_path)[0])
    assert "runs" in pool.call("relay", "local_agent_runs", launch, {}, 10)
    assert len(_pids(tmp_path)) == 2


def test_a_child_that_cannot_start_reads_unavailable(pool, tmp_path):
    missing = LaunchSpec((str(tmp_path / "no-such.exe"),), cwd=str(tmp_path))
    out = pool.call("relay", "local_agent_runs", missing, {}, 5)
    assert out["error"].startswith("lane 'relay' unavailable: ")
    assert pool.describe() == {}


def test_a_session_call_is_admitted_only_for_session_tools(pool, tmp_path):
    with pytest.raises(ValueError):
        pool.call("relay", "local_agent_run", _launch(tmp_path), {}, 10)


def test_close_all_kills_every_child(pool, tmp_path):
    pool.call("relay", "local_agent_runs", _launch(tmp_path), {}, 10)
    pid = _pids(tmp_path)[0]
    pool.close_all()
    assert wait_dead(pid)


_ENGINE = textwrap.dedent("""
    import sys, time
    sys.path.insert(0, {root!r})
    from harness.lane_session import default_pool
    from harness.mcp_client import LaunchSpec
    launch = LaunchSpec((sys.executable, {fake!r}),
                        env_overrides=(("FAKE_PID_LOG", {log!r}),), inherit_env=True)
    default_pool().call("relay", "local_agent_start", launch, {{"goal": "hold"}}, 10)
    print("started", flush=True)
    if sys.argv[1] == "hang":
        time.sleep(60)
""")


@pytest.mark.parametrize("how", ["exit", "killed"])
def test_engine_exit_leaves_no_orphan(tmp_path, how):
    script = tmp_path / "engine.py"
    script.write_text(_ENGINE.format(root=str(ROOT), fake=str(FAKE),
                                     log=str(tmp_path / "pids.log")), encoding="utf-8")
    engine = subprocess.Popen([sys.executable, str(script),
                               "hang" if how == "killed" else "exit"],
                              stdout=subprocess.PIPE, text=True)
    assert engine.stdout.readline().strip() == "started"
    child = _pids(tmp_path)[0]
    if how == "killed":
        engine.kill()                   # no atexit: the child sees stdin close
    engine.wait(timeout=20)
    assert wait_dead(child, 15), f"lane child {child} outlived the engine ({how})"


def test_the_gateway_closes_lane_sessions_when_it_stops_serving(monkeypatch):
    import harness.gateway as gateway
    import harness.lane_session as lane_session
    closed = []
    monkeypatch.setattr(lane_session, "close_lane_sessions", lambda: closed.append(1))

    class _Server:
        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            pass

    class _Service:
        def shutdown(self):
            pass

    monkeypatch.setattr(gateway._Handler, "operation_service", _Service())
    gateway._serve_all([_Server()])
    assert closed == [1]
