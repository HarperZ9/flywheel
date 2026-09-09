"""Projects Index workspace-map registry concurrency regressions."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from harness import index_jobs
from harness.index_job_registry import _lock_path
from harness.journey_lock import ExclusiveJourneyLock


def test_threaded_duplicate_start_is_single_flight(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    run_root = tmp_path / "run"
    starts: list[str] = []
    lock = threading.Lock()

    def fake_run(action, root_s, run_root_arg, args):
        if action == "start":
            with lock:
                starts.append(root_s)
                job_id = f"job-{len(starts)}"
            time.sleep(0.2)
            return _status(root_s, job_id, "running")
        if action == "status":
            return _status(root_s, args[0], "running")
        raise AssertionError(action)

    monkeypatch.setattr(index_jobs, "_run", fake_run)

    results: list[dict] = []
    threads = [
        threading.Thread(
            target=lambda: results.append(
                index_jobs.start_workspace_map(root, run_root=run_root))),
        threading.Thread(
            target=lambda: results.append(
                index_jobs.start_workspace_map(root, run_root=run_root))),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert [result.get("error_type") for result in results] == [None, None]
    assert {result["job_id"] for result in results} == {"job-1"}
    assert starts == [str(root.resolve())]


def test_registry_lock_contention_returns_typed_busy(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    run_root = tmp_path / "run"
    monkeypatch.setattr(index_jobs, "DEFAULT_LOCK_TIMEOUT_S", 0.01)

    with ExclusiveJourneyLock.acquire(_lock_path(run_root), timeout_s=1.0):
        out = index_jobs.start_workspace_map(root, run_root=run_root)

    assert out["status"] == "failed"
    assert out["error_type"] == "INDEX_REGISTRY_BUSY"
    assert out["job_id"] == ""


def test_subprocess_start_same_root_is_single_flight(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    run_root = tmp_path / "run"
    fake_bin = _install_fake_index(tmp_path)

    procs = [
        _start_proc(root, run_root, fake_bin),
        _start_proc(root, run_root, fake_bin),
    ]
    outputs = [_finish(proc) for proc in procs]

    assert [out.get("error_type") for out in outputs] == [None, None]
    assert {out["job_id"] for out in outputs} == {outputs[0]["job_id"]}
    assert _router_actions(run_root).count(["router-job", "start"]) == 1


def test_subprocess_start_different_roots_preserves_both_registry_rows(tmp_path):
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    run_root = tmp_path / "run"
    fake_bin = _install_fake_index(tmp_path)

    procs = [
        _start_proc(root_a, run_root, fake_bin, save_sleep=0.2),
        _start_proc(root_b, run_root, fake_bin, save_sleep=0.2),
    ]
    outputs = [_finish(proc) for proc in procs]

    registry_doc = json.loads(
        (run_root / "index-workspace-map-jobs.json").read_text(
            encoding="utf-8"))
    registry = registry_doc["roots"]
    assert set(registry) == {str(root_a.resolve()), str(root_b.resolve())}
    assert {row["job_id"] for row in registry.values()} == {
        out["job_id"] for out in outputs
    }


def _status(root: str, job_id: str, status: str) -> dict[str, object]:
    return {
        "schema": "index.router-job-status/v1",
        "job_id": job_id,
        "root": root,
        "root_sha256_prefix": "a" * 16,
        "status": status,
        "phase": "building" if status == "running" else status,
        "completed_repos": 1,
        "total_repos": 2,
        "result_available": False,
        "result_sha256": None,
        "error_type": None,
        "message": None,
    }


def _install_fake_index(tmp_path: Path) -> Path:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    script = fake_bin / "fake_index.py"
    script.write_text(_FAKE_INDEX, encoding="utf-8")
    if os.name == "nt":
        wrapper = fake_bin / "index.cmd"
        wrapper.write_text(
            f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n',
            encoding="utf-8",
        )
    else:
        wrapper = fake_bin / "index"
        wrapper.write_text(
            f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n',
            encoding="utf-8",
        )
        wrapper.chmod(0o755)
    return fake_bin


def _repo_path() -> Path:
    return Path(__file__).resolve().parent.parent


def _start_proc(root: Path, run_root: Path, fake_bin: Path,
                *, save_sleep: float = 0) -> subprocess.Popen:
    env = os.environ.copy()
    env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")
    env["PYTHONPATH"] = (
        str(_repo_path()) + os.pathsep + env.get("PYTHONPATH", ""))
    env["FAKE_INDEX_START_SLEEP"] = "0.2"
    env["FAKE_SAVE_SLEEP"] = str(save_sleep)
    return subprocess.Popen(
        [sys.executable, "-c", _START_CODE, str(root), str(run_root)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=str(_repo_path()),
    )


def _finish(proc: subprocess.Popen) -> dict:
    stdout, stderr = proc.communicate(timeout=10)
    assert proc.returncode == 0, stderr
    return json.loads(stdout.splitlines()[-1])


def _router_actions(run_root: Path) -> list[list[str]]:
    path = run_root / "index-router-jobs" / "calls.jsonl"
    return [json.loads(line)["argv"][:2]
            for line in path.read_text(encoding="utf-8").splitlines()]


_START_CODE = r"""
import importlib
import json
import os
import sys
import time
from harness import index_jobs

try:
    target = importlib.import_module("harness.index_job_registry")
except ModuleNotFoundError:
    target = index_jobs

if hasattr(target, "_save_registry"):
    original = target._save_registry

    def delayed_save(*args, **kwargs):
        sleep = float(os.environ.get("FAKE_SAVE_SLEEP", "0"))
        if sleep:
            time.sleep(sleep)
        return original(*args, **kwargs)

    target._save_registry = delayed_save

print(json.dumps(index_jobs.start_workspace_map(sys.argv[1],
                                                run_root=sys.argv[2])))
"""


_FAKE_INDEX = r"""
import hashlib
import json
import os
import pathlib
import sys
import time

job_root = pathlib.Path(os.environ["INDEX_ROUTER_JOB_DIR"])
job_root.mkdir(parents=True, exist_ok=True)
calls = job_root / "calls.jsonl"
with calls.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps({"argv": sys.argv[1:]}) + "\n")

if sys.argv[1:] == ["--version"]:
    print("index 2.12.0")
elif sys.argv[1:3] == ["router-job", "--help"]:
    print("router-job help")
elif sys.argv[1:3] == ["router-job", "start"]:
    root = sys.argv[sys.argv.index("--root") + 1]
    job_id = "job-" + hashlib.sha256(root.encode()).hexdigest()[:12]
    time.sleep(float(os.environ.get("FAKE_INDEX_START_SLEEP", "0")))
    job_dir = job_root / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    status = {
        "schema": "index.router-job-status/v1",
        "job_id": job_id,
        "root": root,
        "root_sha256_prefix": hashlib.sha256(root.encode()).hexdigest()[:16],
        "status": "running",
        "phase": "building",
        "completed_repos": 1,
        "total_repos": 2,
        "result_available": False,
        "result_sha256": None,
        "error_type": None,
        "message": None,
        "job_dir": str(job_dir),
    }
    (job_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
    print(json.dumps(status))
elif sys.argv[1:3] == ["router-job", "status"]:
    status_path = job_root / sys.argv[3] / "status.json"
    print(status_path.read_text(encoding="utf-8"))
else:
    raise SystemExit(9)
"""
