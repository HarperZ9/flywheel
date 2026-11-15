"""Back-flow cases a review found: several checkouts of one project, a render
restored by git, a held lock, loosely written ticks, edits from two tools, a
rejection that must not outlive its render, removed lines of every kind, and
blocks another project or global owns."""
from __future__ import annotations

import io

import pytest

from canon.cli import run_cli
from canon.concurrency import acquire_run_lock, release_run_lock
from canon.exit_codes import EX_CONFLICT, EX_OK
from canon.workspace import authoring
from canon.workspace.identity import derive_identity
from canon.workspace.store import ProjectStore

from ._workspace_helpers import block, init_repo

HOST = "# Mine\n<!-- canon:begin scope=workspace -->\n<!-- canon:end -->\n"


def _run(argv):
    stdout, stderr = io.StringIO(), io.StringIO()
    code = run_cli(argv, stdin=None, stdout=stdout, stderr=stderr, environ={})
    return code, stdout.getvalue(), stderr.getvalue()


def _checkout(tmp_path, name, remote="https://github.com/o/repo"):
    repo = init_repo(tmp_path / name, remote)
    (repo / "CLAUDE.md").write_text(HOST, encoding="utf-8", newline="\n")
    return repo


def _args(repo, tmp_path):
    return ["--workspace", str(repo), "--store", str(tmp_path / "store"),
            "--home", str(tmp_path / "h")]


def _switch(repo, tmp_path, target="claude-code", *extra):
    return _run(["switch", "--to", target, *extra, *_args(repo, tmp_path)])


def _ws(repo, tmp_path, *argv):
    return _run(["workspace", *argv, *_args(repo, tmp_path)[:4]])


def _edit(path, old, new):
    text = path.read_text(encoding="utf-8")
    assert old in text, old
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")


@pytest.fixture()
def one(tmp_path):
    repo = _checkout(tmp_path, "repo")
    store = ProjectStore(tmp_path / "store", derive_identity(repo))
    store.put(block("voice", "Plain technical English.", 1))
    store.put(authoring.focus(store, goal="Ship back-flow", branch="main"))
    store.put(authoring.work_item(store, title="Write the tests"))
    store.put(authoring.constraint(store, statement="Windows runner is slow",
                                   category="quirk"))
    store.put(authoring.decision(store, title="DB", decision_text="sqlite",
                                 context="small", rejected=[("postgres", "ops cost")]))
    assert _switch(repo, tmp_path)[0] == EX_OK
    return tmp_path, repo, store


def test_two_checkouts_switching_in_turn_never_propose_anything(tmp_path):
    a, b = _checkout(tmp_path, "wa"), _checkout(tmp_path, "wb")
    store = ProjectStore(tmp_path / "store", derive_identity(a))
    store.put(block("voice", "Plain technical English.", 1))
    task = authoring.work_item(store, title="first")
    store.put(task)
    assert _switch(b, tmp_path)[0] == EX_OK
    assert _switch(a, tmp_path)[0] == EX_OK, "a first switch never retires blocks"
    store.put(authoring.work_item(store, title="second"))
    assert _switch(a, tmp_path)[0] == EX_OK
    store.put(authoring.update_work_item(store, task.id, status="done"))
    assert _switch(b, tmp_path)[0] == EX_OK
    assert _switch(a, tmp_path)[0] == EX_OK
    assert store.proposals() == []


def test_a_render_restored_by_git_is_stale_not_edited(one):
    tmp_path, repo, store = one
    path = repo / "CLAUDE.md"
    older = path.read_text(encoding="utf-8")
    store.put(authoring.work_item(store, title="A later task"))
    assert _switch(repo, tmp_path)[0] == EX_OK
    path.write_text(older, encoding="utf-8", newline="\n")
    assert _switch(repo, tmp_path)[0] == EX_OK
    assert store.proposals() == []
    assert "A later task" in path.read_text(encoding="utf-8")


def test_a_held_lock_refuses_before_the_file_is_written(one):
    tmp_path, repo, store = one
    path = repo / "CLAUDE.md"
    store.put(authoring.work_item(store, title="Another task"))
    before = path.read_bytes()
    lock = acquire_run_lock(tmp_path / "store", f"canon-project-{store.project_id}")
    try:
        code, _, err = _switch(repo, tmp_path)
    finally:
        release_run_lock(lock)
    assert code == EX_CONFLICT and "lock" in err
    assert path.read_bytes() == before
    assert _switch(repo, tmp_path)[0] == EX_OK and store.proposals() == []


@pytest.mark.parametrize("mark", ["x", "X", "Done"])
def test_a_loosely_written_tick_means_done_never_dropped(one, mark):
    tmp_path, repo, store = one
    _edit(repo / "CLAUDE.md", "- [open] Write the tests (task-3)",
          f"- [{mark}] Write the tests (task-3)")
    assert _switch(repo, tmp_path)[0] == EX_CONFLICT
    [row] = store.proposals()
    assert row.origin["rule"] == "brief-work" and row.record.data["status"] == "done"


