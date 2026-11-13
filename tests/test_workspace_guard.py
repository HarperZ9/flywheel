"""The guarded paths inside a writable project, and the git config allowlist.

These run on every host. They change files directly, the way a command
inside the sandbox could, and assert what `verify` reports and puts back.
"""
import os

import pytest

from harness import workspace_guard as guard
from harness.git_config_guard import strip_unsafe, unsafe_additions


def _repo(tmp_path):
    root = tmp_path / "proj"
    (root / ".git" / "hooks").mkdir(parents=True)
    (root / ".git" / "config").write_bytes(b"[core]\n\tbare = false\n")
    (root / ".git" / "hooks" / "pre-commit").write_bytes(b"#!/bin/sh\nexit 0\n")
    (root / ".flywheel").mkdir()
    (root / ".flywheel" / "permissions.json").write_bytes(b'{"deny": ["run:git push*"]}')
    return root


def test_an_untouched_project_reports_nothing(tmp_path):
    root = _repo(tmp_path)
    before = guard.snapshot(root)
    (root / "src.py").write_text("x = 1\n", encoding="utf-8")
    assert guard.verify(root, before) == []


def test_a_new_hook_is_removed_and_reported(tmp_path):
    root = _repo(tmp_path)
    before = guard.snapshot(root)
    (root / ".git" / "hooks" / "post-checkout").write_bytes(b"#!/bin/sh\ncurl evil\n")
    problems = guard.verify(root, before)
    assert problems == [".git/hooks/post-checkout: added, removed"]
    assert not (root / ".git" / "hooks" / "post-checkout").exists()


def test_a_changed_hook_gets_its_bytes_back(tmp_path):
    root = _repo(tmp_path)
    before = guard.snapshot(root)
    (root / ".git" / "hooks" / "pre-commit").write_bytes(b"#!/bin/sh\nrm -rf ~\n")
    assert guard.verify(root, before) == [".git/hooks/pre-commit: changed, put back"]
    assert (root / ".git" / "hooks" / "pre-commit").read_bytes() == b"#!/bin/sh\nexit 0\n"


def test_a_deleted_hook_is_restored(tmp_path):
    root = _repo(tmp_path)
    before = guard.snapshot(root)
    (root / ".git" / "hooks" / "pre-commit").unlink()
    assert guard.verify(root, before) == [".git/hooks/pre-commit: deleted, put back"]
    assert (root / ".git" / "hooks" / "pre-commit").is_file()


def test_sample_hooks_from_git_init_are_allowed(tmp_path):
    root = tmp_path / "fresh"
    root.mkdir()
    before = guard.snapshot(root)
    (root / ".git" / "hooks").mkdir(parents=True)
    (root / ".git" / "hooks" / "pre-commit.sample").write_bytes(b"#!/bin/sh\n")
    (root / ".git" / "config").write_bytes(
        b"[core]\n\trepositoryformatversion = 0\n\tfilemode = false\n\tbare = false\n")
    assert guard.verify(root, before) == []
    assert (root / ".git" / "hooks" / "pre-commit.sample").exists()


def test_renaming_git_aside_and_rebuilding_it_gains_nothing(tmp_path):
    """The check is by content at the path, so a swapped folder is still caught."""
    root = _repo(tmp_path)
    before = guard.snapshot(root)
    (root / ".git").rename(root / ".git-old")
    (root / ".git" / "hooks").mkdir(parents=True)
    (root / ".git" / "hooks" / "pre-commit").write_bytes(b"#!/bin/sh\ncurl evil\n")
    (root / ".git" / "config").write_bytes(b"[core]\n\tfsmonitor = evil.exe\n")
    problems = guard.verify(root, before)
    assert (root / ".git" / "hooks" / "pre-commit").read_bytes() == b"#!/bin/sh\nexit 0\n"
    assert (root / ".git" / "config").read_bytes() == b"[core]\n\tbare = false\n"
    assert any("core.fsmonitor" in line for line in problems)
    assert any("pre-commit: changed, put back" in line for line in problems)


@pytest.mark.parametrize("line", [
    b"\thooksPath = /tmp/evil", b"\tfsmonitor = evil", b"\tsshCommand = evil",
    b"\tpager = evil", b"\teditor = evil"])
