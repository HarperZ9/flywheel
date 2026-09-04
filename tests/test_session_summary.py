"""The summary must derive what it can and refuse to let a claim outrun the tree."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.session_summary import (  # noqa: E402
    QUESTIONS, SCHEMA, SCOPES, build_session_summary, collect_evidence,
    derive_answers, find_disagreements, render_markdown,
)

SCRIPT = ROOT / "scripts" / "run_session_summary.py"


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(root), check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A two-commit repository with no remote, so every derived signal is reachable."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "work")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "test")
    (root / "kept.py").write_text("value = 1\n", encoding="utf-8")
    _git(root, "add", "kept.py")
    _git(root, "commit", "-qm", "first: add the value")
    (root / "kept.py").write_text("value = 2  # TODO: pick the real value\n", encoding="utf-8")
    _git(root, "commit", "-qam", "second: change the value")
    return root


def test_evidence_reads_the_window_the_scope_names(repo: Path) -> None:
    task = collect_evidence(repo, scope="task")
    assert task["window"] == "HEAD~1..HEAD"
    assert [row["subject"] for row in task["commits"]] == ["second: change the value"]
    assert task["changed_files"] == ["kept.py"]
    assert task["branch"] == "work"
    # No origin/main and no main in this repository, so the goal window has no base
    # and reports nothing rather than silently falling back to the whole history.
    assert collect_evidence(repo, scope="goal")["window"] == ""
    with pytest.raises(ValueError, match="unknown scope"):
        collect_evidence(repo, scope="epoch")


def test_only_markers_this_window_added_are_reported(repo: Path) -> None:
    markers = collect_evidence(repo, scope="task")["markers"]
    assert [row["path"] for row in markers] == ["kept.py"]
    assert "pick the real value" in markers[0]["text"]
    (repo / "kept.py").write_text("value = 3\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "third: drop the marker")
    # The marker is still in history but was not added by HEAD~1..HEAD, so a
    # summary of this commit must not re-report someone else's debt.
    assert collect_evidence(repo, scope="task")["markers"] == []


def test_derived_answers_name_the_uncommitted_and_the_unpushed(repo: Path) -> None:
    (repo / "scratch.py").write_text("x = 1\n", encoding="utf-8")
    answers = derive_answers(collect_evidence(repo, scope="task"))
    assert answers["intent"] == ["branch under work: work"]
    assert any(row.startswith("second: change") or "second: change" in row for row in answers["did"])
    assert any("1 uncommitted path(s): scratch.py" == row for row in answers["remaining"])
    assert any("no upstream" in row for row in answers["remaining"])
    assert "commit, stash, or discard the uncommitted paths" in answers["decisions"]


def test_basis_reports_where_each_answer_came_from(repo: Path) -> None:
    summary = build_session_summary(repo, scope="task",
                                    statements={"intent": ["ship the value change"], "did": []})
    basis = {answer["key"]: answer["basis"] for answer in summary["answers"]}
    assert basis == {"intent": "mixed", "did": "derived", "remaining": "derived", "decisions": "derived"}
    assert [key for key, _ in QUESTIONS] == [answer["key"] for answer in summary["answers"]]
    assert summary["schema"] == SCHEMA and summary["verdict"] == "SUMMARY_RECORDED"

    clean = build_session_summary(repo, scope="task", statements={"intent": ["a"]})
    # An answer nothing could supply says so instead of being dropped from the record.
    assert next(a for a in clean["answers"] if a["key"] == "did")["basis"] == "derived"


def test_a_claim_of_finished_is_refused_while_the_tree_disagrees(repo: Path) -> None:
    (repo / "scratch.py").write_text("x = 1\n", encoding="utf-8")
    summary = build_session_summary(repo, scope="task",
                                    statements={"remaining": [], "decisions": []})
    codes = {row["code"] for row in summary["disagreements"]}
    assert codes == {"claimed_finished_with_work_outstanding", "claimed_no_decisions_with_blockers"}
    assert summary["verdict"] == "SUMMARY_DISAGREES"
    # Saying nothing is not the same as claiming nothing remains.
    assert build_session_summary(repo, scope="task")["disagreements"] == []
    # And a claim that agrees with the tree is not flagged.
    assert find_disagreements({"remaining": [], "decisions": []},
                              {"remaining": [], "decisions": []}) == []


def test_markdown_labels_every_answer_and_keeps_the_null(repo: Path) -> None:
    text = render_markdown(build_session_summary(repo, scope="task", statements={"intent": ["ship it"]}))
    for _, question in QUESTIONS:
        assert f"## {question}" in text
    assert "_basis: mixed_" in text
    assert "- ship it (stated)" in text
    assert "## What this does not prove" in text
    assert "C:/dev" not in text and "AppData" not in text


def test_cli_writes_both_artifacts_and_can_fail_on_disagreement(repo: Path, tmp_path: Path) -> None:
    (repo / "scratch.py").write_text("x = 1\n", encoding="utf-8")
    out, md = tmp_path / "summary.json", tmp_path / "summary.md"
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "--scope", "task", "--root", str(repo),
         "--out", str(out), "--markdown-out", str(md), "--remaining", "", "--fail-on-disagreement"],
        capture_output=True, text=True, encoding="utf-8", check=False)
    assert done.returncode == 1, done.stderr
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body["verdict"] == "SUMMARY_DISAGREES"
    assert "## What did we do?" in md.read_text(encoding="utf-8")
    assert set(SCOPES) == {"task", "goal", "session"}


def test_session_scope_reads_receipt_metadata_only(repo: Path, tmp_path: Path) -> None:
    store = tmp_path / "store"
    (store / "receipts").mkdir(parents=True)
    (store / "receipts" / "one.json").write_text(json.dumps(
        {"kind": "gate_check", "verdict": "GREEN", "run_id": "r1", "created_at": "2026-09-03T00:00:00Z",
         "body": {"token": "should-not-be-copied"}}), encoding="utf-8")
    (store / "receipts" / "old.json").write_text(json.dumps(
        {"kind": "stale", "verdict": "RED", "run_id": "r0", "created_at": "2026-01-01T00:00:00Z"}),
        encoding="utf-8")
    summary = build_session_summary(repo, scope="session", store_root=str(store),
                                    since="2026-09-01T00:00:00Z")
    rows = summary["evidence"]["receipts"]
    assert [row["kind"] for row in rows] == ["gate_check"]
    assert set(rows[0]) == {"kind", "verdict", "run_id", "created_at"}
    assert "should-not-be-copied" not in json.dumps(summary)
    assert "receipt gate_check -> GREEN" in derive_answers(summary["evidence"])["did"]
    # Task and goal scopes never read the store at all.
    assert build_session_summary(repo, scope="task", store_root=str(store))["evidence"]["receipts"] == []


def test_front_controller_delegates_the_subcommand() -> None:
    """The command is reachable through the one dispatcher, not only as a script."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from run_harness_cli import build_command, build_manifest, build_parser  # noqa: E402

    args = build_parser().parse_args(
        ["session-summary", "--scope", "goal", "--base", "origin/main", "--fail-on-disagreement"])
    command = build_command(args, repo_root=ROOT)
    assert command[1] == "scripts/run_session_summary.py"
    assert command[2:6] == ["--scope", "goal", "--base", "origin/main"]
    assert "--fail-on-disagreement" in command
    # An unset optional flag is omitted rather than passed empty, so the
    # delegated script sees its own defaults.
    assert "--since" not in command and "--statements" not in command

    entry = next(row for row in build_manifest()["commands"] if row["name"] == "session-summary")
    assert entry["delegates_to"] == "scripts/run_session_summary.py"
    assert entry["schemas"] == [SCHEMA]
    assert "tests/test_session_summary.py" in entry["recommended_validation_slice"]
