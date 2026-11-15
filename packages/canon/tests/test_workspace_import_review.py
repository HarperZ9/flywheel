"""Importer behaviour a review found missing: identity-based project checks,
thread-keyed Codex ids, the Claude task tools, host-written user text, rolled
back and rewound turns, foreign summaries, newer entry types, and the line
reader's truncation rule. Every session here is synthetic."""
from __future__ import annotations

import json

import pytest

from canon.workspace.identity import derive_identity
from canon.workspace.import_common import ImportRefused
from canon.workspace.import_write import import_session
from canon.workspace.store import ProjectStore

from ._workspace_helpers import init_repo

REMOTE = "https://github.com/example/report-tool.git"


@pytest.fixture()
def project(tmp_path):
    repo = init_repo(tmp_path / "repo", REMOTE)
    ident = derive_identity(repo)
    return tmp_path, repo, ident, ProjectStore(tmp_path / "store", ident)


def _write(tmp_path, name, rows):
    path = tmp_path / name
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def _claude(repo, uid, role, content, parent=None, **extra):
    return {"type": role, "uuid": uid, "parentUuid": parent, "isSidechain": False,
            "cwd": str(repo), "sessionId": "5b0c7f1e-2a3b-4c5d-8e9f-0a1b2c3d4e5f",
            "message": {"role": role, "content": content}, **extra}


def _meta(repo, thread="root-1", session="root-1", cwd=None):
    return {"type": "session_meta", "payload": {"id": thread, "session_id": session,
            "cwd": str(cwd or repo), "git": {"repository_url": REMOTE}}}


def _item(payload):
    return {"type": "response_item", "payload": payload}


def _umsg(text, role="user"):
    kind = "input_text" if role == "user" else "output_text"
    return _item({"type": "message", "role": role, "content": [{"type": kind, "text": text}]})


def _run(project, name, rows, fmt, **kw):
    tmp_path, _repo, ident, store = project
    return import_session(ident, store, str(_write(tmp_path, name, rows)),
                          source_format=fmt, **kw)


def test_a_session_from_a_nested_repository_is_another_project(project):
    tmp_path, repo, ident, store = project
    inner = init_repo(repo / "vendor" / "inner", "https://github.com/o/inner")
    rows = [_claude(inner, "u1", "user", "TODO: patch the vendored parser")]
    with pytest.raises(ImportRefused) as err:
        _run(project, "nested.jsonl", rows, "claude-code")
    assert err.value.code == "isolation_refused"


def test_a_session_from_a_submodule_is_another_project(project):
    tmp_path, repo, ident, store = project
    module_git = repo / ".git" / "modules" / "lib"
    module_git.mkdir(parents=True)
    (module_git / "config").write_text('[remote "origin"]\n\turl = https://github.com/o/lib\n',
                                       encoding="utf-8")
    sub = repo / "lib"
    sub.mkdir()
    (sub / ".git").write_text("gitdir: ../.git/modules/lib\n", encoding="utf-8")
    rows = [_claude(sub, "u1", "user", "TODO: bump the library")]
    with pytest.raises(ImportRefused, match="another working directory"):
        _run(project, "submodule.jsonl", rows, "claude-code")