def test_config_keys_that_start_programs_are_put_back(tmp_path, line):
    root = _repo(tmp_path)
    before = guard.snapshot(root)
    config = root / ".git" / "config"
    config.write_bytes(config.read_bytes() + line + b"\n")
    problems = guard.verify(root, before)
    assert len(problems) == 1 and "put back" in problems[0]
    assert config.read_bytes() == b"[core]\n\tbare = false\n"


def test_plain_git_work_on_the_config_is_allowed(tmp_path):
    root = _repo(tmp_path)
    before = guard.snapshot(root)
    added = (b'[user]\n\tname = A\n\temail = a@example.com\n'
             b'[remote "origin"]\n\turl = https://example.com/r.git\n'
             b'\tfetch = +refs/heads/*:refs/remotes/origin/*\n'
             b'[branch "main"]\n\tremote = origin\n\tmerge = refs/heads/main\n')
    config = root / ".git" / "config"
    config.write_bytes(config.read_bytes() + added)
    assert guard.verify(root, before) == []
    assert config.read_bytes().endswith(added)


@pytest.mark.parametrize("text", [
    b'[alias]\n\tx = !sh -c evil\n', b'[include]\n\tpath = /tmp/evil\n',
    b'[remote "o"]\n\turl = ext::sh -c evil\n', b'[filter "f"]\n\tclean = evil\n',
    b'[credential]\n\thelper = evil\n', b'[diff]\n\texternal = evil\n',
    b'[core]\n\tbare = false \\\n', b'[remote.o]\n\turl = x\n', b'stray = 1\n'])
def test_unsafe_additions_are_named(text):
    assert unsafe_additions(b"[core]\n\tbare = false\n", text) != []


def test_an_entry_the_user_already_had_is_not_judged():
    mine = b"[core]\n\tpager = less\n[alias]\n\tco = checkout\n"
    assert unsafe_additions(mine, mine + b"[user]\n\tname = A\n") == []


def test_a_new_config_keeps_only_allowlisted_lines(tmp_path):
    root = tmp_path / "fresh"
    root.mkdir()
    before = guard.snapshot(root)
    (root / ".git").mkdir()
    (root / ".git" / "config").write_bytes(
        b"[core]\n\tbare = false\n\thooksPath = /tmp/evil\n[alias]\n\tx = !evil\n")
    problems = guard.verify(root, before)
    assert len(problems) == 1 and "core.hookspath" in problems[0]
    assert (root / ".git" / "config").read_bytes() == b"[core]\n\tbare = false\n[alias]\n"
    assert strip_unsafe(b"[core]\n\tfsmonitor = x\n") == b"[core]\n"


@pytest.mark.parametrize("name", guard.CONTROL_FILES)
def test_session_control_files_cannot_be_added_or_changed(tmp_path, name):
    root = _repo(tmp_path)
    before = guard.snapshot(root)
    target = root / name
    existed = target.exists()
    old = target.read_bytes() if existed else None
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b'{"allow": ["run:*"]}')
    problems = guard.verify(root, before)
    assert len(problems) == 1 and name in problems[0]
    assert (target.read_bytes() == old) if existed else not target.exists()


def test_a_hooks_folder_swapped_for_a_link_is_unlinked_not_followed(tmp_path):
    root = _repo(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_bytes(b"mine")
    before = guard.snapshot(root)
    (root / ".git" / "hooks").rename(root / ".git" / "hooks-old")
    link = root / ".git" / "hooks"
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(outside), str(link))
    else:
        link.symlink_to(outside, target_is_directory=True)
    problems = guard.verify(root, before)
    assert any("replaced by a link" in line for line in problems)
    assert (root / ".git" / "hooks" / "pre-commit").read_bytes() == b"#!/bin/sh\nexit 0\n"
    assert not guard._is_link(root / ".git" / "hooks")
    assert sorted(p.name for p in outside.iterdir()) == ["keep.txt"]
    assert (outside / "keep.txt").read_bytes() == b"mine"


def test_submodule_hooks_are_guarded_too(tmp_path):
    root = _repo(tmp_path)
    (root / ".git" / "modules" / "lib" / "hooks").mkdir(parents=True)
    before = guard.snapshot(root)
    (root / ".git" / "modules" / "lib" / "hooks" / "pre-push").write_bytes(b"evil")
    assert guard.verify(root, before) == [".git/modules/lib/hooks/pre-push: added, removed"]
