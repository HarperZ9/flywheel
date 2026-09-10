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
root, name, request, mode = Path(sys.argv[1]), *sys.argv[2:]
def driver(action):
    with (root/'effects.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'request_id':action['request_id']})+'\n')
        stream.flush(); os.fsync(stream.fileno())
    if mode == 'crash': os._exit(23)
    time.sleep(0.15)
    return {'ok':True, 'performed':True}
browser.register_driver('fixture', driver)
(root/('ready-'+name)).touch()
deadline=time.monotonic()+10
while not (root/'go').exists():
    if time.monotonic()>deadline: raise RuntimeError('start signal missing')
    time.sleep(0.01)
result=browser.attempt(root,run_id='r',request_id=request,at='fixture',
    action={'kind':'navigate','url':'https://example.test/'})
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
        output = process.communicate(timeout=15)
        return process.returncode, output
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)


def opened(root, cap=5):
    browser.open_session(root, run_id="r", at="fixture", policy={
        "origins": ["https://example.test"], "max_actions": cap})


def test_process_dies_after_effect_admission_blocks_fresh_process_replay(tmp_path):
    opened(tmp_path)
    (tmp_path / "go").touch()
    crashed = child(tmp_path, "crashed", "same", "crash")
    assert finish(crashed)[0] == 23
    snapshot = browser.session(tmp_path, run_id="r")
    assert snapshot["attempted"] == 1 and snapshot["delivery_unknown"] is True
    replay = child(tmp_path, "replay", "same")
    code, output = finish(replay)
    assert code == 0, output
    result = json.loads((tmp_path / "replay.json").read_text())
    assert result["phase"] == "admitted" and result["performed"] is None
    assert len((tmp_path / "effects.jsonl").read_text().splitlines()) == 1


@pytest.mark.parametrize("same_identifier", [True, False])
def test_competing_processes_reserve_before_dispatch(tmp_path, same_identifier):
    opened(tmp_path, cap=1)
    first = child(tmp_path, "one", "a")
    second = child(tmp_path, "two", "a" if same_identifier else "b")
    try:
        deadline = time.monotonic() + 10
        while not all((tmp_path / ("ready-" + name)).exists() for name in ("one", "two")):
            assert time.monotonic() < deadline, "both inert drivers must reach the barrier"
            time.sleep(0.01)
        (tmp_path / "go").touch()
        for process in (first, second):
            code, output = finish(process)
            assert code == 0, output
    finally:
        for process in (first, second):
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)
    one = json.loads((tmp_path / "one.json").read_text())
    two = json.loads((tmp_path / "two.json").read_text())
    snapshot = browser.session(tmp_path, run_id="r")
    assert len((tmp_path / "effects.jsonl").read_text().splitlines()) == 1
    assert snapshot["performed"] == 1 and snapshot["admitted"] == 1
    if same_identifier:
        assert one == two
        assert snapshot["attempted"] == 1
    else:
        assert one["admitted"] is not two["admitted"]
        assert snapshot["attempted"] == 2