def test_a_trailing_space_is_not_an_edit(one):
    tmp_path, repo, store = one
    _edit(repo / "CLAUDE.md", "Write the tests (task-3)", "Write the tests (task-3) ")
    assert _switch(repo, tmp_path)[0] == EX_OK
    assert store.proposals() == []


def test_an_edit_carries_only_the_fields_it_changed(one):
    tmp_path, repo, store = one
    _edit(repo / "CLAUDE.md", "- [open] Write the tests (task-3)",
          "- [open] Write the unit tests (task-3)")
    store.put(authoring.update_work_item(store, "task-3", status="done"))
    assert _switch(repo, tmp_path)[0] == EX_CONFLICT
    [row] = store.proposals()
    assert row.record.data == {"status": "done", "title": "Write the unit tests"}


def test_a_rejection_holds_only_for_the_render_it_was_made_against(one):
    tmp_path, repo, store = one
    path = repo / "CLAUDE.md"
    tick = ("- [open] Write the tests (task-3)", "- [done] Write the tests (task-3)")
    _edit(path, *tick)
    assert _switch(repo, tmp_path)[0] == EX_CONFLICT
    assert _ws(repo, tmp_path, "reject", "task-3", "--reason", "not done yet")[0] == EX_OK
    code, out, _ = _switch(repo, tmp_path)
    assert code == EX_OK and "overwrote edits you rejected before: task-3" in out
    _edit(path, *tick)
    assert _switch(repo, tmp_path)[0] == EX_CONFLICT
    assert [r.record.id for r in store.proposals()] == ["task-3"]


@pytest.mark.parametrize("old, new, expect", [
    ("- [quirk] Windows runner is slow (constraint-4)\n", "", "retire"),
    ("  Rejected: postgres. Reason: ops cost\n", "", "removed:   Rejected: postgres"),
    ("Goal: Ship back-flow\n", "", "removed: Goal: Ship back-flow"),
    ("## Resume brief: github.com/o/repo", "## Resume brief: renamed",
     "brief heading: Resume brief: renamed"),
    ('<!-- canon:block id="voice" ord="1" -->', '<!-- canon:block id="voice" ord="9" -->',
     "block voice: ord"),
])
def test_every_removed_or_changed_line_is_proposed_or_kept(one, old, new, expect):
    tmp_path, repo, store = one
    _edit(repo / "CLAUDE.md", old, new)
    assert _switch(repo, tmp_path)[0] == EX_CONFLICT
    if expect == "retire":
        [row] = store.proposals()
        assert row.record.id == "constraint-4" and row.record.temporal.valid_until
    else:
        [row] = store.proposals()
        assert expect in row.record.data["text"]


def test_a_removed_global_block_is_kept_as_a_note_not_a_retirement(one):
    tmp_path, repo, store = one
    store.put(block("house-style", "Use the house style.", 10))
    assert _ws(repo, tmp_path, "promote", "house-style", "--reason", "all repos")[0] == EX_OK
    (repo / "GEMINI.md").write_text(HOST, encoding="utf-8", newline="\n")
    assert _switch(repo, tmp_path, "gemini-cli")[0] == EX_OK
    path = repo / "GEMINI.md"
    text = path.read_text(encoding="utf-8")
    start = text.index('<!-- canon:block id="house-style"')
    path.write_text(text[:start] + text[text.index("<!-- canon:block", start + 1):],
                    encoding="utf-8", newline="\n")
    assert _switch(repo, tmp_path, "gemini-cli")[0] == EX_CONFLICT
    [row] = store.proposals()
    assert row.record.kind == "episodic-memory" and "belongs to global" in row.record.data["text"]


def test_an_edited_block_of_a_declared_project_never_becomes_ours(one):
    tmp_path, repo, store = one
    lib = ProjectStore(tmp_path / "store", derive_identity(init_repo(tmp_path / "lib",
                                                                     "https://github.com/o/lib")))
    lib.put(block("lib-api", "Call the lib through its facade.", 1))
    inc = ("--include-project", lib.project_id)
    assert _switch(repo, tmp_path, "claude-code", *inc)[0] == EX_OK
    _edit(repo / "CLAUDE.md", "through its facade.", "through its facade, never raw.")
    assert _switch(repo, tmp_path, "claude-code", *inc)[0] == EX_CONFLICT
    [row] = store.proposals()
    assert row.record.id != "lib-api" and lib.project_id in row.record.data["text"]
    assert _ws(repo, tmp_path, "accept", row.record.id)[0] == EX_OK
    assert _switch(repo, tmp_path, "claude-code", *inc)[0] == EX_OK


def test_a_retired_own_copy_does_not_block_a_declared_project_forever(one):
    from dataclasses import replace

    from canon.schema import Temporal
    from canon.workspace.pool import project_pool

    tmp_path, repo, store = one
    lib = ProjectStore(tmp_path / "store", derive_identity(init_repo(tmp_path / "lib",
                                                                     "https://github.com/o/lib")))
    lib.put(block("lib-api", "Call the lib through its facade.", 1))
    retired = replace(block("lib-api", "Old copy.", 50), temporal=Temporal(valid_until=51))
    store.put(retired)
    assert any(t.record.id == "lib-api" for t in
               project_pool(store, include_projects=(lib.project_id,)))
