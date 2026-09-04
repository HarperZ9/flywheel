"""The output-validation ledger read back as summary evidence.

The check that ran during the work and the summary written at the end of it are
two readings of the same run. What this file pins is that the second one carries
what the first decided, without carrying the value an answer failed against.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.session_summary import (  # noqa: E402
    build_session_summary, collect_evidence, find_disagreements, render_markdown,
)
from harness.summary_validation import (  # noqa: E402
    read_validation, short_of_release, validation_answers,
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


LEDGER_SCHEMA = "flywheel.validation-ledger/v1"


def _entry(subject, release, blocking=(), at="2026-09-04T00:00:00+00:00"):
    return json.dumps({"schema": LEDGER_SCHEMA, "at": at, "scope": "task",
                       "subject": subject, "verdict": "FAIL", "release": release,
                       "blocking": list(blocking), "unresolved": list(blocking),
                       "checked": 2, "passed": 1,
                       "fields": [{"field": "tax", "authoritative_value": 4169}]})


def _ledger(path: Path, *lines: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_a_check_short_of_a_clean_release_is_work_that_is_left(repo: Path, tmp_path: Path) -> None:
    """The ledger answers the accumulated question, which is question three."""
    path = _ledger(tmp_path / "validation.jsonl",
                   _entry("t-1", "HOLD", ["tax"]),
                   _entry("t-2", "RELEASE_WITH_CAVEAT", ["footnote"]),
                   _entry("t-3", "RELEASE"))
    summary = build_session_summary(repo, scope="task", validation_ledger=str(path))
    answers = {row["key"]: row["derived"] for row in summary["answers"]}
    assert "3 output check(s) recorded: 1 released, 1 with a caveat, 1 held" in answers["did"]
    assert "output held for t-1: tax" in answers["remaining"]
    assert "output released with a caveat for t-2: footnote" in answers["remaining"]
    assert not any("t-3" in item for item in answers["remaining"])
    assert "`HOLD` task/t-1: tax" in render_markdown(summary)
    # Held first, because the worst entry is the one an operator works through.
    assert [row["subject"] for row in short_of_release(read_validation(path))] == ["t-1", "t-2"]


def test_the_ledger_is_not_discarded_by_a_torn_or_foreign_line(tmp_path: Path) -> None:
    """A ledger written by a process that was killed mid-write still answers
    the question about every entry before the tear."""
    path = _ledger(tmp_path / "validation.jsonl",
                   _entry("t-1", "HOLD", ["tax"]),
                   json.dumps({"schema": "someone.else/v1", "release": "HOLD"}),
                   '{"schema": "flywheel.validation-ledg')
    rows = read_validation(path)
    assert [row["subject"] for row in rows] == ["t-1"]
    assert read_validation(tmp_path / "absent.jsonl") == []


def test_the_summary_never_carries_the_value_an_answer_failed_against(repo: Path, tmp_path: Path) -> None:
    """Same reason the feedback block does not: a summary that repeated the
    number would hand the next attempt its answer key."""
    path = _ledger(tmp_path / "validation.jsonl", _entry("t-1", "HOLD", ["tax"]))
    summary = build_session_summary(repo, scope="task", validation_ledger=str(path))
    assert "4169" not in json.dumps(summary)
    assert "4169" not in render_markdown(summary)


def test_a_since_bound_applies_to_the_ledger_as_well(repo: Path, tmp_path: Path) -> None:
    path = _ledger(tmp_path / "validation.jsonl",
                   _entry("old", "HOLD", ["tax"], at="2026-01-01T00:00:00+00:00"),
                   _entry("new", "HOLD", ["tax"]))
    evidence = collect_evidence(repo, scope="task", validation_ledger=str(path),
                                since="2026-09-01T00:00:00+00:00")
    assert [row["subject"] for row in evidence["validation"]] == ["new"]
    assert collect_evidence(repo, scope="task")["validation"] == []


def test_a_claim_of_finished_is_refused_while_output_is_held(repo: Path, tmp_path: Path) -> None:
    """Held output is not one more loose end. It is an answer that disagreed
    with the source that decides it, so it gets its own code."""
    path = _ledger(tmp_path / "validation.jsonl", _entry("t-1", "HOLD", ["tax"]))
    summary = build_session_summary(repo, scope="task", validation_ledger=str(path),
                                    statements={"remaining": []})
    assert "claimed_finished_with_output_held" in [row["code"] for row in summary["disagreements"]]
    assert summary["verdict"] == "SUMMARY_DISAGREES"
    # A caveat is unconfirmed rather than wrong, so it does not raise this code.
    caveat = _ledger(tmp_path / "sub" / "validation.jsonl",
                     _entry("t-2", "RELEASE_WITH_CAVEAT", ["note"]))
    other = build_session_summary(repo, scope="task", validation_ledger=str(caveat),
                                  statements={"remaining": []})
    assert "claimed_finished_with_output_held" not in [row["code"] for row in other["disagreements"]]


def test_a_claim_of_work_over_an_empty_window_is_refused(repo: Path) -> None:
    """The failure this catches is a run that narrated a stretch of work and
    left nothing on the tree to show for it."""
    summary = build_session_summary(repo, scope="goal", statements={"did": ["shipped the feature"]})
    row = next(row for row in summary["disagreements"]
               if row["code"] == "claimed_work_with_nothing_in_the_tree")
    assert "clean tree" in row["detail"]
    # One uncommitted file is enough to make the claim supportable, so the code
    # does not fire on work that is merely uncommitted.
    (repo / "scratch.py").write_text("x = 1\n", encoding="utf-8")
    again = build_session_summary(repo, scope="goal", statements={"did": ["shipped the feature"]})
    assert "claimed_work_with_nothing_in_the_tree" not in [r["code"] for r in again["disagreements"]]


def test_no_disagreement_class_reads_the_prose_of_a_stated_answer() -> None:
    """A summary that graded wording would fail honest writing and pass a
    careful liar, so every class is structural."""
    derived = {"intent": [], "did": [], "remaining": ["one thing"], "decisions": []}
    evidence = {"validation": [], "commits": [{"sha": "abc", "subject": "s"}],
                "worktree": {"staged": [], "unstaged": [], "untracked": []}, "window": "a..b"}
    assert find_disagreements(derived, {"did": ["everything is complete and shipped"]}, evidence) == []
    assert validation_answers([]) == {"did": [], "remaining": [], "decisions": []}


def test_strict_separates_a_contradiction_from_unfinished_work(repo: Path, tmp_path: Path) -> None:
    """Three outcomes, the same vocabulary the output check uses: 1 is wrong,
    3 is unchecked, and merging them would report unfinished work as clean."""
    def run(scope, *extra):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--scope", scope, "--root", str(repo),
             "--out", str(tmp_path / "s.json"), "--markdown-out", str(tmp_path / "s.md"),
             "--strict", *extra],
            capture_output=True, text=True, encoding="utf-8", check=False)

    path = str(_ledger(tmp_path / "validation.jsonl", _entry("t-1", "HOLD", ["tax"])))
    assert run("task", "--validation-ledger", path).returncode == 3
    assert run("task", "--validation-ledger", path, "--remaining", "").returncode == 1
    clean = run("goal")
    assert clean.returncode == 0, clean.stderr


def test_the_front_controller_carries_the_ledger_and_the_strict_flag() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    from run_harness_cli import build_command, build_parser  # noqa: E402

    args = build_parser().parse_args(
        ["session-summary", "--validation-ledger", "led.jsonl", "--strict"])
    command = build_command(args, repo_root=ROOT)
    assert command[command.index("--validation-ledger") + 1] == "led.jsonl"
    assert "--strict" in command
