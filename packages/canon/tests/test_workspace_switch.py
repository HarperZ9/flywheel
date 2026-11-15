"""`switch`: the brief rendered into the target's own instruction region,
through the allow-list and the markers, and the `handoff` command surface."""
from __future__ import annotations

import io
import json

import pytest

from canon.cli import run_cli
from canon.exit_codes import EX_BUDGET, EX_CONFLICT, EX_OK, EX_USAGE
from canon.textblock import ingest_region
from canon.workspace import authoring
from canon.workspace.identity import derive_identity
from canon.workspace.pool import project_pool
from canon.workspace.store import ProjectStore
from canon.workspace.switch import BRIEF_BLOCK_ID, SwitchRefused, commit_switch, plan_switch
from canon.workspace.targets import target_for

from ._workspace_helpers import block, init_repo

HOST = "# My notes\r\n\r\nKeep this.\r\n<!-- canon:begin scope=workspace -->\r\n<!-- canon:end -->\r\nAnd this.\r\n"


@pytest.fixture()
def project(tmp_path):
    repo = init_repo(tmp_path / "repo", "https://github.com/o/repo")
    ident = derive_identity(repo)
    store = ProjectStore(tmp_path / "store", ident)
    store.put(block("voice", "Plain technical English.", 1))
    store.put(authoring.focus(store, goal="Ship switch", branch="main"))
    store.put(authoring.work_item(store, title="Write switch tests"))
    return repo, ident, store, tmp_path / "home"


def _io(files: dict):
    return (lambda p: files.get(p)), (lambda p, t: files.__setitem__(p, t))


def _plan(project, target="claude-code", files=None, **kw):
    repo, ident, store, home = project
    read, _ = _io(files if files is not None else {})
    return plan_switch(ident, project_pool(store), target_for(target), home=str(home),
                       read_text=read, **kw)


def test_switch_writes_blocks_and_brief_inside_the_markers_only(project):
    repo, ident, store, home = project
    path = str((repo / "CLAUDE.md").resolve())
    files = {path: HOST}
    plan = _plan(project, files=files)
    assert plan.status == "write" and plan.path == path
    read, write = _io(files)
    commit_switch(plan, write)
    new = files[path]
    assert new.startswith("# My notes\r\n\r\nKeep this.\r\n<!-- canon:begin scope=workspace -->\r\n")
    assert new.endswith("<!-- canon:end -->\r\nAnd this.\r\n")
    ids = [r.id for r in ingest_region(new)]
    assert ids == ["voice", BRIEF_BLOCK_ID]
    brief = next(r for r in ingest_region(new) if r.id == BRIEF_BLOCK_ID)
    assert "Goal: Ship switch" in brief.data["body"]
    assert "Write switch tests" in brief.data["body"]
    assert _plan(project, files=files).status == "unchanged"


def test_a_file_without_a_region_is_refused_and_untouched(project):
    repo, *_ = project
    path = str((repo / "AGENTS.md").resolve())
    with pytest.raises(SwitchRefused, match="no canon region") as err:
        _plan(project, "codex", files={path: "# Just mine\n"})
    assert err.value.code == "conflict"


def test_a_missing_file_needs_create_and_create_makes_one(project):
    with pytest.raises(SwitchRefused, match="--create"):
        _plan(project, "codex")
    plan = _plan(project, "codex", create=True)
    assert plan.status == "create" and plan.old_text is None
    assert "<!-- canon:begin scope=workspace -->" in plan.new_text


def test_codex_truncation_limit_is_refused_before_writing(project):
    repo, ident, store, home = project
    path = str((repo / "AGENTS.md").resolve())
    host = "x" * 32_600 + "\n<!-- canon:begin scope=workspace -->\n<!-- canon:end -->\n"
    with pytest.raises(SwitchRefused, match="truncates") as err:
        _plan(project, "codex", files={path: host})
    assert err.value.code == "budget_too_small"


def test_a_target_with_no_instruction_file_returns_the_brief_alone(project):
    plan = _plan(project, "markdown")
    assert plan.status == "no-surface" and plan.path is None
    assert "Ship switch" in plan.brief.text


def _run(argv):
    stdout, stderr = io.StringIO(), io.StringIO()
    code = run_cli(argv, stdin=None, stdout=stdout, stderr=stderr, environ={})
    return code, stdout.getvalue(), stderr.getvalue()


def test_the_handoff_command_prints_the_brief_and_writes_a_receipt(project):
    repo, ident, store, home = project
    receipt = repo / "brief.receipt.json"
    code, out, _ = _run(["handoff", "--to", "gemini-cli", "--workspace", str(repo),
                         "--store", str(store.root), "--receipt", str(receipt)])
    assert code == EX_OK
    assert out.startswith("# Resume brief: github.com/o/repo")
    data = json.loads(receipt.read_text(encoding="utf-8"))
    assert data["schema"] == "canon.handoff-receipt/v1"
    assert data["target"]["name"] == "gemini-cli"
    code, _, err = _run(["handoff", "--to", "gemini-cli", "--workspace", str(repo),
                         "--store", str(store.root), "--receipt", str(receipt)])
    assert code == EX_CONFLICT and "already exists" in err


def test_the_switch_command_dry_run_writes_nothing(project):
    repo, ident, store, home = project
    target = repo / "CLAUDE.md"
    target.write_text("<!-- canon:begin scope=workspace -->\n<!-- canon:end -->\n",
                      encoding="utf-8")
    before = target.read_bytes()
    base = ["--to", "claude-code", "--workspace", str(repo), "--store", str(store.root),
            "--home", str(home)]
    code, out, _ = _run(["switch", "--dry-run", *base])
    assert code == EX_OK and "would write" in out
    assert target.read_bytes() == before
    code, out, _ = _run(["--json", "switch", *base])
    assert code == EX_OK and json.loads(out)["data"]["status"] == "write"
    assert BRIEF_BLOCK_ID in target.read_text(encoding="utf-8")


def test_an_unknown_target_or_a_tiny_budget_is_a_stable_failure(project):
    repo, ident, store, home = project
    base = ["--workspace", str(repo), "--store", str(store.root)]
    assert _run(["handoff", "--to", "notepad", *base])[0] == EX_USAGE
    assert _run(["handoff", "--to", "codex", "--budget-bytes", "30", *base])[0] == EX_BUDGET


def test_a_file_changed_after_planning_is_not_overwritten(project):
    repo, ident, store, home = project
    path = str((repo / "CLAUDE.md").resolve())
    files = {path: HOST}
    plan = _plan(project, files=files)
    files[path] = HOST.replace("Keep this.", "Edited meanwhile.")
    with pytest.raises(SwitchRefused, match="changed while") as err:
        commit_switch(plan, files.__setitem__, files.get)
    assert err.value.code == "conflict"
    assert "Edited meanwhile." in files[path]
    created = _plan(project, "codex", create=True)
    later = {created.path: "someone else's file\n"}
    with pytest.raises(SwitchRefused, match="changed while"):
        commit_switch(created, later.__setitem__, later.get)
    assert later[created.path] == "someone else's file\n"
