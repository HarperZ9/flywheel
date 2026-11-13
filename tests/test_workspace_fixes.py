"""Review fixes for the writable workspace: each test fails without its fix."""
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from harness import workspace_guard as guard
from harness import workspace_marks as marks
from harness import workspace_paths, workspace_run
from harness.git_config_guard import unsafe_additions
from harness.machine_policy import Policy
from harness.workspace_run import open_workspace

WINDOWS = os.name == "nt"
HOOK = b"#!/bin/sh\nexit 0\n"


def _repo(tmp_path):
    root = tmp_path.resolve() / "proj"
    (root / ".git" / "hooks").mkdir(parents=True)
    (root / ".git" / "config").write_bytes(b"[core]\n\tbare = false\n")
    (root / ".git" / "hooks" / "pre-commit").write_bytes(HOOK)
    return root


def _open(root, **kw):
    base = root.parent
    return open_workspace(root, **{"environ": {}, "policy": Policy(), "home": base / "home",
                                   "flywheel_home": base / "state", **kw})


def test_an_interrupted_run_still_puts_guarded_paths_back(tmp_path, monkeypatch, caplog):
    import harness.sandboxed_runner as sr
    root = _repo(tmp_path)

    def interrupted(cmd, cwd, **kw):
        (root / ".git" / "hooks" / "post-merge").write_bytes(b"evil")
        raise KeyboardInterrupt
    monkeypatch.setattr(sr, "sandboxed_run", interrupted)
    with caplog.at_level(logging.WARNING), pytest.raises(KeyboardInterrupt) as caught:
        workspace_run.workspace_run("make", str(root), space=_open(root))
    assert not (root / ".git" / "hooks" / "post-merge").exists()
    assert "post-merge: added, removed" in caplog.text
    assert any("post-merge" in note for note in caught.value.__notes__)


