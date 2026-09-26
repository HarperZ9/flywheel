"""EN-C6: a run's git identity (HEAD, tracked files, status) is recorded
with hardened git calls: a repository-configured fsmonitor command is not
run and `.git/index` is not modified. Outside git there is no identity."""
import json
import subprocess
import sys

from bench_fixtures import git, git_repo
from harness.local_session import SessionLedger
from harness.workspace_git_identity import git_identity, record_git


def test_identity_is_recorded_in_a_git_repository(tmp_path):
    repo = git_repo(tmp_path)
    identity = git_identity(repo)
    assert identity["head"] == git(repo, "rev-parse", "HEAD")
    assert identity["clean"] is True and len(identity["tracked_sha256"]) == 64
    ledger = SessionLedger()
    record_git(str(repo), ledger)
    assert [e.kind for e in ledger.entries] == ["workspace_git"]
    assert json.loads(ledger.entries[0].content) == identity


def test_there_is_no_identity_outside_git(tmp_path):
    (tmp_path / "plain").mkdir()
    assert git_identity(tmp_path / "plain") is None
    ledger = SessionLedger()
    record_git(str(tmp_path / "plain"), ledger)
    assert ledger.entries == []


def test_changes_and_untracked_files_show_but_ignored_files_do_not(tmp_path):
    repo = git_repo(tmp_path)
    (repo / ".venv").mkdir()
    (repo / ".venv" / "lib.py").write_text("x = 1\n")
    assert git_identity(repo)["clean"] is True
    (repo / "notes.txt").write_text("untracked\n")
    assert git_identity(repo)["clean"] is False
    (repo / "notes.txt").unlink()
    (repo / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    assert git_identity(repo)["clean"] is False


def test_a_configured_fsmonitor_does_not_run_and_the_index_is_untouched(tmp_path):
    repo = git_repo(tmp_path)
    marker = tmp_path / "fsmonitor-ran"
    hook = tmp_path / "fsmonitor.py"
    hook.write_text(f"open({str(marker)!r}, 'w').close()\nprint('')\n")
    git(repo, "config", "core.fsmonitor", f'"{sys.executable}" "{hook}"')
    index = repo / ".git" / "index"
    before = (index.read_bytes(), index.stat().st_mtime_ns)
    assert git_identity(repo)["head"]
    assert not marker.exists()
    assert (index.read_bytes(), index.stat().st_mtime_ns) == before
    # False-success control: a plain git status does run the configured command.
    subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True)
    assert marker.exists()
