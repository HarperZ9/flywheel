"""Falsifiers for background jobs in `flywheel code`."""
import json
import os
import threading
import time

import pytest

from harness.code_session.background import JobTable
from harness.code_session.backends import build_agent
from harness.code_session.session import new_session
from tests.test_code_session import ScriptBackend, _bare_runner


def _wait(cond, seconds=20):
    end = time.time() + seconds
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def _fake_start(job):
    job.cancel.wait(10)
    return (False, "[exit 130]\nstopped") if job.cancel.is_set() else (True, "[exit 0]\ndone")


def test_start_list_output_stop_with_a_fake_runner(tmp_path):
    events = []
    t = JobTable(str(tmp_path), record=lambda k, d: events.append((k, d)), start=_fake_start)
    ok, msg = t.start("npm run dev")
    assert ok and msg.startswith("started bg1")
    assert "bg1 running" in t.listing()
    assert t.stop("bg1")[1].startswith("stopping bg1")
    assert _wait(lambda: t.jobs["bg1"].result is not None)
    assert t.jobs["bg1"].status() == "stopped"
    assert [k for k, _ in events] == ["start", "stop", "finish"]
    assert t.output("nope")[0] is False


def test_job_limit(tmp_path):
    t = JobTable(str(tmp_path), start=_fake_start)
    for _ in range(8):
        t.start("x")
    assert t.start("y")[0] is False
    t.stop_all()


def test_background_is_a_command_for_the_permission_mode(tmp_path):
    asked = []
    s = new_session(build_agent([ScriptBackend(['TOOL run_background {"cmd": "echo hi"}', "ok"])]),
                    str(tmp_path), mode="edit", approver=lambda n, a: asked.append(n) or "no",
                    runner=_bare_runner)
    s.turn("start it")
    assert asked == ["run_background"] and not s.executor.jobs.jobs
    p = new_session(build_agent([ScriptBackend(['TOOL run_background {"cmd": "echo hi"}', "ok"])]),
                    str(tmp_path), mode="plan", runner=_bare_runner)
    p.turn("start it")
    assert not p.executor.jobs.jobs


def test_denylist_applies_to_background_commands(tmp_path):
    s = new_session(build_agent([ScriptBackend([])]), str(tmp_path), mode="auto",
                    runner=_bare_runner)
    res = s.executor.execute("run_background", {"cmd": "rm -rf /"})
    assert not res.ok and not s.executor.jobs.jobs      # the pre-action monitor holds it
    direct = s.executor._t_run_background({"cmd": "rm -rf /"})
    assert direct[0] is False and "denylist" in direct[1]   # and the gate refuses it too


def test_ledger_records_background_events(tmp_path):
    s = new_session(build_agent([ScriptBackend([])]), str(tmp_path), mode="auto",
                    runner=_bare_runner)
    s.executor.jobs._start = _fake_start
    s.executor.execute("run_background", {"cmd": "serve"})
    s.close()
    assert _wait(lambda: any(json.loads(e.content).get("event") == "finish"
                             for e in s.ledger.entries if e.kind == "background"))


def test_a_real_sandboxed_job_streams_output_and_stops(tmp_path):
    from harness.sandboxed_runner import SandboxUnavailable, sandboxed_run
    try:
        sandboxed_run("echo probe", str(tmp_path), timeout_seconds=30)
    except SandboxUnavailable:
        pytest.skip("this host has no OS sandbox")
    (tmp_path / "loop.py").write_text(
        "import time\nfor i in range(600):\n    print('tick', i, flush=True)\n    time.sleep(0.1)\n",
        encoding="utf-8")
    t = JobTable(str(tmp_path))
    t.start("python loop.py")
    assert _wait(lambda: "tick 3" in t.output("bg1")[1], 30), t.output("bg1")
    t.stop("bg1")
    assert _wait(lambda: t.jobs["bg1"].result is not None, 20)
    assert t.jobs["bg1"].status() == "stopped" and "[exit 130]" in t.jobs["bg1"].result[1]
