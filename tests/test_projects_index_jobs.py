"""Projects Index workspace-map jobs bind root, registry, and result state."""
from __future__ import annotations

import json
import sys

from harness import index_jobs


def _install_fake_cli(tmp_path, monkeypatch):
    script = tmp_path / "fake_index.py"
    script.write_text(
        "\n".join([
            "import json, os, pathlib, sys",
            "root_dir = pathlib.Path(os.environ['INDEX_ROUTER_JOB_DIR'])",
            "root_dir.mkdir(parents=True, exist_ok=True)",
            "calls = root_dir / 'calls.jsonl'",
            "calls.open('a', encoding='utf-8').write(json.dumps({",
            "    'argv': sys.argv[1:],",
            "    'job_dir': os.environ.get('INDEX_ROUTER_JOB_DIR')",
            "}) + '\\n')",
            "if sys.argv[1:] == ['--version']:",
            "    print('index 2.12.0')",
            "elif sys.argv[1:3] == ['router-job', '--help']:",
            "    print('router-job help')",
            "elif sys.argv[1:3] == ['router-job', 'start']:",
            "    root = sys.argv[sys.argv.index('--root') + 1]",
            "    print(json.dumps({",
            "        'schema': 'index.router-job-status/v1',",
            "        'job_id': 'job-a', 'root': root,",
            "        'root_sha256_prefix': 'rootabc123456789',",
            "        'status': 'running', 'phase': 'building',",
            "        'completed_repos': 1, 'total_repos': 2,",
            "        'result_available': False, 'result_sha256': None,",
            "        'error_type': None, 'message': None,",
            "        'job_dir': str(root_dir / 'job-a')",
            "    }))",
            "elif sys.argv[1:3] == ['router-job', 'status']:",
            "    print(json.dumps({",
            "        'schema': 'index.router-job-status/v1',",
            "        'job_id': sys.argv[3],",
            "        'root': os.environ['FAKE_INDEX_ROOT'],",
            "        'root_sha256_prefix': 'rootabc123456789',",
            "        'status': os.environ.get('FAKE_INDEX_STATUS', 'running'),",
            "        'phase': os.environ.get('FAKE_INDEX_PHASE', 'building'),",
            "        'completed_repos': 1, 'total_repos': 2,",
            "        'result_available': False, 'result_sha256': None,",
            "        'error_type': None, 'message': None,",
            "        'job_dir': str(root_dir / sys.argv[3])",
            "    }))",
            "elif sys.argv[1:3] == ['router-job', 'result']:",
            "    complete = os.environ.get('FAKE_INDEX_STATUS') == 'complete'",
            "    status = {",
            "        'schema': 'index.router-job-status/v1',",
            "        'job_id': sys.argv[3],",
            "        'root': os.environ['FAKE_INDEX_ROOT'],",
            "        'root_sha256_prefix': 'rootabc123456789',",
            "        'status': 'complete' if complete else 'running',",
            "        'phase': 'complete' if complete else 'building',",
            "        'completed_repos': 2 if complete else 1,",
            "        'total_repos': 2,",
            "        'result_available': complete,",
            "        'result_sha256': 'a' * 64 if complete else None,",
            "        'error_type': None, 'message': None,",
            "        'job_dir': str(root_dir / sys.argv[3])",
            "    }",
            "    print(json.dumps({",
            "        'schema': 'index.router-job-result/v1',",
            "        'job_id': sys.argv[3],",
            "        'status': status['status'], 'phase': status['phase'],",
            "        'result_available': complete,",
            "        'result_sha256': 'a' * 64 if complete else None,",
            "        'content': 'router content' if complete else None,",
            "        'status_receipt': status",
            "    }))",
            "elif sys.argv[1:3] == ['router-job', 'cancel']:",
            "    print(json.dumps({**{",
            "        'schema': 'index.router-job-status/v1',",
            "        'job_id': sys.argv[3],",
            "        'root': os.environ['FAKE_INDEX_ROOT'],",
            "        'root_sha256_prefix': 'rootabc123456789',",
            "        'status': 'cancellation_requested',",
            "        'phase': 'building', 'completed_repos': 1,",
            "        'total_repos': 2, 'result_available': False,",
            "        'result_sha256': None, 'error_type': None,",
            "        'message': 'router job cancellation requested'",
            "    }, 'job_dir': str(root_dir / sys.argv[3])}))",
            "elif sys.argv[1:3] == ['router-job', 'resume']:",
            "    print(json.dumps({**{",
            "        'schema': 'index.router-job-status/v1',",
            "        'job_id': sys.argv[3],",
            "        'root': os.environ['FAKE_INDEX_ROOT'],",
            "        'root_sha256_prefix': 'rootabc123456789',",
            "        'status': 'running', 'phase': 'restarting',",
            "        'completed_repos': 0, 'total_repos': 2,",
            "        'result_available': False, 'result_sha256': None,",
            "        'error_type': None, 'message': None",
            "    }, 'job_dir': str(root_dir / sys.argv[3])}))",
            "else:",
            "    raise SystemExit(9)",
        ]),
        encoding="utf-8",
    )
    monkeypatch.setattr(index_jobs, "_index_argv",
                        lambda: [sys.executable, str(script)])
    return script


