"""`canon workspace` end to end through run_cli: identity, listing, promotion,
and the isolation refusal surfacing as a stable failure code."""
from __future__ import annotations

import io
import json

from canon.cli import run_cli
from canon.exit_codes import EX_OK, EX_SECURITY, EX_USAGE
from canon.workspace.identity import derive_identity
from canon.workspace.store import ProjectStore

from ._workspace_helpers import block, init_repo


def _run(argv, environ=None):
    stdout, stderr = io.StringIO(), io.StringIO()
    code = run_cli(argv, stdin=None, stdout=stdout, stderr=stderr,
                   environ=environ or {})
    return code, stdout.getvalue(), stderr.getvalue()


def _setup(tmp_path):
    store = tmp_path / "store"
    repo_a = init_repo(tmp_path / "a", "https://github.com/o/a")
    repo_b = init_repo(tmp_path / "b", "https://github.com/o/b")
    ProjectStore(store, derive_identity(repo_a)).put(block("a-voice", "Only in A.", 1))
    return store, repo_a, repo_b


def test_workspace_id_reports_a_path_clean_identity(tmp_path):
    store, repo_a, _ = _setup(tmp_path)
    code, out, _ = _run(["--json", "workspace", "id", "--workspace", str(repo_a),
                         "--store", str(store)])
    assert code == EX_OK
    data = json.loads(out)["data"]
    assert data["identity"]["key"] == "github.com/o/a"
    assert data["accepted"] == 1
    assert str(tmp_path) not in out


def test_workspace_list_shows_only_this_projects_records(tmp_path):
    store, repo_a, repo_b = _setup(tmp_path)
    code, out_b, _ = _run(["workspace", "list", "--workspace", str(repo_b),
                           "--store", str(store)])
    assert code == EX_OK
    assert "Only in A." not in out_b and "a-voice" not in out_b
    code, out_a, _ = _run(["workspace", "list", "--workspace", str(repo_a),
                           "--store", str(store)])
    assert "a-voice" in out_a


def test_the_store_root_can_come_from_the_environment(tmp_path):
    store, repo_a, _ = _setup(tmp_path)
    code, out, _ = _run(["workspace", "list", "--workspace", str(repo_a)],
                        environ={"CANON_STORE": str(store)})
    assert code == EX_OK and "a-voice" in out


def test_promote_needs_a_reason_and_is_logged(tmp_path):
    store, repo_a, repo_b = _setup(tmp_path)
    code, _, err = _run(["workspace", "promote", "a-voice", "--reason", " ",
                         "--workspace", str(repo_a), "--store", str(store)])
    assert code == EX_USAGE and "reason" in err
    code, out, _ = _run(["workspace", "promote", "a-voice", "--reason", "house style",
                         "--workspace", str(repo_a), "--store", str(store)])
    assert code == EX_OK and "global" in out
    log = ProjectStore(store, derive_identity(repo_a)).log_entries()
    assert log[-1]["action"] == "promote" and log[-1]["reason"] == "house style"


def test_a_misfiled_row_fails_the_command_with_the_isolation_code(tmp_path):
    store, repo_a, repo_b = _setup(tmp_path)
    a_store = ProjectStore(store, derive_identity(repo_a))
    b_store = ProjectStore(store, derive_identity(repo_b))
    b_store.put(block("b-voice", "B body.", 1))
    line = (a_store.project_dir() / "records.jsonl").read_text(encoding="utf-8")
    target = b_store.project_dir() / "records.jsonl"
    target.write_text(target.read_text(encoding="utf-8") + line, encoding="utf-8")
    code, out, _ = _run(["--json", "workspace", "list", "--workspace", str(repo_b),
                         "--store", str(store)])
    assert code == EX_SECURITY
    payload = json.loads(out)
    assert payload["failure_code"] == "isolation_refused"
    assert "Only in A." not in out


def _ws(tmp_path, *args):
    store, repo_a, _ = _setup(tmp_path)
    return _run(["--json", "workspace", *args, "--workspace", str(repo_a),
                 "--store", str(store)])


def test_the_authoring_commands_write_workspace_state(tmp_path):
    store, repo, _ = _setup(tmp_path)
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/feat/x\n", encoding="utf-8")
    base = ["--workspace", str(repo), "--store", str(store)]
    assert _run(["workspace", "focus", "--goal", "Ship handoff", "--area", "src/canon",
                 *base])[0] == EX_OK
    assert _run(["workspace", "task", "Write importer", *base])[0] == EX_OK
    assert _run(["workspace", "decide", "--title", "Row format", "--decision", "JSONL",
                 "--context", "diffable", "--reject", "SQLite", "binary diffs",
                 *base])[0] == EX_OK
    assert _run(["workspace", "constraint", "Tests run on Windows", "--quirk",
                 *base])[0] == EX_OK
    records = {r.kind: r for r in ProjectStore(store, derive_identity(repo)).records()}
    assert records["workspace-focus"].data["branch"] == "feat/x"
    assert records["work-item"].data["status"] == "open"
    assert records["adr-decision"].data["rejected_alternatives"] == [
        {"option": "SQLite", "reason": "binary diffs"}]
    assert records["environment-constraint"].data["category"] == "quirk"


def test_set_status_updates_a_work_item_in_place(tmp_path):
    store, repo, _ = _setup(tmp_path)
    base = ["--workspace", str(repo), "--store", str(store)]
    code, out, _ = _run(["--json", "workspace", "task", "Port parser", *base])
    rid = json.loads(out)["data"]["record"]["record"]["id"]
    assert _run(["workspace", "set-status", rid, "done", *base])[0] == EX_OK
    items = [r for r in ProjectStore(store, derive_identity(repo)).records()
             if r.kind == "work-item"]
    assert [(r.id, r.data["status"]) for r in items] == [(rid, "done")]


def test_an_invalid_status_is_a_usage_error_and_writes_nothing(tmp_path):
    code, out, _ = _ws(tmp_path, "task", "Something", "--status", "finished")
    assert code == EX_USAGE
    assert json.loads(out)["failure_code"] == "invalid_args"
    assert "status" in json.loads(out)["message"]
