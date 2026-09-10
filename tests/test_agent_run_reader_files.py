"""No private file access: all unsafe targets are synthetic fixtures."""
from contextlib import contextmanager
import json
import os
import subprocess

import pytest

from harness import agent_run_reader as reader
from harness.eval_store import save_agent_run
from harness.private_artifact_fs import PrivateArtifactError


@pytest.mark.parametrize("bad", [None, 12, "../outside", "C:\\outside", "0" * 15, "0" * 17, "0" * 16 + "\n"])
def test_invalid_id_does_not_open_root(monkeypatch, tmp_path, bad):
    monkeypatch.setattr(reader, "open_artifact_root", lambda *_a, **_k: pytest.fail("opened invalid id"))
    assert reader.agent_run_detail(tmp_path, bad)["error"]["code"] == "INVALID_REQUEST"


def test_unsafe_or_unavailable_reader_has_no_path_fallback(monkeypatch, tmp_path):
    saved = save_agent_run(tmp_path, {"final": "INSIDE_FIXTURE"})
    def unavailable(*_args, **_kwargs):
        raise PrivateArtifactError("UNSUPPORTED_FS", "PRIVATE_PATH_SENTINEL")
    monkeypatch.setattr(reader, "open_artifact_root", unavailable)
    for body in [reader.agent_run_detail(tmp_path, saved["run_id"]), reader.agent_runs(tmp_path)]:
        assert body["error"]["code"] == "UNAVAILABLE"
        assert "FIXTURE" not in json.dumps(body) and "SENTINEL" not in json.dumps(body)


def test_bounded_listing_marks_unreadable_and_skips_nonopaque_names(tmp_path):
    saved = save_agent_run(tmp_path, {"final": "retained", "goal_excerpt": "read source"})
    directory = tmp_path / "agent_runs"
    (directory / "outside-name.json").write_text('{"final":"PRIVATE_MARKER"}', encoding="utf-8")
    (directory / ("0" * 16 + ".json")).write_bytes(b"x" * (reader.MAX_RUN_BYTES + 1))
    result = reader.agent_runs(tmp_path)
    assert len(result["runs"]) == 2
    assert "PRIVATE_MARKER" not in json.dumps(result)
    good = next(row for row in result["runs"] if row["run_id"] == saved["run_id"])
    assert good["intact"] is True
    bad = next(row for row in result["runs"] if row["run_id"] == "0" * 16)
    assert bad == {"run_id": "0" * 16, "status": "UNREADABLE", "intact": False}


def test_existing_trace_benchmark_limit_remains_supported(tmp_path):
    from harness.trace_bench_route import _all_runs
    saved = save_agent_run(tmp_path, {"final": "retained fixture"})
    for limit in (100, 101, 500):
        assert any(run["run_id"] == saved["run_id"] for run in _all_runs(tmp_path, limit))


def test_leaf_symlink_cannot_disclose_outside_json(tmp_path):
    directory = tmp_path / "agent_runs"
    directory.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text('{"final":"OUTSIDE_MARKER"}', encoding="utf-8")
    leaf = directory / ("0" * 16 + ".json")
    try:
        leaf.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("file symlink creation unavailable")
    detail = reader.agent_run_detail(tmp_path, "0" * 16)
    assert detail["error"]["code"] == "UNSAFE_PATH"
    assert "OUTSIDE_MARKER" not in json.dumps(reader.agent_runs(tmp_path))


def test_reparse_run_directory_is_refused(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / ("0" * 16 + ".json")).write_text('{"final":"OUTSIDE_MARKER"}', encoding="utf-8")
    link = tmp_path / "agent_runs"
    if os.name == "nt":
        proc = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                              capture_output=True, check=False)
        if proc.returncode:
            pytest.skip("directory junction creation unavailable")
    else:
        link.symlink_to(outside, target_is_directory=True)
    try:
        for body in [reader.agent_run_detail(tmp_path, "0" * 16), reader.agent_runs(tmp_path)]:
            assert body["error"]["code"] == "UNSAFE_PATH"
            assert "OUTSIDE_MARKER" not in json.dumps(body)
    finally:
        if os.name == "nt":
            link.rmdir()
        else:
            link.unlink()


def test_root_swap_after_admission_never_reads_replacement(monkeypatch, tmp_path):
    saved = save_agent_run(tmp_path, {"final": "INSIDE_MARKER"})
    directory, old = tmp_path / "agent_runs", tmp_path / "old"
    real_open = reader.open_artifact_root
    swapped = []
    @contextmanager
    def racing_open(*args, **kwargs):
        with real_open(*args, **kwargs) as fs:
            try:
                directory.rename(old)
            except PermissionError:
                swapped.append(False)  # Windows read handles block ancestor rename.
            else:
                swapped.append(True)
                directory.mkdir()
                (directory / (saved["run_id"] + ".json")).write_text(
                    '{"final":"OUTSIDE_MARKER"}', encoding="utf-8")
            yield fs
    monkeypatch.setattr(reader, "open_artifact_root", racing_open)
    result = reader.agent_run_detail(tmp_path, saved["run_id"])
    assert "OUTSIDE_MARKER" not in json.dumps(result)
    if swapped == [True]:
        assert result["error"]["code"] == "UNSAFE_PATH"
    else:
        assert result["intact"] is True and result["final"] == "INSIDE_MARKER"
