"""Falsifiers for `flywheel code --worktree`: a separate checkout that carries your edits."""
import subprocess

import pytest

from harness.code_session import cli
from harness.code_session.worktree import WorktreeError, open_worktree
from tests.test_code_session import ScriptBackend


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@example.org")
    _git(r, "config", "user.name", "t")
    (r / "a.txt").write_text("one\n", encoding="utf-8")
    _git(r, "add", "a.txt")
    _git(r, "commit", "-qm", "init")
    return r


def test_worktree_carries_uncommitted_and_untracked_files(repo):
    (repo / "a.txt").write_text("one\nedited\n", encoding="utf-8")
    (repo / "new.txt").write_text("fresh", encoding="utf-8")
    wt = open_worktree(str(repo), "task1")
    assert wt.created and wt.branch == "flywheel/task1"
    path = repo.parent / "repo-worktrees" / "task1"
    assert (path / "a.txt").read_text(encoding="utf-8") == "one\nedited\n"
    assert (path / "new.txt").read_text(encoding="utf-8") == "fresh"
    assert sorted(wt.carried) == ["a.txt", "new.txt"]
    status = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True,
                            text=True).stdout
    assert status.split() == ["M", "a.txt", "??", "new.txt"]   # the checkout is untouched


def test_reopening_the_same_name_continues_there(repo):
    first = open_worktree(str(repo), "again")
    (repo.parent / "repo-worktrees" / "again" / "work.txt").write_text("x", encoding="utf-8")
    second = open_worktree(str(repo), "again")
    assert not second.created and second.path == first.path
    assert (repo.parent / "repo-worktrees" / "again" / "work.txt").exists()


def test_bad_names_and_non_repos_are_refused(repo, tmp_path):
    with pytest.raises(WorktreeError):
        open_worktree(str(repo), "../escape")
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(WorktreeError):
        open_worktree(str(plain), "x")


def test_session_edits_land_in_the_worktree_not_the_checkout(repo, tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_home", lambda: str(tmp_path / "home"))
    monkeypatch.setattr(cli, "ladder", lambda **kw: [ScriptBackend([
        'TOOL edit_file {"path": "a.txt", "old": "one", "new": "ONE"}', "done"])])
    code = cli.main(["-p", "shout", "--root", str(repo), "--worktree", "w1", "--mode", "edit",
                     "--no-save"])
    assert code == 0
    assert (repo / "a.txt").read_text(encoding="utf-8") == "one\n"
    assert (repo.parent / "repo-worktrees" / "w1" / "a.txt").read_text(
        encoding="utf-8") == "ONE\n"
