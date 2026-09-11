"""Controlled admission helper tests for registry contention subprocesses."""
from __future__ import annotations

from pathlib import Path

import pytest

import harness.index_job_registry as registry
import harness.journey_lock as journey_lock
from tests import index_job_concurrency_admission as admission
from tests.index_job_concurrency_admission import (
    AdmissionPreconditionError,
    FIRST_SAVE_READY_TEXT,
    SECOND_CONTENTION_TEXT,
    install_admission,
    marker_paths,
)


def test_first_save_waits_for_second_contention_before_delegating(
        tmp_path, monkeypatch):
    run_root = tmp_path / "run"
    rows = {"root": {"job_id": "job-1"}}
    saves: list[tuple[Path, dict[str, dict[str, str]]]] = []

    def original_save(run_root_arg, rows_arg):
        saves.append((Path(run_root_arg), dict(rows_arg)))

    monkeypatch.setattr(registry, "_save_registry", original_save)
    markers = marker_paths(run_root)
    reads: list[Path] = []

    def read_marker(path: Path) -> str:
        reads.append(path)
        assert markers.first_save_ready.read_text(
            encoding="utf-8") == FIRST_SAVE_READY_TEXT
        markers.second_contention.write_text(
            SECOND_CONTENTION_TEXT, encoding="utf-8")
        return markers.second_contention.read_text(encoding="utf-8")

    install_admission(run_root, "first", timeout_s=1.0, poll_s=0.0,
                      read_text=read_marker)

    registry._save_registry(run_root, rows)

    assert reads == [markers.second_contention]
    assert saves == [(run_root, rows)]


@pytest.mark.parametrize("read_error", [FileNotFoundError, PermissionError])
def test_first_save_fails_precondition_without_second_contention(
        tmp_path, monkeypatch, read_error):
    run_root = tmp_path / "run"
    saves = []
    missing_reads: list[Path] = []
    sleeps: list[float] = []

    def original_save(run_root_arg, rows_arg):
        saves.append((run_root_arg, rows_arg))

    def missing_marker(path: Path) -> str:
        missing_reads.append(path)
        raise read_error(path)

    monkeypatch.setattr(registry, "_save_registry", original_save)
    markers = marker_paths(run_root)
    install_admission(run_root, "first", timeout_s=0.0, poll_s=1.0,
                      read_text=missing_marker, sleep=sleeps.append)

    with pytest.raises(AdmissionPreconditionError,
                       match="second-contention"):
        registry._save_registry(run_root, {})

    assert markers.first_save_ready.read_text(
        encoding="utf-8") == FIRST_SAVE_READY_TEXT
    assert missing_reads == [markers.second_contention]
    assert sleeps == []
    assert saves == []


def test_first_save_preserves_original_save_errors(tmp_path, monkeypatch):
    class SaveFailed(RuntimeError):
        pass

    run_root = tmp_path / "run"
    markers = marker_paths(run_root)
    markers.second_contention.parent.mkdir(parents=True)
    markers.second_contention.write_text(
        SECOND_CONTENTION_TEXT, encoding="utf-8")

    def original_save(run_root_arg, rows_arg):
        raise SaveFailed("save failed")

    monkeypatch.setattr(registry, "_save_registry", original_save)
    install_admission(run_root, "first", timeout_s=1.0, poll_s=0.0)

    with pytest.raises(SaveFailed, match="save failed"):
        registry._save_registry(run_root, {})


def test_second_try_lock_marks_only_after_real_false(tmp_path, monkeypatch):
    run_root = tmp_path / "run"
    lock_path = registry._lock_path(run_root)
    lock_path.parent.mkdir(parents=True)
    outcomes = [True, False, False]
    tried: list[Path] = []
    writes = []
    original_write = admission._write_marker

    def write_marker(path, text):
        writes.append(path)
        original_write(path, text)

    monkeypatch.setattr(admission, "_write_marker", write_marker)

    def original_try_lock(stream):
        tried.append(Path(stream.name))
        return outcomes.pop(0)

    monkeypatch.setattr(journey_lock, "_try_lock", original_try_lock)
    markers = marker_paths(run_root)
    install_admission(run_root, "second")

    with lock_path.open("a+b") as stream:
        assert journey_lock._try_lock(stream) is True
        assert not markers.second_contention.exists()
        assert journey_lock._try_lock(stream) is False
        assert journey_lock._try_lock(stream) is False

    assert markers.second_contention.read_text(
        encoding="utf-8") == SECOND_CONTENTION_TEXT
    assert tried == [lock_path, lock_path, lock_path]
    assert writes == [markers.second_contention]


def test_transient_marker_permission_error_requires_later_valid_content(
        tmp_path, monkeypatch):
    saves, reads, sleeps = [], [], []
    monkeypatch.setattr(registry, "_save_registry", lambda *args: saves.append(args))

    def read_marker(path):
        reads.append(path)
        if len(reads) == 1:
            raise PermissionError("synthetic marker sharing error")
        return SECOND_CONTENTION_TEXT

    install_admission(tmp_path, "first", timeout_s=1, poll_s=0,
                      read_text=read_marker, sleep=sleeps.append)
    registry._save_registry(tmp_path, {})
    assert reads == [marker_paths(tmp_path).second_contention] * 2
    assert sleeps == [0]
    assert saves == [(tmp_path, {})]


def test_second_try_lock_preserves_original_errors(tmp_path, monkeypatch):
    class LockFailed(RuntimeError):
        pass

    run_root = tmp_path / "run"
    lock_path = registry._lock_path(run_root)
    lock_path.parent.mkdir(parents=True)

    def original_try_lock(stream):
        raise LockFailed("lock failed")

    monkeypatch.setattr(journey_lock, "_try_lock", original_try_lock)
    markers = marker_paths(run_root)
    install_admission(run_root, "second")

    with lock_path.open("a+b") as stream:
        with pytest.raises(LockFailed, match="lock failed"):
            journey_lock._try_lock(stream)

    assert not markers.second_contention.exists()


def test_controlled_admission_keeps_real_two_second_busy_boundary(
        tmp_path, text_once_written):
    import json
    from harness import index_jobs
    from tests.test_projects_index_job_concurrency import (
        _contending_outputs, _install_fake_index, _router_actions)

    roots = [tmp_path / 'a', tmp_path / 'b']
    for root in roots:
        root.mkdir()
    run_root = tmp_path / 'run'
    assert index_jobs.DEFAULT_LOCK_TIMEOUT_S == 2
    outputs = _contending_outputs(roots, run_root, _install_fake_index(tmp_path),
                                 text_once_written, save_sleep=2.5)
    evidence = [output['_process'] for output in outputs]
    assert outputs[0]['error_type'] is None, evidence
    assert outputs[1]['error_type'] == 'INDEX_REGISTRY_BUSY', evidence
    assert outputs[1]['job_id'] == '', evidence
    rows = json.loads(registry.registry_path(run_root).read_text(encoding='utf-8'))['roots']
    assert set(rows) == {str(roots[0].resolve())}, evidence
    assert _router_actions(run_root).count(['router-job', 'start']) == 1
