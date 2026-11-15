"""Drift back-flow: an edit made inside a rendered region becomes a proposal,
and switch will not overwrite it until each proposal is accepted or rejected."""
from __future__ import annotations

import io
import json

import pytest

from canon.cli import run_cli
from canon.exit_codes import EX_CONFLICT, EX_OK
from canon.textblock import ingest_region
from canon.workspace import authoring
from canon.workspace.identity import derive_identity
from canon.workspace.ledger import last_render
from canon.workspace.store import ProjectStore

from ._workspace_helpers import block, init_repo


def _run(argv):
    stdout, stderr = io.StringIO(), io.StringIO()
    code = run_cli(argv, stdin=None, stdout=stdout, stderr=stderr, environ={})
    return code, stdout.getvalue(), stderr.getvalue()


@pytest.fixture()
def project(tmp_path):
    repo = init_repo(tmp_path / "repo", "https://github.com/o/repo")
    ident = derive_identity(repo)
    store = ProjectStore(tmp_path / "store", ident)
    store.put(block("voice", "Plain technical English.", 1))
    store.put(authoring.focus(store, goal="Ship back-flow", branch="main"))
    store.put(authoring.work_item(store, title="Write the tests"))
    base = ["--workspace", str(repo), "--store", str(store.root), "--home", str(tmp_path / "h")]
    path = repo / "CLAUDE.md"
    path.write_text("# Mine\n<!-- canon:begin scope=workspace -->\n<!-- canon:end -->\n",
                    encoding="utf-8", newline="\n")
    assert _run(["switch", "--to", "claude-code", *base])[0] == EX_OK
    return store, path, base


def _edit(path, old, new):
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")


def _proposals(store):
    return {r.record.id: r for r in store.proposals()}


def test_switch_records_what_it_wrote(project):
    store, path, _ = project
    entry = last_render(store, "CLAUDE.md", store.identity.checkout)
    assert entry is not None and "Plain technical English." in entry.interior


def test_an_edited_block_becomes_a_proposal_and_blocks_the_overwrite(project):
    store, path, base = project
    _edit(path, "Plain technical English.", "Plain technical English, short sentences.")
    before = path.read_bytes()
    code, _, err = _run(["switch", "--to", "claude-code", *base])
    assert code == EX_CONFLICT and "voice" in err
    assert path.read_bytes() == before, "the edit is never overwritten"
    proposal = _proposals(store)["voice"]
    assert proposal.origin["rule"] == "edited-block"
    assert proposal.record.data["body"] == "Plain technical English, short sentences."
    assert _run(["workspace", "accept", "voice", *base[:4]])[0] == EX_OK
    assert _run(["switch", "--to", "claude-code", *base])[0] == EX_OK
    [voice] = [r for r in ingest_region(path.read_text(encoding="utf-8")) if r.id == "voice"]
    assert voice.data["body"] == "Plain technical English, short sentences."


def test_brief_edits_map_to_status_new_work_focus_and_a_kept_note(project):
    store, path, base = project
    task = next(r.id for r in store.records() if r.kind == "work-item")
    _edit(path, f"- [open] Write the tests ({task})", f"- [done] Write the tests ({task})\n"
          "- [open] Write the docs\nRemember the Windows runner is slow.")
    _edit(path, "Goal: Ship back-flow", "Goal: Ship back-flow and the docs")
    assert _run(["switch", "--to", "claude-code", *base])[0] == EX_CONFLICT
    rules = {r.origin["rule"]: r.record for r in store.proposals()}
    assert rules["brief-work"].id == task and rules["brief-work"].data["status"] == "done"
    assert rules["brief-new-work"].data == {"title": "Write the docs", "status": "open"}
    assert rules["brief-focus"].data["goal"] == "Ship back-flow and the docs"
    assert rules["brief-focus"].data["branch"] == "main"
    assert "Windows runner is slow" in rules["unmapped-edit"].data["text"]


