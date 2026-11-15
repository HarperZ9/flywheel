"""The transcript importers: proposals with provenance to file and line, a
declared-loss ledger that refuses what it cannot name, the project check, and
the secret controls that keep a planted canary out of every stored byte."""
from __future__ import annotations

import json

import pytest

from canon.workspace.brief import make_brief
from canon.workspace.identity import derive_identity
from canon.workspace.import_common import ImportRefused
from canon.workspace.import_write import import_session
from canon.workspace.pool import project_pool
from canon.workspace.store import ProjectStore
from canon.workspace.targets import target_for

from ._import_helpers import every_stored_byte, materialize, planted
from ._workspace_helpers import init_repo

REMOTE = "https://github.com/example/report-tool.git"


@pytest.fixture()
def project(tmp_path):
    repo = init_repo(tmp_path / "repo", REMOTE)
    ident = derive_identity(repo)
    return repo, ident, ProjectStore(tmp_path / "store", ident)


def _claude(tmp_path, project, **kw):
    repo, ident, store = project
    path = materialize(tmp_path, "claude_code_session.jsonl", root=repo)
    return path, import_session(ident, store, str(path), source_format="claude-code", **kw)


def _codex(tmp_path, project, remote=REMOTE, **kw):
    repo, ident, store = project
    path = materialize(tmp_path, "codex_rollout.jsonl", root=repo, remote=remote)
    return path, import_session(ident, store, str(path), source_format="codex", **kw)


def _by_rule(store):
    rows = sorted(store.proposals(), key=lambda r: r.record.provenance.create_ord)
    return {r.origin["rule"]: [x for x in rows if x.origin["rule"] == r.origin["rule"]]
            for r in rows}


def test_claude_import_proposes_focus_plan_decisions_and_failures(tmp_path, project):
    _, report = _claude(tmp_path, project)
    store = project[2]
    rules = _by_rule(store)
    focus = rules["session-summary"][0].record
    assert focus.data["goal"] == "Add a JSON output flag to the report command"
    assert focus.data["branch"] == "feat/json-report"
    assert focus.data["areas"] == ["src/report/cli.py"]
    plan = [(r.record.data["title"], r.record.data["status"]) for r in rules["plan-tool"]]
    assert plan == [("Add --json to the shared parser", "in-progress"),
                    ("Document the flag", "open")]
    decisions = [r.record.data["decision"] for r in rules["decision-phrase"]]
    assert "add the flag to the shared parser" in decisions
    failed = rules["failed-phrase"][0].record.data["rejected_alternatives"][0]
    assert failed == {"option": "adding a subparser",
                      "reason": "it clashed with the legacy report command"}
    assert report["project_check"] == {"status": "match", "by": "working_directory"}
    assert not store.records(), "an import writes proposals only"


def test_every_proposal_points_at_its_source_file_and_line(tmp_path, project):
    path, report = _claude(tmp_path, project)
    lines = path.read_text(encoding="utf-8").split("\n")
    for row in project[2].proposals():
        origin = row.origin
        assert origin["source"] == path.name
        assert origin["source_sha256"] == report["source"]["sha256"]
        source_line = lines[origin["line"] - 1]
        if origin["rule"] == "plan-tool":
            assert "TodoWrite" in source_line
        elif origin["rule"] == "failed-phrase":
            assert "tried" in source_line or "work" in source_line


def test_the_ledger_counts_every_declared_drop(tmp_path, project):
    _, report = _claude(tmp_path, project)
    drops = report["declared_drops"]
    assert drops["thinking"] == 1 and drops["sidechain"] == 1
    assert drops["meta-entry"] == 2 and drops["meta-message"] == 1
    assert drops["superseded-plan"] == 1 and drops["closed-plan-step"] == 1
    assert drops["outside-area"] == 1 and drops["image"] == 1
    assert drops["tool-output"] == 3 and drops["tool-call"] == 1
    assert set(report["declared_drop_meanings"]) == set(drops)
    texts = json.dumps([r.record.data for r in project[2].proposals()])
    assert "subagent" not in texts and "never propose this" not in texts


def test_an_unknown_entry_type_refuses_unless_declared(tmp_path, project):
    repo, ident, store = project
    path = materialize(tmp_path, "claude_code_session.jsonl", root=repo)
    path.write_text(path.read_text(encoding="utf-8") + '{"type":"hologram","x":1}\n',
                    encoding="utf-8")
    with pytest.raises(ImportRefused, match="hologram") as err:
        import_session(ident, store, str(path), source_format="claude-code")
    assert err.value.code == "undeclared_loss"
    assert store.proposals() == []
    report = import_session(ident, store, str(path), source_format="claude-code",
                            user_drops=("entry type 'hologram'",))
    assert report["user_declared_drops"] == {"entry type 'hologram'": 1}


def test_secret_control_no_canary_reaches_a_record_report_brief_or_region(tmp_path, project):
    repo, ident, store = project
    _, claude = _claude(tmp_path, project)
    _, codex = _codex(tmp_path, project)
    for row in store.proposals():
        store.decide(row.record.id, accept=True, reason="test")
    brief = make_brief(ident, project_pool(store), target_for("markdown")).text
    haystack = "\n".join([every_stored_byte(store.root), json.dumps(claude),
                          json.dumps(codex), brief])
    leaked = [name for name, value in planted().items() if value in haystack]
    assert leaked == []
    assert "[REDACTED:" in brief
    redacted = set(claude["secrets_redacted"]) | set(codex["secrets_redacted"])
    assert {"openai-key", "connection-string", "bearer-header", "aws-access-key",
            "private-key", "json-secret", "github-token", "anthropic-key"} <= redacted


