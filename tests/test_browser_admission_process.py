"""Real process death/races, with filesystem-only synthetic driver effects."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from harness import browser_control as browser

CHILD = r'''
import json, os, sys, time
from pathlib import Path
from harness import browser_control as browser
from harness.journey_lock import JourneyLockBusy
root, name, request, mode = Path(sys.argv[1]), *sys.argv[2:]
def driver(action):
    with (root/'effects.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'request_id':action['request_id']})+'\n')
        stream.flush(); os.fsync(stream.fileno())
    if mode == 'crash': os._exit(23)
    if mode == 'hold':
        (root/('driver-entered-'+name)).touch()
        deadline=time.monotonic()+10
        while not (root/'release-driver').exists():
            if time.monotonic()>deadline: raise RuntimeError('driver release missing')
            time.sleep(0.01)
    time.sleep(0.15)
    return {'ok':True, 'performed':True}
browser.register_driver('fixture', driver, binding_sha256='a'*64)
(root/('ready-'+name)).touch()
deadline=time.monotonic()+10
while not (root/'go').exists():
    if time.monotonic()>deadline: raise RuntimeError('start signal missing')
    time.sleep(0.01)
try:
    result=browser.attempt(root,run_id='r',request_id=request,at='fixture',
        action={'kind':'navigate','url':'https://example.test/'})
except JourneyLockBusy as exc:
    result={'phase':'store_busy','error_type':type(exc).__name__,
        'message':str(exc),'request_id':request}
(root/(name+'.json')).write_text(json.dumps(result),encoding='utf-8')
'''


def child(root, name, request, mode="return"):
    return subprocess.Popen(
        [sys.executable, "-c", CHILD, str(root), name, request, mode],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=0x08000000 if os.name == "nt" else 0,
        env={"SystemRoot": os.environ.get("SystemRoot", ""),
             "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
             "PYTHONNOUSERSITE": "1"},
    )


def finish(process):
    try:
        stdout, stderr = process.communicate(timeout=15)
        return (
            process.returncode,
            stdout.decode("utf-8", "replace"),
            stderr.decode("utf-8", "replace"),
        )
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)


def child_failure(name, code, stdout, stderr):
    return (
        f"{name} exited {code}\n"
        f"stdout:\n{stdout}\n"
        f"stderr:\n{stderr}"
    )


def wait_for(path, message, *, timeout=10):
    deadline = time.monotonic() + timeout
    while not path.exists():
        assert time.monotonic() < deadline, message
        time.sleep(0.01)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def effects(root):
    path = root / "effects.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def assert_single_dispatch_outcome(root, results, *, same_identifier):
    snapshot = browser.session(root, run_id="r")
    effect_rows = effects(root)
    assert snapshot["chain_intact"] is True
    assert snapshot["policy"]["max_actions"] == 1
    assert snapshot["delivery_unknown"] is False
    assert len(effect_rows) == 1
    assert snapshot["performed"] == 1 and snapshot["admitted"] == 1
    if same_identifier:
        assert results["one"] == results["two"]
        assert effect_rows[0]["request_id"] == results["one"]["request_id"]
        assert snapshot["attempted"] == 1
        return
    admitted = [result for result in results.values() if result["admitted"]]
    refused = [result for result in results.values() if not result["admitted"]]
    assert len(admitted) == 1 and len(refused) == 1
    assert effect_rows[0]["request_id"] == admitted[0]["request_id"]
    assert effect_rows[0]["request_id"] in {"a", "b"}
    assert refused[0]["request_id"] != admitted[0]["request_id"]
    assert refused[0]["performed"] is False
    assert refused[0]["phase"] == "settled"
    assert refused[0]["delivery_status"] == "not_dispatched"
    assert "cap of 1 is spent" in refused[0]["reason"]
    assert snapshot["attempted"] == 2


def opened(root, cap=5):
    def parent_driver(action):
        raise AssertionError("only the owned child process may perform this fixture")
    browser.register_driver("fixture", parent_driver, binding_sha256="a" * 64)
    try:
        browser.open_session(root, run_id="r", at="fixture", policy={
            "origins": ["https://example.test"], "max_actions": cap})
    finally:
        browser.clear_drivers()


def test_process_dies_after_effect_admission_blocks_fresh_process_replay(tmp_path):
    opened(tmp_path)
    (tmp_path / "go").touch()
    crashed = child(tmp_path, "crashed", "same", "crash")
    code, stdout, stderr = finish(crashed)
    assert code == 23, child_failure("crashed", code, stdout, stderr)
    snapshot = browser.session(tmp_path, run_id="r")
    assert snapshot["attempted"] == 1 and snapshot["delivery_unknown"] is True
    replay = child(tmp_path, "replay", "same")
    code, stdout, stderr = finish(replay)
    assert code == 0, child_failure("replay", code, stdout, stderr)
    result = read_json(tmp_path / "replay.json")
    assert result["phase"] == "admitted" and result["performed"] is None
    assert [row["request_id"] for row in effects(tmp_path)] == ["same"]


@pytest.mark.parametrize("winner", ["one", "two"])
@pytest.mark.parametrize("same_identifier", [True, False])
def test_busy_before_dispatch_can_be_replayed_after_originals_settle(
        tmp_path, same_identifier, winner):
    opened(tmp_path, cap=1)
    requests = {"one": "a", "two": "a" if same_identifier else "b"}
    owner = child(tmp_path, winner, requests[winner], "hold")
    contender_name = "two" if winner == "one" else "one"
    contender = None
    replay = None
    try:
        wait_for(
            tmp_path / f"ready-{winner}",
            "owner inert driver must reach the barrier")
        (tmp_path / "go").touch()
        wait_for(
            tmp_path / f"driver-entered-{winner}",
            "owner child must dispatch and hold the real browser guard")
        contender = child(tmp_path, contender_name, requests[contender_name])
        wait_for(
            tmp_path / f"ready-{contender_name}",
            "contender must reach the barrier")
        code, stdout, stderr = finish(contender)
        assert code == 0, child_failure(contender_name, code, stdout, stderr)
        busy = read_json(tmp_path / f"{contender_name}.json")
        assert busy == {
            "phase": "store_busy", "error_type": "JourneyLockBusy",
            "message": "STORE_BUSY", "request_id": requests[contender_name]}
        assert [row["request_id"] for row in effects(tmp_path)] == [
            requests[winner]]
        (tmp_path / "release-driver").touch()
        code, stdout, stderr = finish(owner)
        assert code == 0, child_failure(winner, code, stdout, stderr)
        replay = child(tmp_path, "replay", requests[contender_name])
        code, stdout, stderr = finish(replay)
        assert code == 0, child_failure("replay", code, stdout, stderr)
    finally:
        (tmp_path / "release-driver").touch()
        for process in (owner, contender, replay):
            if process is None:
                continue
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)
    results = {
        winner: read_json(tmp_path / f"{winner}.json"),
        contender_name: read_json(tmp_path / "replay.json"),
    }
    assert_single_dispatch_outcome(
        tmp_path, results, same_identifier=same_identifier)


@pytest.mark.parametrize("same_identifier", [True, False])
def test_simultaneous_processes_preserve_single_reservation_or_explicit_busy_replay(
        tmp_path, same_identifier):
    opened(tmp_path, cap=1)
    requests = {"one": "a", "two": "a" if same_identifier else "b"}
    first = child(tmp_path, "one", requests["one"])
    second = child(tmp_path, "two", requests["two"])
    replay = None
    try:
        wait_for(tmp_path / "ready-one", "first inert driver must reach the barrier")
        wait_for(tmp_path / "ready-two", "second inert driver must reach the barrier")
        (tmp_path / "go").touch()
        results = []
        for name, process in (("one", first), ("two", second)):
            code, stdout, stderr = finish(process)
            assert code == 0, child_failure(name, code, stdout, stderr)
            results.append((name, read_json(tmp_path / f"{name}.json")))
        busy = [
            (name, result) for name, result in results
            if result.get("phase") == "store_busy"]
        assert len(busy) <= 1
        results_by_name = dict(results)
        if busy:
            name, busy_result = busy[0]
            assert busy_result == {
                "phase": "store_busy", "error_type": "JourneyLockBusy",
                "message": "STORE_BUSY", "request_id": requests[name]}
            replay = child(tmp_path, "replay", requests[name])
            code, stdout, stderr = finish(replay)
            assert code == 0, child_failure("replay", code, stdout, stderr)
            results_by_name[name] = read_json(tmp_path / "replay.json")
    finally:
        for process in (first, second, replay):
            if process is None:
                continue
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)
    assert_single_dispatch_outcome(
        tmp_path, results_by_name, same_identifier=same_identifier)
