import json

import pytest

from harness.cross_harness_postrun_intent import build_intended_matrix
from tests.cross_harness_postrun_support import _execute_pair, _sha


def test_build_intended_matrix_rejects_boolean_repetitions(tmp_path):
    source = tmp_path / "source"; source.mkdir()
    with pytest.raises(ValueError, match="repetitions"):
        build_intended_matrix({"task_set_id": "set", "task_rows": [], "provider_specs": []},
                              run_id="run", phase="spark", task_ids=[], roles=[],
                              repetitions=True, execution_mode="focused_run", cache_state="cold_declared",
                              source_commit="head", source_snapshot_sha256="0" * 64)


def test_executor_binds_pre_run_intent_matrix_to_rows_run_scorecard_and_index(tmp_path):
    run, run_root = _execute_pair(tmp_path, ready=False)
    intent_path = run_root / "intended-matrix.json"
    intent_sha = _sha(intent_path)
    run_doc = json.loads((run_root / "run.json").read_text(encoding="utf-8"))
    scorecard = json.loads((run_root / "comparison-input.json").read_text(encoding="utf-8"))
    index = json.loads((run_root / "artifact-index.json").read_text(encoding="utf-8"))

    assert run["intended_matrix_sha256"] == intent_sha
    assert run_doc["intended_matrix_sha256"] == intent_sha
    assert scorecard["intended_matrix_sha256"] == intent_sha
    assert {row["intended_matrix_sha256"] for row in scorecard["rows"]} == {intent_sha}
    cell_fields = ("task_set_id", "task_id", "repetition", "provider_role", "harness_id", "adapter_id", "model_id", "requested_model_reference")
    cells = json.loads(intent_path.read_text(encoding="utf-8"))["cells"]
    assert {tuple(cell[field] for field in cell_fields) for cell in cells} == {
        ("set", "agt-003-codex-flywheel-shared-task", 1, "codex_harness", "codex", "codex_cli_json/v1", "gpt-5.3-codex-spark", "gpt-5.3-codex-spark"),
        ("set", "agt-003-codex-flywheel-shared-task", 1, "flywheel_harness", "flywheel", "flywheel_router/v1", "gpt-5.3-codex-spark", "gpt-5.3-codex-spark"),
    }
    assert any(item["path"] == "intended-matrix.json" and item["sha256"] == intent_sha for item in index["artifacts"])
