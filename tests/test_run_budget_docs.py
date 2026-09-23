"""The run-budget docs name what the breaker does not cover.

A reader of "per-run budget" should not have to read the code to learn which
paths it skips, what the check command costs, which limits a CLI enforces
after the fact, or which kinds of limit error the check reads.
"""
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"


def _doc(name: str) -> str:
    return " ".join((DOCS / name).read_text(encoding="utf-8").split())


def test_the_uncovered_workflow_paths_are_named():
    text = _doc("RUN-BUDGET.md")
    for path in ("`workflow.run`", "`/api/workflow`", "`plan.run`"):
        assert path in text


def test_the_overloaded_signal_and_the_language_limit_are_stated():
    text = _doc("RUN-BUDGET.md")
    assert "service-overloaded (HTTP 503 or 529)" in text
    assert "English phrase heuristic" in text


def test_the_check_command_is_said_to_be_a_harness_check_not_a_tool_action():
    for name in ("RUN-BUDGET.md", "VERIFIED-COMPLETION.md"):
        assert "does not use a tool action" in _doc(name), name
    assert "`harness_checks`" in _doc("RUN-BUDGET.md")


def test_the_wall_time_record_is_described_as_it_behaves():
    text = _doc("RUN-BUDGET.md")
    assert "Wall time stays with the existing aggregate deadline" not in text
    assert "no budget record is written" not in text
    assert "`recorded_by: gateway_deadline`" in text


def test_cli_tokens_are_said_to_count_as_they_stream_and_spend_after_the_fact():
    text = _doc("RUN-BUDGET.md")
    assert "counts each message's tokens once, by id, as they stream" in text
    assert "the spend limit marks a session stopped after the fact" in text
    assert "both the token limit and the spend limit mark a CLI session stopped" not in text


def test_the_schedule_breaker_trigger_and_re_arm_are_documented():
    text = _doc("RUN-BUDGET.md")
    section = text[text.index("## Scheduled jobs"):text.index("## What the projection")]
    for phrase in ("a nonzero exit", "a timeout or a runner error", "one replayed backlog",
                   "before this check existed", "`POST /api/schedule/rearm`",
                   "`scan_output: false`"):
        assert phrase in section, phrase
    readme = " ".join((DOCS.parent / "README.md").read_text(encoding="utf-8").split())
    assert "stops itself after two failed fires in a row" in readme
    notes = _doc("RELEASE-NEXT.md")
    assert "## Behaviour changes" in notes and "Schedules stop themselves" in notes


def test_the_completion_doc_names_the_protected_set_and_no_unreachable_check():
    text = _doc("VERIFIED-COMPLETION.md")
    table = text[text.index("## The checks"):text.index("A write whose tool")]
    assert "| The final answer | `acceptance_criteria` |" not in table
    assert "`agent.run` takes no criteria" in text
    for name in ("`pytest.ini`", "`tox.ini`", "`pyproject.toml`", "`setup.cfg`",
                 "`conftest.py`", "`changed_by_command`"):
        assert name in text, name


def test_the_docs_this_feature_changed_pass_the_writing_gate():
    import subprocess
    import sys
    repo = DOCS.parent
    changed = ["docs/RUN-BUDGET.md", "docs/VERIFIED-COMPLETION.md", "docs/ROWAN-HANDOFF.md",
               "docs/native-agent-binding-contract.md", "docs/RELEASE-NEXT.md",
               "project-docs/records/ROWAN-CAPABILITY-MAP-2026-09-23.md"]
    gate = subprocess.run([sys.executable, "scripts/check_writing.py", "--gate", *changed],
                          cwd=repo, capture_output=True, text=True, timeout=120)
    assert gate.returncode == 0, gate.stdout + gate.stderr