def test_a_removed_block_proposes_retirement(project):
    store, path, base = project
    text = path.read_text(encoding="utf-8")
    start = text.index('<!-- canon:block id="voice"')
    end = text.index("<!-- canon:block", start + 1)
    path.write_text(text[:start] + text[end:], encoding="utf-8", newline="\n")
    assert _run(["switch", "--to", "claude-code", *base])[0] == EX_CONFLICT
    retire = _proposals(store)["voice"]
    assert retire.origin["rule"] == "removed-block"
    assert retire.record.temporal.valid_until is not None
    assert _run(["workspace", "accept", "voice", *base[:4]])[0] == EX_OK
    assert _run(["switch", "--to", "claude-code", *base])[0] == EX_OK
    assert "voice" not in {r.id for r in ingest_region(path.read_text(encoding="utf-8"))}


def test_a_rejected_edit_is_decided_and_the_switch_overwrites_it(project):
    store, path, base = project
    _edit(path, "Plain technical English.", "Anything goes.")
    assert _run(["switch", "--to", "claude-code", *base])[0] == EX_CONFLICT
    assert _run(["workspace", "reject", "voice", "--reason", "not ours", *base[:4]])[0] == EX_OK
    assert _run(["switch", "--to", "claude-code", *base])[0] == EX_OK
    assert "Anything goes." not in path.read_text(encoding="utf-8")


def test_a_stale_render_with_no_edit_is_overwritten_without_proposals(project):
    store, path, base = project
    store.put(authoring.work_item(store, title="A later task"))
    assert _run(["switch", "--to", "claude-code", *base])[0] == EX_OK
    assert store.proposals() == []
    assert "A later task" in path.read_text(encoding="utf-8")


def test_a_broken_region_keeps_the_changed_text_as_one_note(project):
    store, path, base = project
    _edit(path, "Plain technical English.", "Plain.\n<!-- canon:block oops -->")
    assert _run(["switch", "--to", "claude-code", *base])[0] == EX_CONFLICT
    [note] = [r for r in store.proposals() if r.origin["rule"] == "unparseable-region"]
    assert "Plain." in note.record.data["text"]


def test_without_a_ledger_only_additions_count(project, tmp_path):
    store, path, base = project
    fresh = tmp_path / "other-store"
    other = ["--workspace", base[1], "--store", str(fresh), "--home", base[5]]
    code, out, _ = _run(["--json", "workspace", "pull", "--from", "claude-code", *other])
    report = json.loads(out)["data"]["report"]
    rules = {p["rule"] for p in report["proposed"]}
    assert "new-block" in rules and "removed-block" not in rules


def test_a_secret_pasted_into_the_region_is_scrubbed_before_it_is_proposed(project):
    store, path, base = project
    canary = "ghp_" + "k" * 36
    _edit(path, "Plain technical English.", f"Plain technical English. Token {canary}.")
    assert _run(["switch", "--to", "claude-code", *base])[0] == EX_CONFLICT
    stored = (store.project_dir() / "proposed.jsonl").read_text(encoding="utf-8")
    assert canary not in stored and "[REDACTED:github-token]" in stored


def test_pull_dry_run_reports_and_writes_nothing(project):
    store, path, base = project
    _edit(path, "Plain technical English.", "Edited.")
    code, out, _ = _run(["workspace", "pull", "--from", "claude-code", "--dry-run", *base])
    assert code == EX_OK and "would propose 1 records" in out
    assert store.proposals() == []


def test_removing_another_projects_line_never_drops_this_projects_task(project):
    from canon.workspace.backflow_brief import brief_edits

    store, _, _ = project
    task = next(r for r in store.records() if r.kind == "work-item")
    foreign = f"- [open] Their task ({task.id}) [from prj_{'0' * 32}]"
    base = f"### Open work\n- [open] Write the tests ({task.id})\n{foreign}"
    actual = f"### Open work\n- [open] Write the tests ({task.id})"
    edits, _ = brief_edits(actual, base, 1, store.records(), has_base=True)
    assert [e for e in edits if e.rule == "brief-removed-work"] == []
    own_removed, _ = brief_edits("### Open work", base, 1, store.records(), has_base=True)
    assert [(e.rid, e.data["status"]) for e in own_removed] == [(task.id, "dropped")]
