import os
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from desktop.tool import installed_launch_acceptance_platform as platform
from desktop.tool.installed_launch_acceptance_model import ProcessHandle
from desktop.tool import installed_launch_acceptance_census as census


def test_successful_empty_census_is_distinct_from_unavailable():
    captured = [{"pid": 55, "creation_time": "first"}]
    assert platform._surviving_captured_pids(captured, {}) == []
    assert platform._surviving_captured_pids(captured, None) == [55]


@pytest.mark.parametrize("captured_time,live_time", [("", "new"), ("old", ""), (None, "new")])
def test_missing_creation_witness_cannot_disprove_survival(captured_time, live_time):
    assert platform._surviving_captured_pids(
        [{"pid": 55, "creation_time": captured_time}], {55: live_time}) == [55]


@pytest.mark.skipif(os.name != "nt", reason="actual Windows process census")
def test_actual_census_keeps_live_child_and_clears_only_waited_child():
    controller = platform.LocalProcessController()
    child = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE)
    try:
        before = controller.process_creation_times([child.pid])
        assert before is not None and before.get(child.pid)
        captured = [{"pid": child.pid, "creation_time": before[child.pid]}]
        assert platform._surviving_captured_pids(captured, before) == [child.pid]
        child.terminate()
        child.wait(timeout=10)
        after = controller.process_creation_times([child.pid])
        assert after == {}
        assert platform._surviving_captured_pids(captured, after) == []
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)
        child.stdin.close()


@pytest.mark.parametrize("live,expected", [({}, []), (None, [55]), ({55: "first"}, [55]),
                                          ({55: "second"}, [])])
def test_job_cleanup_independent_census_overrides_empty_job_report(monkeypatch, live, expected):
    controller = platform.LocalProcessController()
    proc = SimpleNamespace(terminate_and_verify=lambda: {"state": "PASS", "job_active_pids_after": []})
    monkeypatch.setattr(controller, "process_creation_times", lambda pids: live)
    monkeypatch.setattr(controller, "is_port_open", lambda port: False)
    result = controller._cleanup_job(ProcessHandle(44, proc, True, ""), 1234,
                                     [{"pid": 55, "creation_time": "first"}])
    assert result["captured_descendant_survivors"] == expected
    assert result["surviving_pids"] == expected
    assert result["state"] == ("FAIL" if expected else "PASS")
    assert result["captured_census_available"] is (live is not None)


@pytest.mark.parametrize("code,body", [(1, "[]"), (0, ""), (0, "null"), (0, "{"),
    (0, '[{"ProcessId":true,"ParentProcessId":1}]'),
    (0, '[{"ProcessId":55,"ParentProcessId":1},{"ProcessId":55,"ParentProcessId":1}]')])
def test_failed_or_malformed_census_remains_unavailable(monkeypatch, code, body):
    monkeypatch.setattr(census.os, "name", "nt")
    monkeypatch.setattr(census.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=code, stdout=body))
    assert census.process_rows() is None


@pytest.mark.parametrize("failure", [OSError("synthetic"), subprocess.TimeoutExpired("synthetic", 10)])
def test_census_launch_and_timeout_failure_remain_unavailable(monkeypatch, failure):
    monkeypatch.setattr(census.os, "name", "nt")
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr(census.subprocess, "run", fail)
    assert census.process_rows() is None


@pytest.mark.parametrize("rows", [[], [{"ProcessId":99,"ParentProcessId":1,"CreationDate":"other"}]])
def test_successful_unmatched_census_retains_known_empty_projection(monkeypatch, rows):
    monkeypatch.setattr(census.os, "name", "nt")
    monkeypatch.setattr(census.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stdout=json.dumps(rows)))
    assert platform.LocalProcessController().process_creation_times([55]) == {}