def test_codex_import_reads_the_plan_the_patch_and_the_messages(tmp_path, project):
    _, report = _codex(tmp_path, project)
    rules = _by_rule(project[2])
    assert report["project_check"]["status"] == "match"
    assert report["project_check"]["by"] == "repository_url"
    plan = [(r.record.data["title"], r.record.data["status"]) for r in rules["plan-tool"]]
    assert plan == [("Add --json to export", "in-progress"), ("Update the changelog", "open")]
    focus = rules["first-prompt"][0].record.data
    assert focus["areas"] == ["src/export.py", "tests/test_export_json.py"]
    assert focus["branch"] == "feat/json-export"
    assert any(r.record.data["decision"] == "keep the CSV writer"
               for r in rules["decision-phrase"])
    drops = report["declared_drops"]
    assert drops["injected-context"] == 1 and drops["event"] == 2
    assert drops["reasoning"] == 1 and drops["session-state"] == 1
    assert drops["system-message"] == 1 and drops["superseded-plan"] == 1


def test_a_rollout_from_another_repository_is_refused(tmp_path, project):
    with pytest.raises(ImportRefused, match="github.com/example/other-tool") as err:
        _codex(tmp_path, project, remote="https://github.com/example/other-tool.git")
    assert err.value.code == "isolation_refused"
    assert project[2].proposals() == []
    _, report = _codex(tmp_path, project, remote="https://github.com/example/other-tool.git",
                       accept_foreign=True)
    assert report["project_check"]["status"] == "mismatch"


def test_an_untagged_rollout_is_an_unsupported_format(tmp_path, project):
    repo, ident, store = project
    path = tmp_path / "old-rollout.jsonl"
    path.write_text('{"id":"x","timestamp":"t","instructions":null}\n'
                    '{"type":"message","role":"user","content":[]}\n', encoding="utf-8")
    with pytest.raises(ImportRefused, match="0.32") as err:
        import_session(ident, store, str(path), source_format="codex")
    assert err.value.code == "unsupported_format"


def test_reimport_is_idempotent_and_a_rejection_is_remembered(tmp_path, project):
    store = project[2]
    _claude(tmp_path, project)
    first = sorted(r.record.id for r in store.proposals())
    victim = next(r.record.id for r in store.proposals() if r.origin["rule"] == "todo-marker")
    store.decide(victim, accept=False, reason="not a real task")
    _, report = _claude(tmp_path, project)
    assert sorted(r.record.id for r in store.proposals()) == sorted(set(first) - {victim})
    assert [p["id"] for p in report["previously_rejected"]] == [victim]


def test_a_truncated_last_line_is_declared_and_a_broken_middle_line_refuses(tmp_path, project):
    repo, ident, store = project
    path = materialize(tmp_path, "claude_code_session.jsonl", root=repo)
    path.write_text(path.read_text(encoding="utf-8") + '{"type":"user","mess', encoding="utf-8")
    report = import_session(ident, store, str(path), source_format="claude-code", dry_run=True)
    assert report["source"]["truncated_tail"] and report["declared_drops"]["truncated-tail"] == 1
    lines = path.read_text(encoding="utf-8").split("\n")
    path.write_text("\n".join([lines[0], "{not json", *lines[1:]]), encoding="utf-8")
    with pytest.raises(ImportRefused, match="line 2"):
        import_session(ident, store, str(path), source_format="claude-code")


def _cli(argv):
    import io

    from canon.cli import run_cli
    stdout, stderr = io.StringIO(), io.StringIO()
    code = run_cli(argv, stdin=None, stdout=stdout, stderr=stderr, environ={})
    return code, stdout.getvalue(), stderr.getvalue()


def test_the_import_accept_reject_commands_end_to_end(tmp_path, project):
    repo, ident, store = project
    path = materialize(tmp_path, "codex_rollout.jsonl", root=repo, remote=REMOTE)
    base = ["--workspace", str(repo), "--store", str(store.root)]
    code, out, _ = _cli(["workspace", "import", "--from", "codex", str(path), *base])
    assert code == 0 and "project check: match by repository_url" in out
    assert "secrets redacted: " in out and "github-token" in out
    plan_id = next(r.record.id for r in store.proposals()
                   if r.record.data.get("title") == "Add --json to export")
    code, out, _ = _cli(["handoff", "--to", "markdown", *base])
    assert "Add --json to export" not in out, "a proposal is not in the brief"
    assert _cli(["workspace", "accept", plan_id, *base])[0] == 0
    code, out, _ = _cli(["handoff", "--to", "markdown", *base])
    assert "Add --json to export" in out
    other = next(r.record.id for r in store.proposals())
    code, _, err = _cli(["workspace", "reject", other, *base])
    assert code != 0 and "reason" in err
    assert _cli(["workspace", "reject", other, "--reason", "noise", *base])[0] == 0
    assert other not in {r.record.id for r in store.proposals()}


def test_an_import_refusal_surfaces_its_code(tmp_path, project):
    repo, ident, store = project
    path = materialize(tmp_path, "codex_rollout.jsonl", root=repo,
                       remote="https://github.com/example/other-tool.git")
    code, out, _ = _cli(["--json", "workspace", "import", "--from", "codex", str(path),
                         "--workspace", str(repo), "--store", str(store.root)])
    assert json.loads(out)["failure_code"] == "isolation_refused"
