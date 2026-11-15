"""Findings from the security review of the confinement and isolation change.

Each was written to fail before its fix: the ``git`` that ``--auto-commit`` runs
was still found by bare name, so a planted ``git.exe`` in the working folder ran
instead; and a ledger file whose name is not a valid session id vanished from
the listing without being counted. The short-name check holds without a change
and stays as a regression test. A later review added one more: each git call
read every PATH entry again, which took about a second a call under WSL.
"""
import ctypes
import os
import shutil
import subprocess

import pytest
from cli_stand_in import SYSTEM32, WINDOWS

from relay._vendor import safe_spawn
from relay.local_git import GitRepo, commit_run
from relay.local_session import SessionLedger
from relay.local_tools import ToolGate
from relay.mcp_paths import GuardedExecutor, ProtectedPaths
from relay.session_store import list_sessions


@pytest.mark.skipif(not WINDOWS or shutil.which("git") is None,
                    reason="CreateProcess searches the working folder on Windows; needs git")
def test_a_git_planted_in_the_working_folder_never_runs(tmp_path, monkeypatch):
    repo, cwd = tmp_path / "repo", tmp_path / "cwd"
    repo.mkdir()
    cwd.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True, timeout=60)
    shutil.copy(os.path.join(SYSTEM32, "hostname.exe"), cwd / "git.exe")
    monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)
    monkeypatch.chdir(cwd)
    assert GitRepo(str(repo)).is_repo() is True


def test_a_git_that_cannot_be_found_reads_as_no_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    assert GitRepo(str(tmp_path)).is_repo() is False


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_a_commit_reads_path_once_for_all_its_git_calls(tmp_path, monkeypatch):
    # Each lookup reads every PATH entry, which is slow under WSL, so the git calls
    # of one commit share one lookup and one guarded environment.
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True, timeout=60)
    for key, value in (("user.name", "relay test"), ("user.email", "relay-test@example.invalid"),
                       ("commit.gpgsign", "false")):
        subprocess.run(["git", "-C", str(repo), "config", key, value], check=True, timeout=60)
    (repo / "note.txt").write_text("hello\n", encoding="utf-8")
    reads = []
    for name in ("resolve", "child_env"):
        real = getattr(safe_spawn, name)
        monkeypatch.setattr(safe_spawn, name,
                            lambda *a, _real=real, _name=name, **k: reads.append(_name)
                            or _real(*a, **k))
    out = commit_run(str(repo), "add a note", "CHK", paths=["note.txt"])
    assert out["committed"] is True, out
    assert sorted(reads) == ["child_env", "resolve"], reads


def test_a_ledger_with_an_invalid_name_is_counted_as_skipped(tmp_path):
    led = SessionLedger()
    led.append("user", "g")
    led.save(str(tmp_path / "good.jsonl"))
    led.save(str(tmp_path / "bad name.jsonl"))
    out = list_sessions(str(tmp_path))
    assert [s["id"] for s in out["sessions"]] == ["good"] and out["skipped"] == 1


@pytest.mark.skipif(not WINDOWS, reason="8.3 short names exist only on Windows")
def test_a_short_name_for_agent_configuration_is_refused(tmp_path):
    (tmp_path / ".claude").mkdir()
    buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.kernel32.GetShortPathNameW(str(tmp_path / ".claude"), buf, 260)
    short = os.path.basename(buf.value)
    if short.lower() == ".claude":
        pytest.skip("8.3 names are off on this volume")
    ex = GuardedExecutor(root=str(tmp_path), gate=ToolGate(allow_write=True),
                         protected=ProtectedPaths())
    res = ex.execute("write_file", {"path": f"{short}/settings.json", "content": "{}"})
    assert res.ok is False and not (tmp_path / ".claude" / "settings.json").exists()


def test_a_dangling_link_in_the_store_is_skipped_not_a_crash(tmp_path):
    led = SessionLedger()
    led.append("user", "g")
    led.save(str(tmp_path / "good.jsonl"))
    try:
        os.symlink(tmp_path / "gone.jsonl.target", tmp_path / "dangling.jsonl")
    except OSError:
        pytest.skip("this machine cannot create a symlink")
    out = list_sessions(str(tmp_path))
    assert [s["id"] for s in out["sessions"]] == ["good"] and out["skipped"] == 1
