"""Moves that cross a boundary or replace a record: promotion never destroys a
global record, a promoted id is never issued again, a secret in provenance is
refused, and accepting a proposal never erases a newer accepted record."""
from __future__ import annotations

import io

import pytest

from canon.cli import run_cli
from canon.exit_codes import EX_CONFLICT, EX_OK
from canon.workspace import authoring
from canon.workspace.identity import derive_identity
from canon.workspace.moves import promote
from canon.workspace.store import AcceptConflict, ProjectStore, SecretRefused, StoreError

from ._workspace_helpers import block, init_repo


def _run(argv):
    stdout, stderr = io.StringIO(), io.StringIO()
    code = run_cli(argv, stdin=None, stdout=stdout, stderr=stderr, environ={})
    return code, stdout.getvalue(), stderr.getvalue()


@pytest.fixture()
def two(tmp_path):
    root = tmp_path / "store"
    a = ProjectStore(root, derive_identity(init_repo(tmp_path / "a", "https://github.com/o/a")))
    b = ProjectStore(root, derive_identity(init_repo(tmp_path / "b", "https://github.com/o/b")))
    return a, b


def test_promoting_an_id_global_already_holds_is_refused_and_writes_nothing(two):
    a, b = two
    a.put(authoring.constraint(a, statement="A: never run migrations on Friday"))
    b.put(authoring.constraint(b, statement="B: tabs not spaces"))
    promote(a, "constraint-1", reason="applies everywhere")
    with pytest.raises(StoreError, match="global already holds global/constraint-1"):
        promote(b, "constraint-1", reason="applies everywhere")
    assert [r.record.data["statement"] for r in a.global_rows()] == [
        "A: never run migrations on Friday"]
    assert [r.data["statement"] for r in b.records()] == ["B: tabs not spaces"]


def test_a_promoted_ordinal_is_never_issued_again_in_its_project(two):
    a, _ = two
    a.put(authoring.work_item(a, title="first"))
    promote(a, "task-1", reason="every project needs it")
    second = authoring.work_item(a, title="second")
    assert second.id != "task-1"
    a.put(second)
    promote(a, second.id, reason="this one too")
    titles = sorted(r.record.data["title"] for r in a.global_rows())
    assert titles == ["first", "second"]


def test_a_secret_in_provenance_is_refused_by_the_store(two):
    a, _ = two
    record = authoring.build("work-item", "imp-task-1", {"title": "t", "status": "open"}, 1,
                             harness="claude-code", session_id="sk-ant-api03-" + "b" * 30)
    with pytest.raises(SecretRefused):
        a.put(record)
    assert not (a.project_dir() / "records.jsonl").exists()


def _switched(tmp_path):
    repo = init_repo(tmp_path / "repo", "https://github.com/o/repo")
    store = ProjectStore(tmp_path / "s", derive_identity(repo))
    store.put(block("voice", "Plain technical English.", 1))
    store.put(authoring.work_item(store, title="Write the tests"))
    base = ["--workspace", str(repo), "--store", str(store.root)]
    (repo / "CLAUDE.md").write_text("<!-- canon:begin scope=workspace -->\n<!-- canon:end -->\n",
                                    encoding="utf-8", newline="\n")
    assert _run(["switch", "--to", "claude-code", *base, "--home", str(tmp_path / "h")])[0] == EX_OK
    return repo, store, base


def test_accepting_a_proposal_made_before_a_newer_update_is_refused(tmp_path):
    repo, store, base = _switched(tmp_path)
    path = repo / "CLAUDE.md"
    path.write_text(path.read_text(encoding="utf-8").replace(
        "- [open] Write the tests (task-2)", "- [in-progress] Write the tests (task-2)"),
        encoding="utf-8", newline="\n")
    assert _run(["workspace", "pull", "--from", "claude-code", *base,
                 "--home", str(tmp_path / "h")])[0] == EX_OK
    assert _run(["workspace", "set-status", "task-2", "blocked", "--detail",
                 "waiting on the CI image", *base])[0] == EX_OK
    code, _, err = _run(["workspace", "accept", "task-2", *base])
    assert code == EX_CONFLICT and "changed since" in err
    [task] = [r for r in store.records() if r.id == "task-2"]
    assert task.data["status"] == "blocked" and task.data["detail"] == "waiting on the CI image"
    with pytest.raises(AcceptConflict):
        store.decide("task-2", accept=True, reason="r")
    assert _run(["workspace", "accept", "task-2", "--force", *base])[0] == EX_OK
    [task] = [r for r in store.records() if r.id == "task-2"]
    assert task.data["status"] == "in-progress"