def _write_old_cli(tmp_path):
    script = tmp_path / "old_index.py"
    script.write_text(
        "import sys\n"
        "if sys.argv[1:] == ['--version']:\n"
        "    print('index 2.11.0')\n"
        "elif sys.argv[1:3] == ['router-job', '--help']:\n"
        "    print('router-job help')\n"
        "else:\n"
        "    raise SystemExit(9)\n",
        encoding="utf-8",
    )
    return script


def test_workspace_map_start_uses_private_job_dir_and_budget_zero(
        tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    run_root = tmp_path / "run"
    _install_fake_cli(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_INDEX_ROOT", str(root.resolve()))

    out = index_jobs.start_workspace_map(root, run_root=run_root,
                                         max_docs=17, no_cache=True)

    assert out["schema"] == index_jobs.SCHEMA
    assert out["job_id"] == "job-a"
    assert out["status"] == "running"
    assert "job_dir" not in json.dumps(out)
    calls = (run_root / "index-router-jobs" / "calls.jsonl").read_text(
        encoding="utf-8").splitlines()
    start = json.loads(calls[-1])
    assert start["argv"] == [
        "router-job", "start", "--root", str(root.resolve()),
        "--max-docs", "17", "--budget-ms", "0", "--no-cache",
    ]
    assert start["job_dir"].startswith(str(run_root))


def test_workspace_map_uses_module_fallback_when_console_is_old(
        tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    run_root = tmp_path / "run"
    old = _write_old_cli(tmp_path)
    module = _install_fake_cli(tmp_path, monkeypatch)
    monkeypatch.setattr(index_jobs, "_index_argv",
                        lambda: [sys.executable, str(old)])
    monkeypatch.setattr(index_jobs, "_module_argv",
                        lambda: [sys.executable, str(module)])
    monkeypatch.setenv("FAKE_INDEX_ROOT", str(root.resolve()))

    out = index_jobs.start_workspace_map(root, run_root=run_root)

    assert out["job_id"] == "job-a"
    calls = (run_root / "index-router-jobs" / "calls.jsonl").read_text(
        encoding="utf-8")
    assert '"router-job", "start"' in calls


def test_workspace_map_lifecycle_and_result_gating(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    run_root = tmp_path / "run"
    _install_fake_cli(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_INDEX_ROOT", str(root.resolve()))
    index_jobs.start_workspace_map(root, run_root=run_root)

    status = index_jobs.workspace_map_status(root, run_root=run_root)
    assert (status["phase"], status["completed_repos"], status["total_repos"]) == (
        "building", 1, 2)

    pending = index_jobs.workspace_map_result(root, run_root=run_root)
    assert pending["result_available"] is False
    assert "content" not in pending

    monkeypatch.setenv("FAKE_INDEX_STATUS", "complete")
    complete = index_jobs.workspace_map_result(root, run_root=run_root)
    assert complete["result_available"] is True
    assert complete["content"] == "router content"

    cancel = index_jobs.workspace_map_cancel(root, run_root=run_root)
    assert cancel["status"] == "cancellation_requested"

    resume = index_jobs.workspace_map_resume(root, run_root=run_root)
    assert resume["phase"] == "restarting"


def test_workspace_map_start_attaches_existing_active_job(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    run_root = tmp_path / "run"
    _install_fake_cli(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_INDEX_ROOT", str(root.resolve()))

    first = index_jobs.start_workspace_map(root, run_root=run_root)
    second = index_jobs.start_workspace_map(root, run_root=run_root)

    assert second["job_id"] == first["job_id"]
    calls = (run_root / "index-router-jobs" / "calls.jsonl").read_text(
        encoding="utf-8").splitlines()
    starts = [json.loads(line)["argv"][:2] for line in calls]
    assert starts.count(["router-job", "start"]) == 1


def test_workspace_map_same_root_guard_refuses_cross_root_job(
        tmp_path, monkeypatch):
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    run_root = tmp_path / "run"
    _install_fake_cli(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_INDEX_ROOT", str(root_a.resolve()))
    started = index_jobs.start_workspace_map(root_a, run_root=run_root)

    out = index_jobs.workspace_map_status(
        root_b, run_root=run_root, job_id=started["job_id"])

    assert out["status"] == "failed"
    assert out["error_type"] == "UNKNOWN_JOB_FOR_ROOT"
    assert str(root_a) not in json.dumps(out)


def test_workspace_map_recovery_failed_status_passes_without_pending_forever(
        tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    run_root = tmp_path / "run"
    _install_fake_cli(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_INDEX_ROOT", str(root.resolve()))
    index_jobs.start_workspace_map(root, run_root=run_root)
    monkeypatch.setenv("FAKE_INDEX_STATUS", "failed")
    monkeypatch.setenv("FAKE_INDEX_PHASE", "failed")

    out = index_jobs.workspace_map_status(root, run_root=run_root)

    assert out["status"] == "failed"
    assert out["phase"] == "failed"
    assert out["result_available"] is False


def test_workspace_map_start_reports_unavailable_engine(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setattr(index_jobs, "_index_argv", lambda: None)
    monkeypatch.setattr(index_jobs, "_module_argv", lambda: None)
    def no_subprocess(*_args, **_kwargs):
        raise AssertionError("missing engine must not launch a subprocess")

    monkeypatch.setattr(index_jobs.subprocess, "run", no_subprocess)

    out = index_jobs.start_workspace_map(root, run_root=tmp_path / "run")

    assert out["status"] == "failed"
    assert out["error_type"] == "INDEX_UNAVAILABLE"
    assert "index-graph" in out["message"]
