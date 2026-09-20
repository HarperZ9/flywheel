from pathlib import Path

from harness.cross_harness_manifest import PILOT_TASKS, build_manifest, load_json
from harness.task_set_executability import evaluate_task_set
from tests.test_context_recovery_oracle import ARTIFACTS, CHECKER, TASK_ID

ROOT = Path(__file__).resolve().parent.parent


def test_live_task_set_registers_context_recovery_as_scorable():
    record = evaluate_task_set(ROOT, ROOT / "benchmarks/agentic-task-set-v1.json")
    row = next(item for item in record["tasks"] if item["task_id"] == TASK_ID)
    assert PILOT_TASKS[CHECKER] == TASK_ID
    assert row["provisionable"] is True and row["scorable"] is True
    assert row["measured"] is True
    shared_v2_row = next(
        item for item in record["tasks"] if item["task_id"] == "agt-003-shared-task-artifact-v2-diagnostic"
    )
    assert PILOT_TASKS["shared_task_artifact/v2"] == "agt-003-shared-task-artifact-v2-diagnostic"
    assert shared_v2_row["checker_id"] == "shared_task_artifact/v2"
    assert shared_v2_row["provisionable"] is True and shared_v2_row["scorable"] is True
    assert shared_v2_row["measured"] is True
    assert record["counts"] == {"declared": 19, "provisionable": 19, "scorable": 9, "measured": 9}


def test_manifest_binds_context_recovery_fixture_and_response_contract():
    task_path = ROOT / "benchmarks/agentic-task-set-v1.json"
    contract_path = ROOT / "benchmarks/cross-harness-adapter-contract-v2.json"
    manifest = build_manifest(
        load_json(task_path),
        load_json(contract_path),
        task_set_path=str(task_path),
        source_root=str(ROOT),
        provider_roles=["dry"],
    )
    row = next(item for item in manifest["task_rows"] if item["task_id"] == TASK_ID)
    assert row["oracle"]["checker_id"] == CHECKER
    assert row["expected_artifacts"] == ARTIFACTS
    assert row["response_envelope"]["artifacts"] == {
        "context_recovery_state.json": "json_object",
        "context_recovery_state.md": "markdown_string",
    }
    assert set(row["input_sha256s"]) == set(row["required_inputs"])
