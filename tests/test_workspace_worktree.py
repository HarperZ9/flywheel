"""A linked git worktree: what git may write, and what stays guarded."""
import os
import shutil
import subprocess

import pytest

from harness import workspace_guard as guard
from harness import workspace_paths, workspace_run
from harness.machine_policy import Policy
from harness.workspace_run import open_workspace

WINDOWS = os.name == "nt"


def _open(root, **kw):
    base = root.parent
    return open_workspace(root, **{"environ": {}, "policy": Policy(), "home": base / "home",
                                   "flywheel_home": base / "state", **kw})


def _git(cwd, *args):
    done = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                          cwd=cwd, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


@pytest.fixture
def worktree(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    base = tmp_path.resolve()
    main, linked = base / "main", base / "linked"
    main.mkdir()
    _git(main, "init", "-q", ".")
    _git(main, "commit", "-q", "--allow-empty", "-m", "first")
    _git(main, "worktree", "add", "-q", str(linked), "-b", "side")
    return main, linked


def test_a_linked_worktree_names_what_git_writes_and_guards_the_repository(worktree):
    main, linked = worktree
    names = workspace_paths.protected(linked)
    admin = main / ".git" / "worktrees" / "linked"
    assert names["opened"][0] == str(admin)
    assert set(names["opened"][1:]) == {str(main / ".git" / name) for name in ("objects", "refs", "logs")
                                        if (main / ".git" / name).is_dir()}
    assert (main / ".git" / "hooks").as_posix() in names["hooks"] and ".git" in names["control"]
    before = guard.snapshot(linked)
    (main / ".git" / "hooks" / "pre-commit").write_bytes(b"evil")
    (linked / ".git").unlink()                       # git hides it on Windows; replace it
    (linked / ".git").write_text("gitdir: ../evil\n", encoding="utf-8")
    problems = guard.verify(linked, before)
    assert len(problems) == 2 and not (main / ".git" / "hooks" / "pre-commit").exists()
    assert workspace_paths.linked_git(linked) == (admin, main / ".git")
    space = _open(linked)
    assert space.writable and space.posix()["extra_writable"] == names["opened"]


def test_posix_backends_open_the_worktree_git_folders():
    from harness.posix_sandbox import bwrap_argv, describe
    from harness.sandbox_policy import sbpl_profile
    argv = bwrap_argv("bwrap", "/w", "/s", "git commit", extra_writable=("/m/.git/objects",))
    assert argv[argv.index("/m/.git/objects") - 1] == "--bind"
    assert '(subpath "/m/.git/objects")' in sbpl_profile("/w", "/s", extra_writable=("/m/.git/objects",))
    assert describe("bwrap", "/w", "/s", extra_writable=("/m/x",)).writable == ("/w", "/s", "/m/x")


@pytest.mark.skipif(not WINDOWS, reason="a real commit in a worktree was run on Windows only")
def test_git_add_and_commit_work_in_a_linked_worktree(worktree):
    main, linked = worktree
    space = _open(linked)
    assert space.writable, space.reason

    def run(cmd):
        return workspace_run.workspace_run(cmd, str(linked), scratch_home=True, space=space)
    ok, out = run("echo one> a.txt && git add a.txt && git -c user.name=t "
                  "-c user.email=t@example.com commit -q -m second && git log --oneline")
    assert ok, out
    assert "second" in out and out.endswith("[workspace writable: guarded paths unchanged]")
    hook = main / ".git" / "hooks" / "pre-commit"
    ok, _out = run(f"echo evil> {hook}")
    assert not ok and not hook.exists()
    ok, out = run("del /a .git && echo gitdir: ../evil> .git")
    assert not ok and "[refused]" in out
    assert workspace_paths.linked_git(linked) is not None
    ok, _out = run(f"echo x> {main / 'outside.txt'}")
    assert not ok and not (main / "outside.txt").exists()
    from harness.windows_label import is_low
    assert not is_low(main / ".git" / "objects") and not is_low(linked)
