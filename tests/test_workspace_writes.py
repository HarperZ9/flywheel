"""A sandboxed command may write in the project, and nowhere else.

Each test here starts a real command in this host's sandbox. On Windows that
is the low-integrity namespace; on Linux and macOS it is bubblewrap or
Seatbelt, and the tests skip with the reason when the host has neither.
"""
import hashlib
import os
import shutil
import sys
from pathlib import Path

import pytest

from harness.workspace_run import Workspace, open_workspace, workspace_run

WINDOWS = os.name == "nt"


def _backend_reason() -> str:
    """Why real sandbox runs cannot happen on this host, or an empty string."""
    if WINDOWS:
        return ""
    from harness import safe_program
    from harness.posix_sandbox import PROGRAM, backend_for
    from harness.sandbox_probe import sandbox_starts
    backend = backend_for()
    if backend is None:
        return "no bubblewrap or Seatbelt on this host"
    found = safe_program.which(PROGRAM[backend])
    if not sandbox_starts(backend, found if isinstance(found, str) else PROGRAM[backend]):
        return f"{backend} is installed and this host will not let it start"
    return ""


pytestmark = pytest.mark.skipif(bool(_backend_reason()), reason=_backend_reason() or "-")


def _write(rel: str, text: str = "x") -> str:
    """A shell command that writes `text` to `rel`, for this host's shell."""
    return f"echo {text}> {rel.replace('/', os.sep)}" if WINDOWS else f"echo {text} > '{rel}'"


@pytest.fixture
def project(tmp_path):
    """A project root with a home and a Flywheel state folder outside it."""
    base = tmp_path.resolve()
    root, home, state = base / "proj", base / "home", base / "state"
    for folder in (root / "src", home, state / "sessions" / "s1"):
        folder.mkdir(parents=True)
    (state / "sessions" / "s1" / "ledger.jsonl").write_text('{"n": 1}\n', encoding="utf-8")
    (state / "permissions.json").write_text('{"deny": []}', encoding="utf-8")
    space = open_workspace(root, environ={}, home=home, flywheel_home=state)
    assert space.writable, space.reason

    def run(cmd, **kw):
        return workspace_run(cmd, str(root), scratch_home=True, space=space, **kw)
    return root, home, state, run


def _tree_digest(folder: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(folder.rglob("*")):
        if path.name == "workspace-open":   # the session's own record, empty between runs
            assert list(path.iterdir()) == []
            continue
        digest.update(path.relative_to(folder).as_posix().encode())
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def test_a_command_writes_a_file_inside_the_root(project):
    root, _home, _state, run = project
    ok, out = run(_write("src/made.txt", "hello"))
    assert ok, out
    assert (root / "src" / "made.txt").read_text().strip() == "hello"
    assert out.endswith("[workspace writable: guarded paths unchanged]")


def test_a_command_changes_and_deletes_existing_files(project):
    root, _home, _state, run = project
    (root / "src" / "old.txt").write_text("old\n", encoding="utf-8")
    (root / "gone.txt").write_text("x", encoding="utf-8")
    remove = "del gone.txt" if WINDOWS else "rm gone.txt"
    ok, out = run(f"{_write('src/old.txt', 'new')} && {remove}")
    assert ok, out
    assert (root / "src" / "old.txt").read_text().strip() == "new"
    assert not (root / "gone.txt").exists()


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
@pytest.mark.skipif(sys.platform == "darwin",
                    reason="a Seatbelt run of git was not verified for this change")
def test_git_init_and_a_commit_succeed_inside_the_root(project):
    root, _home, _state, run = project
    ok, out = run("git init -q . && " + _write("a.txt", "one") + " && git add a.txt && "
                  "git -c user.name=t -c user.email=t@example.com commit -q -m first"
                  " && git log --oneline")
    assert ok, out
    assert "first" in out
    assert (root / ".git" / "HEAD").is_file()
    assert any((root / ".git" / "objects").rglob("*"))
    assert out.endswith("[workspace writable: guarded paths unchanged]")


def test_a_write_outside_the_root_is_refused(project):
    root, home, _state, run = project
    outside = root.parent / "outside"
    outside.mkdir()
    for target in (outside / "escaped.txt", home / "escaped.txt"):
        ok, _out = run(_write(str(target)))
        assert not ok
        assert not target.exists()
    ok, _out = run(_write("../outside/dotdot.txt"))
    assert not ok and not (outside / "dotdot.txt").exists()
    assert list(outside.iterdir()) == [] and list(home.iterdir()) == []


def test_a_link_inside_the_root_that_points_outside_is_refused(project):
    root, _home, _state, run = project
    outside = root.parent / "outside"
    outside.mkdir()
    (outside / "theirs.txt").write_text("theirs", encoding="utf-8")
    if WINDOWS:
        import _winapi
        _winapi.CreateJunction(str(outside), str(root / "link"))
    else:
        (root / "link").symlink_to(outside, target_is_directory=True)
    ok, _out = run(_write("link/escaped.txt"))
    assert not ok
    ok, _out = run(_write("link/theirs.txt", "mine"))
    assert not ok
    assert sorted(p.name for p in outside.iterdir()) == ["theirs.txt"]
    assert (outside / "theirs.txt").read_text() == "theirs"


def test_a_write_into_git_hooks_is_refused(project):
    root, _home, _state, run = project
    hooks = root / ".git" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "pre-commit").write_bytes(b"#!/bin/sh\nexit 0\n")
    ok, out = run(_write(".git/hooks/post-checkout", "evil"))
    assert not ok, out
    assert not (hooks / "post-checkout").exists()
    ok, out = run(_write(".git/hooks/pre-commit", "evil"))
    assert not ok, out
    assert (hooks / "pre-commit").read_bytes() == b"#!/bin/sh\nexit 0\n"