def test_a_session_from_a_sibling_worktree_is_this_project(project):
    tmp_path, repo, ident, store = project
    gitdir = repo / ".git" / "worktrees" / "feature"
    gitdir.mkdir(parents=True)
    (gitdir / "commondir").write_text("../..\n", encoding="utf-8")
    worktree = tmp_path / "feature"
    worktree.mkdir()
    (worktree / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
    report = _run(project, "wt.jsonl", [_claude(worktree, "u1", "user", "TODO: x")],
                  "claude-code")
    assert report["project_check"] == {"status": "match", "by": "working_directory"}


def test_a_file_edited_inside_a_nested_repository_is_not_an_area(project):
    tmp_path, repo, ident, store = project
    init_repo(repo / "vendor" / "inner", "https://github.com/o/inner")
    edit = {"type": "tool_use", "id": "t1", "name": "Edit",
            "input": {"file_path": str(repo / "vendor" / "inner" / "x.py")}}
    rows = [_claude(repo, "u1", "user", "Fix it"), _claude(repo, "a1", "assistant", [edit], "u1")]
    report = _run(project, "areas.jsonl", rows, "claude-code")
    assert report["declared_drops"]["outside-area"] == 1


def test_a_secret_shaped_session_id_is_dropped_not_stored(project):
    tmp_path, repo, ident, store = project
    row = _claude(repo, "u1", "user", "TODO: ship it")
    row["sessionId"] = "sk-ant-api03-" + "b" * 30
    report = _run(project, "sid.jsonl", [row], "claude-code")
    assert report["declared_drops"]["session-id"] == 1
    stored = (store.project_dir() / "proposed.jsonl").read_text(encoding="utf-8")
    assert "b" * 30 not in stored


def test_sub_agent_rollouts_that_share_a_session_id_keep_their_own_ids(project):
    _, repo, _, store = project
    parent = _run(project, "rollout-a.jsonl",
                  [_meta(repo, "root-1"), _umsg("TODO: update the changelog")], "codex")
    child = _run(project, "rollout-b.jsonl",
                 [_meta(repo, "child-2"), _umsg("TODO: delete the flaky retry test")], "codex")
    pid = next(p["id"] for p in parent["proposed"] if p["rule"] == "todo-marker")
    cid = next(p["id"] for p in child["proposed"] if p["rule"] == "todo-marker")
    assert pid != cid


def test_an_accepted_id_from_another_file_is_never_replaced(project):
    _, repo, _, store = project
    first = _run(project, "rollout-a.jsonl", [_meta(repo), _umsg("TODO: one")], "codex")
    pid = next(p["id"] for p in first["proposed"] if p["rule"] == "todo-marker")
    store.decide(pid, accept=True, reason="real")
    second = _run(project, "rollout-copy.jsonl", [_meta(repo), _umsg("TODO: two")], "codex")
    cid = next(p["id"] for p in second["proposed"] if p["rule"] == "todo-marker")
    store.decide(cid, accept=True, reason="real")
    titles = sorted(r.data["title"] for r in store.records() if r.kind == "work-item")
    assert titles == ["one", "two"]


def test_the_claude_task_tools_are_read_as_the_plan(project):
    _, repo, _, store = project
    create = [{"type": "tool_use", "id": "t1", "name": "TaskCreate",
               "input": {"subject": "Add --json to the parser", "activeForm": "Adding"}},
              {"type": "tool_use", "id": "t2", "name": "TaskCreate",
               "input": {"subject": "Write the docs"}},
              {"type": "tool_use", "id": "t3", "name": "TaskCreate", "input": {"subject": "Old"}}]
    results = [{"type": "tool_result", "tool_use_id": f"t{n}",
                "content": f"Task #{n} created successfully: x"} for n in (1, 2, 3)]
    update = [{"type": "tool_use", "id": "t4", "name": "TaskUpdate",
               "input": {"taskId": "1", "status": "in_progress"}},
              {"type": "tool_use", "id": "t5", "name": "TaskUpdate",
               "input": {"taskId": "3", "status": "deleted"}}]
    rows = [_claude(repo, "u1", "user", "Add a flag"),
            _claude(repo, "a1", "assistant", create, "u1"),
            _claude(repo, "u2", "user", results, "a1"),
            _claude(repo, "a2", "assistant", update, "u2")]
    report = _run(project, "tasks.jsonl", rows, "claude-code")
    plan = sorted((r.record.data["title"], r.record.data["status"])
                  for r in store.proposals() if r.origin["rule"] == "plan-tool")
    assert plan == [("Add --json to the parser", "in-progress"), ("Write the docs", "open")]
    assert report["declared_drops"]["tool-call"] == 0
    assert report["declared_drops"]["closed-plan-step"] == 1


def test_codex_written_user_text_is_not_mined(project):
    _, repo, _, store = project
    rows = [_meta(repo),
            _umsg("<user_shell_command>\n<command>cat NOTES.md</command>\nOutput:\n"
                  "TODO: drop the legacy exporter\nWe decided to vendor libfoo.\n"
                  "</user_shell_command>"),
            _umsg("<skill>\n- [ ] bump the version\n</skill>"),
            _umsg('<subagent_notification>{"message": "We went with the retry wrapper."}'
                  "</subagent_notification>"),
            _umsg("<turn_aborted>\nTODO: check what was left half done\n</turn_aborted>"),
            _umsg("<codex_internal_context>TODO: internal</codex_internal_context>"),
            _umsg("Ship the exporter")]
    report = _run(project, "rollout-inj.jsonl", rows, "codex")
    assert [p["rule"] for p in report["proposed"]] == ["first-prompt"]
    assert report["declared_drops"]["tool-output"] == 1
    assert report["declared_drops"]["injected-context"] == 4
    [focus] = store.proposals()
    assert focus.record.data["goal"] == "Ship the exporter"


def test_claude_written_user_text_is_not_mined(project):
    _, repo, _, store = project
    rows = [_claude(repo, "u1", "user", "<command-name>/clear</command-name>"),
            _claude(repo, "u2", "user", "<bash-input>cat notes.md</bash-input>", "u1"),
            _claude(repo, "u3", "user", "<bash-stdout>TODO: drop the exporter\nWe decided "
                    "to vendor libfoo.</bash-stdout><bash-stderr></bash-stderr>", "u2"),
            _claude(repo, "u4", "user", "Summary text. TODO: revisit caching", "u3",
                    isCompactSummary=True),
            _claude(repo, "u5", "user", "This session is being continued from a previous "
                    "conversation. We went with the old parser.", "u4"),
            _claude(repo, "u6", "user", "<system-reminder>TODO: never this</system-reminder>"
                    "Fix the login test", "u5")]
    report = _run(project, "local.jsonl", rows, "claude-code")
    assert [p["rule"] for p in report["proposed"]] == ["first-prompt"]
    [focus] = store.proposals()
    assert focus.record.data["goal"] == "Fix the login test"
    drops = report["declared_drops"]
    assert drops["local-command"] == 3 and drops["compact-summary"] == 2
    assert drops["injected-block"] == 1


def test_a_rolled_back_codex_turn_is_not_mined(project):
    _, repo, _, store = project
    rows = [_meta(repo), _umsg("Speed up the export"), _umsg("Then remove the writer"),
            _umsg("We decided to drop the CSV writer. TODO: delete csv_writer.py", "assistant"),
            {"type": "event_msg", "payload": {"type": "thread_rolled_back", "num_turns": 1}},
            _umsg("Keep the writer and stream rows instead")]
    report = _run(project, "rollout-rb.jsonl", rows, "codex")
    assert [p["rule"] for p in report["proposed"]] == ["first-prompt"]
    assert report["declared_drops"]["rolled-back"] == 2
    assert report["declared_drops"]["event"] == 0


def test_an_abandoned_claude_rewind_branch_is_not_mined(project):
    _, repo, _, store = project
    text = [{"type": "text", "text": "We decided to drop the CSV writer. TODO: delete it"}]
    keep = [{"type": "text", "text": "We decided to stream rows through the writer."}]
    rows = [_claude(repo, "u1", "user", "Speed up the export"),
            _claude(repo, "a1", "assistant", [{"type": "text", "text": "Profiled."}], "u1"),
            _claude(repo, "u2", "user", "Then remove it", "a1"),
            _claude(repo, "a2", "assistant", text, "u2"),
            _claude(repo, "u3", "user", "Keep the writer and stream rows", "a1"),
            _claude(repo, "a3", "assistant", keep, "u3")]
    report = _run(project, "rewind.jsonl", rows, "claude-code")
    decisions = [r.record.data["decision"] for r in store.proposals()
                 if r.record.kind == "adr-decision"]
    assert decisions == ["stream rows through the writer"]
    assert report["declared_drops"]["abandoned-branch"] == 2


def test_a_summary_of_another_session_never_becomes_the_focus(project):
    _, repo, _, store = project
    rows = [{"type": "summary", "summary": "Migrate billing", "leafUuid": "elsewhere"},
            _claude(repo, "u1", "user", "Fix the flaky login test")]
    report = _run(project, "summary.jsonl", rows, "claude-code")
    [focus] = store.proposals()
    assert focus.record.data["goal"] == "Fix the flaky login test"
    assert report["declared_drops"]["foreign-summary"] == 1
    rows.append({"type": "ai-title", "aiTitle": "Fix flaky login test",
                 "sessionId": rows[1]["sessionId"]})
    _run(project, "titled.jsonl", rows, "claude-code")
    assert store.proposals()[0].record.data["goal"] == "Fix flaky login test"


@pytest.mark.parametrize("item", [
    {"type": "configuration_update", "reasoning": {"effort": "high"}},
    {"type": "compaction_summary", "encrypted_content": "gAAA"},
    {"type": "ghost_snapshot", "ghost_commit": {"id": "abc"}},
])
def test_codex_items_the_current_source_writes_are_declared(project, item):
    _, repo, _, _ = project
    _run(project, "rollout-types.jsonl", [_meta(repo), _umsg("TODO: tag"), _item(item)],
         "codex", dry_run=True)


@pytest.mark.parametrize("kind", ["agent-setting", "pr-link"])
def test_claude_entry_types_seen_in_real_files_are_declared(project, kind):
    _, repo, _, _ = project
    report = _run(project, "types.jsonl", [_claude(repo, "u1", "user", "TODO: x"),
                                           {"type": kind, "uuid": "x1"}],
                  "claude-code", dry_run=True)
    assert report["declared_drops"]["meta-entry"] == 1


def test_a_relative_patch_path_resolves_against_the_session_cwd(project):
    _, repo, _, store = project
    api = repo / "packages" / "api"
    api.mkdir(parents=True)
    patch = _item({"type": "custom_tool_call", "name": "apply_patch", "call_id": "c1",
                   "input": "*** Begin Patch\n*** Update File: src/handler.py\n*** End Patch"})
    _run(project, "rollout-cwd.jsonl", [_meta(repo, cwd=api), _umsg("Fix it"), patch], "codex")
    [focus] = store.proposals()
    assert focus.record.data["areas"] == ["packages/api/src/handler.py"]


def test_a_malformed_last_line_that_ends_in_a_newline_refuses(project):
    tmp_path, repo, ident, store = project
    good = json.dumps(_claude(repo, "u1", "user", "TODO: x"))
    path = tmp_path / "corrupt.jsonl"
    path.write_text(good + '\n{"type":"user" broken}\n', encoding="utf-8")
    with pytest.raises(ImportRefused, match="line 2 is not JSON"):
        import_session(ident, store, str(path), source_format="claude-code", dry_run=True)
    path.write_text(good + '\n{"type":"user"', encoding="utf-8")
    report = import_session(ident, store, str(path), source_format="claude-code", dry_run=True)
    assert report["source"]["truncated_tail"] is True


def test_drop_type_takes_the_bare_type_name_and_the_refusal_says_how(project):
    _, repo, _, _ = project
    rows = [_claude(repo, "u1", "user", "TODO: x"), {"type": "brand-new-entry"}]
    with pytest.raises(ImportRefused, match="--drop-type brand-new-entry"):
        _run(project, "new.jsonl", rows, "claude-code", dry_run=True)
    report = _run(project, "new.jsonl", rows, "claude-code", dry_run=True,
                  user_drops=("brand-new-entry",))
    assert report["user_declared_drops"] == {"entry type 'brand-new-entry'": 1}