def test_every_git_folder_under_modules_is_guarded_at_any_depth(tmp_path):
    root = _repo(tmp_path)
    modules = root / ".git" / "modules"
    for rel in ("flat", "libs/with/slash", "flat/modules/inner"):
        (modules / rel / "hooks").mkdir(parents=True)
        (modules / rel / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    before = guard.snapshot(root)
    for rel in ("flat", "libs/with/slash", "flat/modules/inner"):
        (modules / rel / "hooks" / "pre-push").write_bytes(b"evil")
        (modules / rel / "config").write_bytes(b"[core]\n\tfsmonitor = evil\n")
    problems = guard.verify(root, before)
    assert len(problems) == 6 and not problems.failed
    assert not list(modules.rglob("pre-push"))
    assert all(b"fsmonitor" not in p.read_bytes() for p in modules.rglob("config"))


def test_past_the_cap_the_project_is_read_only_with_the_reason(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    for name in ("a", "b", "c"):
        (root / ".git" / "modules" / name).mkdir(parents=True)
        (root / ".git" / "modules" / name / "HEAD").write_text("x", encoding="utf-8")
    assert _open(root).writable
    monkeypatch.setattr(workspace_paths, "MAX_GIT_DIRS", 2)
    space = _open(root)
    assert not space.writable and "more than the guard reads" in space.reason
    deep = root / ".git" / "modules" / "plain" / "1" / "2" / "3"
    deep.mkdir(parents=True)
    monkeypatch.setattr(workspace_paths, "MAX_GIT_DIRS", 128)
    monkeypatch.setattr(workspace_paths, "MAX_DEPTH", 2)
    assert workspace_paths.git_dirs(root)[1] is True


def test_a_change_that_cannot_be_undone_holds_the_project(tmp_path, caplog):
    root = _repo(tmp_path)
    space = _open(root)
    before = guard.snapshot(root)
    hook = root / ".git" / "hooks" / "pre-commit"
    hook.unlink()
    (hook / "inner").mkdir(parents=True)             # a folder that is not empty
    (hook / "inner" / "keep.sample").write_bytes(b"x")
    with caplog.at_level(logging.WARNING):
        ok, out = workspace_run.finish(space, before, True, "[exit 0]")
    assert not ok and "could not remove" in out and "[workspace closed to commands" in out
    assert "could not remove" in caplog.text
    held = _open(root)
    assert not held.writable and "could not be put back" in held.reason
    assert str(marks._file(marks.HOLDS, root, space.state)) in held.reason
    assert marks.clear_hold(root, space.state) and _open(root).writable


def test_remove_reports_failure_and_logs_it(tmp_path, caplog):
    (tmp_path / "full" / "x").mkdir(parents=True)
    with caplog.at_level(logging.WARNING):
        assert guard._remove(tmp_path / "full") is False
    assert "could not remove" in caplog.text and caplog.records[0].exc_info
    assert guard._remove(tmp_path / "absent") is True


def test_a_file_too_large_to_keep_is_reported_as_not_undone(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    monkeypatch.setattr(guard, "MAX_KEEP", 8)
    before = guard.snapshot(root)
    (root / ".git" / "hooks" / "pre-commit").write_bytes(b"#!/bin/sh\nrm -rf ~\n")
    problems = guard.verify(root, before)
    assert problems == [".git/hooks/pre-commit: changed, too large to put back"]
    assert problems.failed == list(problems)


def test_a_restored_hook_keeps_its_permission_bits(tmp_path):
    root = _repo(tmp_path)
    hook = root / ".git" / "hooks" / "pre-commit"
    mode = 0o444 if WINDOWS else 0o755               # read-only there, executable here
    os.chmod(hook, mode)
    before = guard.snapshot(root)
    os.chmod(hook, 0o666 if WINDOWS else 0o644)
    hook.write_bytes(b"#!/bin/sh\ncurl evil\n")
    assert guard.verify(root, before) == [".git/hooks/pre-commit: changed, put back"]
    assert hook.read_bytes() == HOOK and (hook.stat().st_mode & 0o777) == mode
    os.chmod(hook, 0o666 if WINDOWS else 0o644)      # content the same, mode changed
    assert guard.verify(root, before) == [".git/hooks/pre-commit: changed, put back"]
    assert (hook.stat().st_mode & 0o777) == mode
    os.chmod(hook, 0o666)


def test_a_link_is_restored_as_a_link(tmp_path):
    root = _repo(tmp_path)
    shared = root / "shared-hooks"
    shared.mkdir()
    (shared / "pre-commit").write_bytes(HOOK)
    shutil.rmtree(root / ".git" / "hooks")
    link = root / ".git" / "hooks"
    if WINDOWS:
        import _winapi
        _winapi.CreateJunction(str(shared), str(link))
    else:
        link.symlink_to(shared, target_is_directory=True)
    before = guard.snapshot(root)
    guard._remove(link)
    link.mkdir()
    problems = guard.verify(root, before)
    assert problems == [".git/hooks: link removed, put back"] and not problems.failed
    assert guard._is_link(link) and (link / "pre-commit").read_bytes() == HOOK


def test_a_case_only_rename_of_a_hook_is_the_same_hook(tmp_path):
    root = _repo(tmp_path)
    hooks = root / ".git" / "hooks"
    before = guard.snapshot(root)
    (hooks / "pre-commit").rename(hooks / "PRE-COMMIT")
    problems = guard.verify(root, before)
    if workspace_paths.FOLDS:
        assert problems == []                        # one file on this host, unchanged
    (hooks / "PRE-COMMIT").write_bytes(b"evil") if (hooks / "PRE-COMMIT").exists() else \
        (hooks / "pre-commit").rename(hooks / "PRE-COMMIT")
    (hooks / "PRE-COMMIT").write_bytes(b"evil")
    assert guard.verify(root, before) != []
    assert [p.name.lower() for p in hooks.iterdir()] == ["pre-commit"]
    assert next(hooks.iterdir()).read_bytes() == HOOK


def test_a_branch_remote_is_checked_like_an_address():
    assert unsafe_additions(b"", b'[branch "main"]\n\tremote = ext::sh -c evil\n') != []
    assert unsafe_additions(b"", b'[branch "main"]\n\tremote = -evil\n') != []
    assert unsafe_additions(b"", b'[branch "main"]\n\tremote = origin\n\tmerge = refs/heads/main\n') == []


def test_a_failed_close_holds_the_project_and_the_sweep_closes_what_was_left(tmp_path):
    from harness import windows_workspace as ww
    root, state, calls = _repo(tmp_path), tmp_path / "state", []

    def label(path, level):
        calls.append((str(path), level))

    def broken(path, level):
        raise OSError("windows error 5")
    ww._acquire(root, (), label, state=state)
    assert (str(root), "LW") in calls and len(marks.left_open(state)) == 1
    ww._close_all(label)                             # what the atexit handler runs
    assert calls[-1] == (str(root), "ME") and marks.left_open(state) == []
    ww._acquire(root, (), label, state=state)
    ww._release(root, broken)
    assert "could not close the project" in marks.hold_reason(root, state)
    assert not _open(root).writable
    marks.clear_hold(root, state)
    record = marks._file(marks.OPEN, root, state)
    record.write_text('{"root": %r, "pid": -1, "paths": [%r]}'.replace("%r", '"%s"') % (
        root.as_posix(), root.as_posix()), encoding="utf-8")
    calls.clear()
    assert ww.sweep(state, label) == 1
    assert calls == [(str(root), "ME")] and marks.left_open(state) == []


@pytest.mark.skipif(not WINDOWS, reason="integrity labels are Windows")
def test_the_runner_is_closed_even_when_the_release_raises(tmp_path, monkeypatch):
    from harness import windows_workspace as ww
    from harness.execution_input_protection import ExecutionInputProtectionUnavailable
    root, work = _repo(tmp_path), tmp_path.resolve() / "work"
    work.mkdir()
    real, seen = ww._release, {}

    def failing(source, label):
        real(source, label)
        raise RuntimeError("release failed")
    monkeypatch.setattr(ww, "_release", failing)
    with pytest.raises(ExecutionInputProtectionUnavailable):
        with ww.writable_namespace(root, work, state=tmp_path / "state") as runner:
            seen["runner"] = runner
            assert runner.token
    assert seen["runner"].token is None


@pytest.mark.skipif(not WINDOWS, reason="integrity labels are Windows")
def test_a_folder_without_full_control_runs_read_only_and_says_why(tmp_path):
    from harness.windows_label import can_label, is_low
    root = tmp_path.resolve() / "proj"
    root.mkdir()
    user = os.environ.get("USERNAME", "")
    grant = subprocess.run(["icacls", str(root), "/inheritance:r", "/grant:r", f"{user}:(OI)(CI)M"],
                           capture_output=True, text=True)
    try:
        if grant.returncode or can_label(root):
            pytest.skip("this account keeps WRITE_OWNER on a folder it has Modify on")
        assert not is_low(root)
        space = _open(root)
        assert not space.writable and "Modify and not Full control" in space.reason
        ok, out = workspace_run.workspace_run("echo hi", str(root), scratch_home=True, space=space)
        assert ok and "hi" in out and out.splitlines()[-1].startswith("[workspace read-only:")
        ok, _out = workspace_run.workspace_run("echo x> made.txt", str(root), scratch_home=True,
                                               space=space)
        assert not ok and not (root / "made.txt").exists()
    finally:
        subprocess.run(["icacls", str(root), "/reset"], capture_output=True)


def test_the_sweep_leaves_a_live_owner_alone_and_closes_a_stale_one(tmp_path):
    import json
    from harness import windows_workspace as ww
    state, calls = tmp_path / "state", []
    live, stale, reused = (tmp_path / name for name in ("live", "stale", "reused"))
    for folder in (live, stale, reused):
        folder.mkdir()
    marks.mark_open(live, [live], state)             # this process: alive, start time right
    mine = json.loads(marks._file(marks.OPEN, live, state).read_text(encoding="utf-8"))
    assert mine["pid"] == os.getpid() and mine["started"] == marks.process_started(os.getpid())
    records = {stale: {"pid": 2 ** 22 + 12345, "started": mine["started"]},      # no such process
               reused: {"pid": os.getpid(), "started": mine["started"] + 1}}     # id reused
    for folder, owner in records.items():
        marks._file(marks.OPEN, folder, state).write_text(json.dumps(
            {"root": str(folder), "paths": [str(folder)], **owner}), encoding="utf-8")
    assert ww.sweep(state, lambda path, level: calls.append((str(path), level))) == 2
    assert sorted(calls) == sorted([(str(stale), "ME"), (str(reused), "ME")])
    assert [record["root"] for _file, record in marks.left_open(state)] == [str(live)]


def test_a_hold_that_cannot_be_saved_lasts_for_the_session_and_says_so(tmp_path):
    root = _repo(tmp_path)
    state = tmp_path.resolve() / "state"
    state.mkdir()
    (state / marks.HOLDS).write_text("a file where the holds folder belongs", encoding="utf-8")
    space = _open(root)
    assert space.writable
    before = guard.snapshot(root)
    hook = root / ".git" / "hooks" / "pre-commit"
    hook.unlink()
    (hook / "inner").mkdir(parents=True)
    (hook / "inner" / "keep.sample").write_bytes(b"x")
    ok, out = workspace_run.finish(space, before, True, "[exit 0]")
    assert not ok and "could not be saved" in out and "until this session ends" in out
    assert not marks._file(marks.HOLDS, root, state).exists()
    held = _open(root)
    assert not held.writable and "kept in memory" in held.reason
    assert marks.clear_hold(root, state) and _open(root).writable
