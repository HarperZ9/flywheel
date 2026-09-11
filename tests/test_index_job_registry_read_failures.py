"""Index workspace-map registry read failures fail closed."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness import index_jobs
from harness.index_job_registry import SCHEMA, registry_path


@pytest.mark.parametrize("exc_type", [PermissionError, OSError])
def test_registry_read_error_fails_commit_without_replacing_existing_bytes(
        tmp_path, monkeypatch, exc_type):
    root = tmp_path / "repo"
    root.mkdir()
    run_root = tmp_path / "run"
    path = registry_path(run_root)
    path.parent.mkdir(parents=True)
    path.write_bytes(_valid_registry_bytes({
        str((tmp_path / "prior").resolve()): {
            "root": str((tmp_path / "prior").resolve()),
            "job_id": "job-prior",
            "root_sha256_prefix": "priorhash",
            "status": "running",
            "phase": "building",
        },
    }))
    before = path.read_bytes()
    calls: list[tuple[str, str, tuple[str, ...]]] = []
    _patch_registry_read_text_failure(monkeypatch, path, exc_type)
    monkeypatch.setattr(index_jobs, "_run", _fake_run(calls))

    out = index_jobs.start_workspace_map(root, run_root=run_root)

    assert out["status"] == "failed"
    assert out["error_type"] == "INDEX_REGISTRY_COMMIT_FAILED"
    assert out["job_id"] == ""
    assert calls == []
    assert path.read_bytes() == before


@pytest.mark.parametrize("existing_bytes", [
    b'{"schema":"flywheel.index-workspace-map-job/v1","roots":',
    b'["not","a","registry"]',
    b'{"schema":"flywheel.index-workspace-map-job/v1","roots":[]}',
])
def test_malformed_existing_registry_fails_commit_without_starting_or_rewriting(
        tmp_path, monkeypatch, existing_bytes):
    root = tmp_path / "repo"
    root.mkdir()
    run_root = tmp_path / "run"
    path = registry_path(run_root)
    path.parent.mkdir(parents=True)
    path.write_bytes(existing_bytes)
    before = path.read_bytes()
    calls: list[tuple[str, str, tuple[str, ...]]] = []
    monkeypatch.setattr(index_jobs, "_run", _fake_run(calls))

    out = index_jobs.start_workspace_map(root, run_root=run_root)

    assert out["status"] == "failed"
    assert out["error_type"] == "INDEX_REGISTRY_COMMIT_FAILED"
    assert out["job_id"] == ""
    assert calls == []
    assert path.read_bytes() == before


@pytest.mark.parametrize("action", [
    index_jobs.workspace_map_status,
    index_jobs.workspace_map_result,
    index_jobs.workspace_map_cancel,
    index_jobs.workspace_map_resume,
])
@pytest.mark.parametrize("registry_break", ["read_error", "invalid_roots"])
def test_workspace_map_actions_fail_commit_without_router_or_rewrite(
        tmp_path, monkeypatch, action, registry_break):
    root = tmp_path / "repo"
    root.mkdir()
    run_root = tmp_path / "run"
    path = registry_path(run_root)
    path.parent.mkdir(parents=True)
    path.write_bytes(_valid_registry_bytes({
        str(root.resolve()): {
            "root": str(root.resolve()),
            "job_id": "job-existing",
            "root_sha256_prefix": "rootabc123456789",
            "status": "running",
            "phase": "building",
        },
    }))
    if registry_break == "invalid_roots":
        path.write_bytes(
            b'{"schema":"flywheel.index-workspace-map-job/v1","roots":[]}')
    before = path.read_bytes()
    if registry_break == "read_error":
        _patch_registry_read_text_failure(monkeypatch, path, OSError)
    calls: list[tuple[str, str, tuple[str, ...]]] = []
    monkeypatch.setattr(index_jobs, "_run", _fake_run(calls))

    out = action(root, run_root=run_root)

    assert out["status"] == "failed"
    assert out["error_type"] == "INDEX_REGISTRY_COMMIT_FAILED"
    assert out["job_id"] == ""
    assert calls == []
    assert path.read_bytes() == before


def test_missing_registry_file_still_initializes_workspace_map_job(
        tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    run_root = tmp_path / "run"
    path = registry_path(run_root)
    calls: list[tuple[str, str, tuple[str, ...]]] = []
    monkeypatch.setattr(index_jobs, "_run", _fake_run(calls))

    out = index_jobs.start_workspace_map(root, run_root=run_root)

    root_s = str(root.resolve())
    assert out["status"] == "running"
    assert out["error_type"] is None
    assert out["job_id"] == "job-1"
    assert calls == [("start", root_s, (
        "--root", root_s, "--max-docs", "500", "--budget-ms", "0",
    ))]
    registry = json.loads(path.read_text(encoding="utf-8"))
    assert set(registry["roots"]) == {root_s}
    assert registry["roots"][root_s]["job_id"] == "job-1"


def test_starting_second_root_preserves_existing_registry_row(
        tmp_path, monkeypatch):
    prior_root = tmp_path / "prior"
    new_root = tmp_path / "new"
    prior_root.mkdir()
    new_root.mkdir()
    run_root = tmp_path / "run"
    path = registry_path(run_root)
    prior_root_s = str(prior_root.resolve())
    new_root_s = str(new_root.resolve())
    prior_row = {
        "root": prior_root_s,
        "job_id": "job-prior",
        "root_sha256_prefix": "priorhash",
        "status": "running",
        "phase": "building",
        "retained_field": "keep-me",
    }
    path.parent.mkdir(parents=True)
    path.write_bytes(_valid_registry_bytes({prior_root_s: prior_row}))
    calls: list[tuple[str, str, tuple[str, ...]]] = []
    monkeypatch.setattr(index_jobs, "_run", _fake_run(calls))

    out = index_jobs.start_workspace_map(new_root, run_root=run_root)

    registry = json.loads(path.read_text(encoding="utf-8"))
    assert out["status"] == "running"
    assert out["job_id"] == "job-1"
    assert set(registry["roots"]) == {prior_root_s, new_root_s}
    assert registry["roots"][prior_root_s] == prior_row
    assert registry["roots"][new_root_s]["job_id"] == "job-1"
    assert calls == [("start", new_root_s, (
        "--root", new_root_s, "--max-docs", "500", "--budget-ms", "0",
    ))]


def _valid_registry_bytes(rows: dict[str, dict[str, object]]) -> bytes:
    return json.dumps({"schema": SCHEMA, "roots": rows},
                      indent=1, sort_keys=True).encode("utf-8")


def _patch_registry_read_text_failure(monkeypatch, target: Path,
                                      exc_type: type[OSError]) -> None:
    original = type(target).read_text

    def read_text(self, *args, **kwargs):
        if Path(self) == target:
            raise exc_type("blocked registry read")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(type(target), "read_text", read_text)


def _fake_run(calls: list[tuple[str, str, tuple[str, ...]]]):
    def run(action: str, root: str, _run_root: Path | str,
            args: list[str]) -> dict[str, object]:
        calls.append((action, root, tuple(args)))
        return {
            "schema": "index.router-job-status/v1",
            "job_id": f"job-{len(calls)}",
            "root": root,
            "root_sha256_prefix": "rootabc123456789",
            "status": "running",
            "phase": "building",
            "completed_repos": 1,
            "total_repos": 2,
            "result_available": False,
            "result_sha256": None,
            "error_type": None,
            "message": None,
        }

    return run
