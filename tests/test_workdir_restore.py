"""workdir_restore puts a workdir back byte for byte and never acts outside it.

Success criteria:
  - a file or directory the run added is removed, a file it changed, removed
    or retyped is written back, and a mode it changed is set back.
  - a workdir the run deleted whole is rebuilt.
  - a hard link planted in place of a task file is replaced, and the file it
    points at outside the workdir is not written.
  - a directory link the run created to a place outside the workdir is removed
    as a link, and nothing behind it is deleted. On Windows the link is a
    junction, which os.walk enters even with followlinks=False.
  - a task-supplied link the run removed raises WorkdirRestoreError rather
    than leaving the next run a different workdir without saying so.
"""
import os
import shutil
import stat
from pathlib import Path

import pytest

from harness.workdir_restore import WorkdirRestoreError, restore, snapshot


def _tree(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): (p.read_bytes() if p.is_file() else None)
            for p in sorted(root.rglob("*"))}


def _task_dir(tmp_path: Path) -> Path:
    root = tmp_path / "w"
    (root / "pkg").mkdir(parents=True)
    (root / "hidden_test.py").write_bytes(b"def test_a():\n    assert True\n")
    (root / "pkg" / "cases.json").write_bytes(b"[1, 2, 3]\n")
    (root / "solution.py").write_bytes(b"def f():\n    return 1\n")
    return root


def _dir_link(link: Path, target: Path) -> None:
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def test_added_changed_removed_and_retyped_entries_go_back(tmp_path):
    root = _task_dir(tmp_path)
    before, snap = _tree(root), snapshot(root)
    (root / "conftest.py").write_text("def pytest_configure(config):\n    pass\n")
    (root / "deep" / "er").mkdir(parents=True)
    (root / "deep" / "er" / "x.py").write_text("x = 1\n")
    (root / "hidden_test.py").write_text("def test_ok():\n    pass\n")
    (root / "solution.py").unlink()
    shutil.rmtree(root / "pkg")
    (root / "pkg").write_text("a file where a directory was\n")
    restore(snap)
    assert _tree(root) == before


def test_a_read_only_plant_is_removed_and_a_mode_change_is_undone(tmp_path):
    root = _task_dir(tmp_path)
    test_file = root / "hidden_test.py"
    before_mode = stat.S_IMODE(test_file.stat().st_mode)
    before, snap = _tree(root), snapshot(root)
    (root / "conftest.py").write_text("x = 1\n")
    os.chmod(root / "conftest.py", stat.S_IREAD)
    os.chmod(test_file, stat.S_IREAD)
    restore(snap)
    assert _tree(root) == before
    assert stat.S_IMODE(test_file.stat().st_mode) == before_mode


def test_a_workdir_deleted_whole_is_rebuilt(tmp_path):
    root = _task_dir(tmp_path)
    before, snap = _tree(root), snapshot(root)
    shutil.rmtree(root)
    restore(snap)
    assert _tree(root) == before


def test_a_planted_hard_link_is_replaced_not_written_through(tmp_path):
    root = _task_dir(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"not the task's file\n")
    before, snap = _tree(root), snapshot(root)
    (root / "hidden_test.py").unlink()
    os.link(outside, root / "hidden_test.py")
    restore(snap)
    assert _tree(root) == before
    assert outside.read_bytes() == b"not the task's file\n"


def test_a_directory_link_to_outside_is_removed_as_a_link(tmp_path):
    root = _task_dir(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_bytes(b"outside the workdir\n")
    before, snap = _tree(root), snapshot(root)
    _dir_link(root / "escape", outside)
    shutil.rmtree(root / "pkg")
    _dir_link(root / "pkg", outside)
    restore(snap)
    assert _tree(root) == before
    assert (outside / "keep.txt").read_bytes() == b"outside the workdir\n"
    assert sorted(p.name for p in outside.iterdir()) == ["keep.txt"]


def test_a_removed_task_link_raises(tmp_path):
    root = _task_dir(tmp_path)
    shared = tmp_path / "shared"
    shared.mkdir()
    _dir_link(root / "data", shared)
    snap = snapshot(root)
    os.unlink(root / "data")
    with pytest.raises(WorkdirRestoreError, match="not recreated"):
        restore(snap)
