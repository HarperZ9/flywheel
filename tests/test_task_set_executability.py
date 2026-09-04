"""The gate must separate what can run from what can be scored, and name why not."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from harness.cross_harness_manifest import PILOT_TASKS
from harness.cross_harness_oracles import _CHECKERS
from harness.task_set_executability import (
    SCHEMA, VERDICTS, classify_task, evaluate_task_set, render_markdown,
)

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "run_task_set_executability.py"
TASK_SET = ROOT / "benchmarks" / "agentic-task-set-v1.json"
PILOT_CHECKER = "index_fallback_integrity/v1"
PILOT_TASK = PILOT_TASKS[PILOT_CHECKER]


def _task(**overrides):
    base = {"id": "t-1", "lane": "lane", "required_inputs": [], "oracle": {}}
    base.update(overrides)
    return base


def test_an_input_the_tree_does_not_have_blocks_provisioning(tmp_path):
    row = classify_task(tmp_path, _task(required_inputs=["missing/thing.json"]))
    assert row["provisionable"] is False
    assert row["blockers"] == ["input_missing:missing/thing.json", "no_oracle"]
    assert row["provisioned_inputs"] == 0


def test_a_typed_reference_is_declared_not_missing(tmp_path):
    row = classify_task(tmp_path, _task(required_inputs=["workspace://public/mneme"]))
    # This is the case the head-to-head lost fifty attempts to. The material is
    # named and not sealed into the workspace, which is a fact to report, not a
    # reason to throw the attempt away.
    assert row["provisionable"] is True
    assert row["unprovisioned_inputs"] == ["workspace://public/mneme"]
    assert row["provisioned_inputs"] == 0


def test_an_escape_is_refused_rather_than_resolved(tmp_path):
    for reference in ("../outside.json", "workspace://../outside"):
        row = classify_task(tmp_path, _task(required_inputs=[reference]))
        assert row["provisionable"] is False
        assert any(item.startswith(("input_escapes_root", "input_reference_invalid"))
                   for item in row["blockers"]), row["blockers"]


def test_scorable_needs_a_registered_checker_and_its_fixture(tmp_path):
    fixture = tmp_path / "fixtures" / "facts.json"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("{}", encoding="utf-8")
    oracle = {"checker_id": PILOT_CHECKER, "fixture": "fixtures/facts.json"}
    assert classify_task(tmp_path, _task(id=PILOT_TASK, oracle=oracle))["scorable"] is True

    absent = classify_task(tmp_path, _task(id=PILOT_TASK,
                                           oracle={**oracle, "fixture": "fixtures/gone.json"}))
    assert absent["scorable"] is False
    assert "fixture_missing:fixtures/gone.json" in absent["blockers"]

    unknown = classify_task(tmp_path, _task(oracle={"checker_id": "invented/v1"}))
    assert unknown["scorable"] is False
    assert "checker_not_registered:invented/v1" in unknown["blockers"]

    silent = classify_task(tmp_path, _task())
    assert silent["scorable"] is False and "no_oracle" in silent["blockers"]


def test_a_checker_bound_to_another_task_is_named(tmp_path):
    row = classify_task(tmp_path, _task(id="t-1", oracle={"checker_id": PILOT_CHECKER}))
    assert row["scorable"] is False
    assert f"checker_bound_to_other_task:{PILOT_TASK}" in row["blockers"]


def test_a_scored_task_may_not_name_material_the_workspace_cannot_hold(tmp_path):
    row = classify_task(tmp_path, _task(id=PILOT_TASK, required_inputs=["workspace://public/mneme"],
                                        oracle={"checker_id": PILOT_CHECKER}))
    # It would launch, so it stays provisionable. It cannot be read, so the
    # score is withheld rather than reported against a partial workspace.
    assert row["provisionable"] is True and row["scorable"] is False
    assert "pilot_typed_input:workspace://public/mneme" in row["blockers"]


def test_the_two_denominators_are_reported_separately(tmp_path):
    body = {"task_set_id": "set", "tasks": [
        _task(id="a", required_inputs=["missing.json"]),
        _task(id="b"),
    ]}
    path = tmp_path / "set.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    record = evaluate_task_set(tmp_path, path)
    assert record["schema"] == SCHEMA and record["verdict"] in VERDICTS
    assert record["counts"] == {"declared": 2, "provisionable": 1, "scorable": 0, "measured": 0}
    assert record["registered_checkers"] == sorted(_CHECKERS)
    assert record["does_not_prove"]


@pytest.mark.parametrize("tasks,verdict", [
    ([], "TASK_SET_BLOCKED"),
    ([_task(id="a", required_inputs=["missing.json"])], "TASK_SET_BLOCKED"),
    ([_task(id="a")], "TASK_SET_PARTIAL"),
])
def test_verdict_follows_the_counts(tmp_path, tasks, verdict):
    path = tmp_path / "set.json"
    path.write_text(json.dumps({"task_set_id": "set", "tasks": tasks}), encoding="utf-8")
    assert evaluate_task_set(tmp_path, path)["verdict"] == verdict


def test_the_live_task_set_is_provisionable_throughout_and_scorable_in_part():
    """The number this gate exists to hold, measured against the shipped set."""
    record = evaluate_task_set(ROOT, TASK_SET)
    counts = record["counts"]
    assert counts["declared"] == 14
    # Every task reaches a provider. Before the typed-reference seam was closed
    # only the four pilot tasks did, and the other ten died in the workspace
    # builder before a provider was called.
    assert counts["provisionable"] == 14
    # Four tasks carry a registered checker. The other ten declare no oracle, so
    # a run of them produces output nothing can read.
    assert counts["scorable"] == 4 and counts["measured"] == 4
    assert record["verdict"] == "TASK_SET_PARTIAL"
    scored = {row["task_id"] for row in record["tasks"] if row["measured"]}
    assert scored == set(PILOT_TASKS.values())


def test_markdown_carries_both_counts_and_keeps_the_null():
    text = render_markdown(evaluate_task_set(ROOT, TASK_SET))
    assert "- provisionable: 14 of 14" in text
    assert "- scorable: 4 of 14" in text
    assert "## What this does not prove" in text
    assert "C:/dev" not in text and "AppData" not in text


def test_cli_writes_both_artifacts_and_can_fail_on_a_floor(tmp_path):
    out, markdown = tmp_path / "record.json", tmp_path / "record.md"
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "--task-set", str(TASK_SET), "--root", str(ROOT),
         "--out", str(out), "--markdown-out", str(markdown), "--require-measurable"],
        capture_output=True, text=True, encoding="utf-8", check=False)
    assert done.returncode == 1, done.stderr
    assert "not measurable: 4 of 14 tasks" in done.stderr
    record = json.loads(out.read_text(encoding="utf-8"))
    assert record["counts"]["measured"] == 4
    assert "| task |" in markdown.read_text(encoding="utf-8")

    passing = subprocess.run(
        [sys.executable, str(SCRIPT), "--task-set", str(TASK_SET), "--root", str(ROOT),
         "--min-measured", "4"], capture_output=True, text=True, encoding="utf-8", check=False)
    assert passing.returncode == 0, passing.stderr


def test_front_controller_delegates_the_subcommand():
    sys.path.insert(0, str(ROOT / "scripts"))
    from run_harness_cli import build_command, build_manifest, build_parser  # noqa: E402

    args = build_parser().parse_args(
        ["task-set-executability", "--min-measured", "4", "--require-measurable"])
    command = build_command(args, repo_root=ROOT)
    assert command[1] == "scripts/run_task_set_executability.py"
    assert "--require-measurable" in command
    assert command[command.index("--min-measured") + 1] == "4"
    # An unset optional output is omitted rather than passed empty, so the
    # delegated script keeps its own default of writing nothing.
    assert "--out" not in command and "--markdown-out" not in command

    entry = next(row for row in build_manifest()["commands"]
                 if row["name"] == "task-set-executability")
    assert entry["delegates_to"] == "scripts/run_task_set_executability.py"
    assert entry["schemas"] == [SCHEMA]
    assert "tests/test_task_set_executability.py" in entry["recommended_validation_slice"]