def test_a_hook_planted_by_renaming_git_aside_is_put_back(project):
    """The kernel label does not stop a rename of the folder above the hooks."""
    root, _home, _state, run = project
    hooks = root / ".git" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "pre-commit").write_bytes(b"#!/bin/sh\nexit 0\n")
    move = "ren .git gitold && mkdir .git\\hooks" if WINDOWS \
        else "mv .git gitold && mkdir -p .git/hooks"
    ok, out = run(f"{move} && {_write('.git/hooks/pre-commit', 'evil')}")
    assert not ok
    if WINDOWS:     # verified here; another kernel may refuse the rename itself
        assert "[refused] the command changed a guarded path" in out
    assert (hooks / "pre-commit").read_bytes() == b"#!/bin/sh\nexit 0\n"


def test_a_git_config_line_that_starts_a_program_is_put_back(project):
    root, _home, _state, run = project
    (root / ".git").mkdir()
    config = root / ".git" / "config"
    config.write_bytes(b"[core]\n\tbare = false\n")
    line = "echo 	fsmonitor = evil>> .git\\config" if WINDOWS \
        else "printf '\\tfsmonitor = evil\\n' >> .git/config"
    ok, out = run(line)
    assert not ok
    assert "core.fsmonitor" in out
    assert config.read_bytes() == b"[core]\n\tbare = false\n"


def test_the_sessions_own_permission_files_stay_as_they_were(project):
    root, _home, _state, run = project
    (root / ".flywheel").mkdir()
    rules = root / ".flywheel" / "permissions.json"
    rules.write_bytes(b'{"deny": ["run:git push*"]}')
    ok, _out = run(_write(".flywheel/permissions.json", "{}"))
    assert not ok
    assert rules.read_bytes() == b'{"deny": ["run:git push*"]}'
    ok, out = run(_write(".mcp.json", "{}"))
    assert not ok and "[refused]" in out
    assert not (root / ".mcp.json").exists()


def test_flywheel_state_is_unchanged_after_a_run(project):
    root, _home, state, run = project
    before = _tree_digest(state)
    ok, _out = run(_write("fine.txt"))
    assert ok
    for target in (state / "permissions.json", state / "sessions" / "s1" / "ledger.jsonl",
                   state / "new.txt"):
        ok, _out = run(_write(str(target), "evil"))
        assert not ok
    assert _tree_digest(state) == before


def test_the_root_is_closed_again_after_the_run(project):
    """A later read-only run cannot write, not even to a file a command made."""
    root, _home, _state, run = project
    assert run(_write("made.txt"))[0]
    closed = Workspace(root, False, "test")
    ok, out = workspace_run(_write("made.txt", "again"), str(root), scratch_home=True,
                            space=closed)
    assert not ok
    assert (root / "made.txt").read_text().strip() == "x"
    assert out.endswith("[workspace read-only: test]")
    ok, _out = workspace_run(_write("second.txt"), str(root), scratch_home=True, space=closed)
    assert not ok and not (root / "second.txt").exists()


def test_scratch_temp_is_writable_and_removed(project):
    root, _home, _state, run = project
    cmd = "echo t> %TEMP%\\t.txt && type %TEMP%\\t.txt" if WINDOWS \
        else 'echo t > "$TMPDIR/t.txt" && cat "$TMPDIR/t.txt"'
    ok, out = run(cmd)
    assert ok, out
    assert [p.name for p in root.parent.iterdir() if p.name.startswith("fw_sandbox_")] == []
