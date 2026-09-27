"""The frozen engine's lane worker mode for index router jobs (WP10).

index starts a router job's worker as ``[sys.executable, -m,
index_graph.router_jobs, _worker, <job_dir>, <token>]``. A frozen engine
refuses ``-m``, so the job never ran there. The frozen index child now rewrites
that one argv to ``[engine.exe, --bundled-lane-worker, index, <job_dir>,
<token>]`` (built by lane_cli), and the engine serves that mode after the same
admission as its other lane modes.
"""
from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

import pytest

from harness import lane_worker_mode as lwm

TOKEN = "0123456789abcdef0123456789abcdef"


class _Popen:
    def __init__(self):
        self.calls = []

    def __call__(self, args, *a, **kw):
        self.calls.append((list(args), kw))

        class _P:
            pid = 4242
        return _P()


@pytest.fixture
def shimmed(monkeypatch):
    """index_graph.router_jobs with the worker shim over a fake Popen."""
    import index_graph.router_jobs as rj
    fake = _Popen()
    monkeypatch.setattr(rj, "subprocess", rj.subprocess)       # restored after the test
    monkeypatch.setattr(subprocess, "Popen", fake)
    assert lwm.install_worker_spawn("index", executable="C:/F/flywheel-gateway.exe")
    return rj, fake


def test_lane_cli_builds_the_worker_argv():
    from harness.lane_cli import lane_worker_argv
    assert lane_worker_argv("index", ["D:/j", TOKEN], executable="C:/F/e.exe") == [
        "C:/F/e.exe", "--bundled-lane-worker", "index", "D:/j", TOKEN]


def test_the_shim_rewrites_only_the_index_worker_argv(shimmed, tmp_path):
    rj, fake = shimmed
    rj._spawn_worker(tmp_path, TOKEN)
    rj.subprocess.Popen(["git", "status"])
    (worker, kw), (other, _kw) = fake.calls
    assert worker == ["C:/F/flywheel-gateway.exe", "--bundled-lane-worker", "index",
                      str(tmp_path), TOKEN]
    assert kw["stdin"] == subprocess.DEVNULL and kw["close_fds"] is True
    assert other == ["git", "status"]
    assert rj.subprocess.DEVNULL == subprocess.DEVNULL


def test_installing_twice_keeps_one_shim(shimmed):
    rj, _fake = shimmed
    first = rj.subprocess
    assert lwm.install_worker_spawn("index")
    assert rj.subprocess is first


def test_only_index_has_a_worker():
    assert lwm.install_worker_spawn("gather") is False
    assert lwm.dispatch_bundled_lane_worker(["--bundled-lane-worker", "gather", "x", TOKEN]) == 2


@pytest.fixture
def job_root(monkeypatch, tmp_path):
    root = tmp_path / "router-jobs"
    job = root / str(uuid.uuid4())
    job.mkdir(parents=True)
    monkeypatch.setenv("INDEX_ROUTER_JOB_DIR", str(root))
    ran, admitted = [], []

    class _Admission:
        blocking_codes = ()

    def admit(lane, **_kw):
        admitted.append(lane)
        return _Admission()

    import index_graph.router_jobs as rj
    monkeypatch.setattr(lwm, "admit_bundled_lane", admit)
    monkeypatch.setattr(rj, "run_router_job_worker",
                        lambda job_dir, token: ran.append((Path(job_dir), token)) or 0)
    return job, ran, admitted


def test_the_worker_mode_runs_index_s_worker_after_admission(job_root):
    job, ran, admitted = job_root
    assert lwm.dispatch_bundled_lane_worker(
        ["--bundled-lane-worker", "index", str(job), TOKEN]) == 0
    assert admitted == ["index"] and ran == [(job.resolve(), TOKEN)]


@pytest.mark.parametrize("make", [
    lambda job: ["--bundled-lane-worker"],
    lambda job: ["--bundled-lane-worker", "index", str(job)],
    lambda job: ["--bundled-lane-worker", "index", str(job), TOKEN, "x"],
    lambda job: ["--bundled-lane-worker", "index", str(job), "not-hex"],
    lambda job: ["--bundled-lane-worker", "index", "relative/job", TOKEN],
    lambda job: ["--bundled-lane-worker", "index", str(job.parent), TOKEN],
    lambda job: ["--bundled-lane-worker", "index", str(job.parent.parent), TOKEN],
    lambda job: ["--bundled-lane-worker", "index", str(job / "missing"), TOKEN],
])
def test_a_malformed_or_foreign_worker_argv_is_refused_before_admission(job_root, make):
    job, ran, admitted = job_root
    assert lwm.dispatch_bundled_lane_worker(make(job)) == 2
    assert admitted == [] and ran == []


def test_a_job_folder_outside_the_job_root_is_refused(job_root, tmp_path):
    _job, ran, admitted = job_root
    other = tmp_path / "elsewhere" / str(uuid.uuid4())
    other.mkdir(parents=True)
    assert lwm.dispatch_bundled_lane_worker(
        ["--bundled-lane-worker", "index", str(other), TOKEN]) == 2
    assert admitted == [] and ran == []


def test_other_argv_is_not_this_mode():
    assert lwm.dispatch_bundled_lane_worker([]) is None
    assert lwm.dispatch_bundled_lane_worker(["--port", "1"]) is None


def test_the_frozen_entry_serves_the_worker_mode(monkeypatch):
    import importlib.util
    path = Path(__file__).resolve().parents[1] / "packaging" / "gateway_entry.py"
    spec = importlib.util.spec_from_file_location("gateway_entry_worker_test", path)
    gateway_entry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gateway_entry)
    seen = []
    monkeypatch.setattr(lwm, "dispatch_bundled_lane_worker",
                        lambda argv: seen.append(argv) or 0)
    assert gateway_entry.main(["--bundled-lane-worker", "index", "j", TOKEN]) == 0
    assert seen == [["--bundled-lane-worker", "index", "j", TOKEN]]


@pytest.mark.parametrize("dispatch,argv", [
    ("mcp", ["--bundled-lane-mcp", "index"]),
    ("cli", ["--bundled-lane-cli", "index", "router-job", "status", "--job-id", "j"]),
])
def test_the_frozen_index_modes_install_the_worker_shim(monkeypatch, dispatch, argv):
    installed = []
    monkeypatch.setattr(lwm, "install_worker_spawn", lambda lane, **_k: installed.append(lane))
    if dispatch == "mcp":
        from harness import bundled_lane_admission as bla

        class _Adm:
            blocking_codes = ()

        class _Mod:
            @staticmethod
            def serve():
                return 0

        monkeypatch.setattr(bla, "admit_bundled_lane", lambda *a, **k: _Adm())
        assert bla.dispatch_bundled_lane_mcp(argv, import_module_fn=lambda m: _Mod,
                                             expected={"module": "m", "callable": "serve"}) == 0
    else:
        from harness import frozen_lane_modes as flm

        class _Adm:
            blocking_codes = ()

        monkeypatch.setattr(flm, "admit_bundled_lane", lambda *a, **k: _Adm())
        monkeypatch.setattr(flm, "importlib", type("I", (), {"import_module": staticmethod(
            lambda name: type("M", (), {"main": staticmethod(lambda args: 0)}))}))
        assert flm.dispatch_bundled_lane_cli(argv) == 0
    assert installed == ["index"]
