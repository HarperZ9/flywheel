import json
from pathlib import Path

from harness.cross_harness_artifacts import bind_attempt_receipt, write_artifact_index
from harness.cross_harness_policy import tool_policy_for
from tests.cross_harness_postrun_support import (
    ROLES,
    SOURCE_COMMIT,
    TASK_ID,
    _canonical_sha,
    _execute_pair,
    _make_dir_link,
    _refresh_index_hashes,
    _sha,
    _write_json,
)

def test_postrun_validator_accepts_executor_produced_pass_and_oracle_fail_pair(tmp_path):
    from harness.cross_harness_postrun import validate_postrun_comparison

    _run, run_root = _execute_pair(tmp_path)
    report = validate_postrun_comparison(run_root)

    assert report["decision"] == "completed_comparison"
    assert report["comparison_scope"] == "orchestration_stack_observation"
    assert report["quality_ranking"] is None
    assert report["counts"] == {"intended_attempts": 2, "eligible_scored": 2, "gaps": 0, "extra_rows": 0}
    by_role = {cell["provider_role"]: cell for cell in report["cells"]}
    assert by_role["codex_harness"]["oracle_state"] == "pass"
    assert by_role["flywheel_harness"]["primary_outcome"] == "oracle_fail"
    assert report["enforcement"]["equivalence"] == "non_equivalent"


def test_postrun_validator_rejects_reduced_original_denominator(tmp_path):
    from harness.cross_harness_postrun import validate_postrun_comparison

    _run, run_root = _execute_pair(tmp_path, roles=("codex_harness",))

    report = validate_postrun_comparison(run_root)

    assert report["decision"] == "evidence_gap"
    assert "intended_role_set_mismatch" in report["reasons"]
    assert report["quality_ranking"] is None


def test_postrun_validator_rejects_duplicate_observed_cell_before_quality(tmp_path):
    from harness.cross_harness_postrun import validate_postrun_comparison

    _run, run_root = _execute_pair(tmp_path)
    scorecard = run_root / "comparison-input.json"
    data = json.loads(scorecard.read_text(encoding="utf-8"))
    data["rows"].append(dict(data["rows"][0]))
    scorecard.write_text(json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    report = validate_postrun_comparison(run_root)

    assert report["decision"] == "evidence_gap"
    assert "duplicate_observed_cell" in report["reasons"]
    assert report["quality_ranking"] is None


def test_postrun_validator_rejects_extra_observed_row_before_completion(tmp_path):
    from harness.cross_harness_postrun import validate_postrun_comparison

    _run, run_root = _execute_pair(tmp_path)
    score_path = run_root / "comparison-input.json"
    run_path = run_root / "run.json"
    scorecard = json.loads(score_path.read_text(encoding="utf-8"))
    run = json.loads(run_path.read_text(encoding="utf-8"))
    extra = dict(scorecard["rows"][0], provider_role="local_14b", harness_id="local")
    scorecard["rows"].append(extra)
    run["rows"].append(extra)
    _write_json(score_path, scorecard)
    _write_json(run_path, run)
    _refresh_index_hashes(run_root)

    report = validate_postrun_comparison(run_root)

    assert report["decision"] == "evidence_gap"
    assert "extra_observed_row" in report["reasons"]
    assert report["counts"]["extra_rows"] == 1
    assert report["quality_ranking"] is None


def test_postrun_validator_rejects_declared_two_repetitions_with_one_rep_cells(tmp_path):
    from harness.cross_harness_postrun import validate_postrun_comparison

    _run, run_root = _execute_pair(tmp_path)
    intent_path = run_root / "intended-matrix.json"
    intent = json.loads(intent_path.read_text(encoding="utf-8"))
    intent["repetitions"] = [1, 2]
    _write_json(intent_path, intent)
    new_sha = _sha(intent_path)
    for name in ("run.json", "comparison-input.json"):
        data = json.loads((run_root / name).read_text(encoding="utf-8"))
        data["intended_matrix_sha256"] = new_sha
        _write_json(run_root / name, data)
    _refresh_index_hashes(run_root)

    report = validate_postrun_comparison(run_root)

    assert report["decision"] == "evidence_gap"
    assert report["counts"]["intended_attempts"] == 4
    assert "intended_product_mismatch" in report["reasons"]
    assert "intended_repetition_pair_incomplete" in report["reasons"]
    assert report["quality_ranking"] is None


def test_postrun_validator_rejects_linked_run_root_before_resolve(tmp_path):
    from harness.cross_harness_postrun import validate_postrun_comparison

    _run, run_root = _execute_pair(tmp_path)
    alias = tmp_path / "run-root-alias"
    _make_dir_link(alias, run_root)

    report = validate_postrun_comparison(alias)

    assert report["decision"] == "evidence_gap"
    assert "linked_run_root" in report["reasons"]
    assert report["counts"]["eligible_scored"] == 0
    assert report["quality_ranking"] is None


def test_postrun_validator_rejects_duplicate_artifact_index_paths(tmp_path):
    from harness.cross_harness_postrun import validate_postrun_comparison

    _run, run_root = _execute_pair(tmp_path)
    index_path = run_root / "artifact-index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["artifacts"].append(dict(index["artifacts"][0]))
    _write_json(index_path, index)

    report = validate_postrun_comparison(run_root)

    assert report["decision"] == "evidence_gap"
    assert "artifact_index_duplicate_path" in report["reasons"]
    assert report["quality_ranking"] is None


def test_postrun_validator_rejects_linked_artifact_path_before_resolve(tmp_path):
    from harness.cross_harness_postrun import validate_postrun_comparison

    _run, run_root = _execute_pair(tmp_path)
    score_path = run_root / "comparison-input.json"
    run_path = run_root / "run.json"
    scorecard = json.loads(score_path.read_text(encoding="utf-8"))
    run = json.loads(run_path.read_text(encoding="utf-8"))
    target_attempt = Path(scorecard["rows"][0]["attempt_dir"])
    alias = run_root / "alias-attempt"
    _make_dir_link(alias, target_attempt)
    scorecard["rows"][0]["raw_output_path"] = str(alias / "output.txt")
    run["rows"][0]["raw_output_path"] = str(alias / "output.txt")
    _write_json(score_path, scorecard)
    _write_json(run_path, run)
    _refresh_index_hashes(run_root)

    report = validate_postrun_comparison(run_root)

    assert report["decision"] == "evidence_gap"
    assert "linked_artifact_path" in report["reasons"]
    assert report["quality_ranking"] is None


def test_postrun_validator_reports_typed_cell_malformed_without_crash(tmp_path):
    from harness.cross_harness_postrun import validate_postrun_comparison

    _run, run_root = _execute_pair(tmp_path)
    score_path = run_root / "comparison-input.json"
    run_path = run_root / "run.json"
    scorecard = json.loads(score_path.read_text(encoding="utf-8"))
    run = json.loads(run_path.read_text(encoding="utf-8"))
    scorecard["rows"][0]["repetition"] = "1"
    run["rows"][0]["repetition"] = "1"
    _write_json(score_path, scorecard)
    _write_json(run_path, run)
    _refresh_index_hashes(run_root)

    report = validate_postrun_comparison(run_root)

    assert report["decision"] == "evidence_gap"
    assert "row_cell_malformed" in report["reasons"]
    assert "missing_row" in report["reasons"]
    assert report["quality_ranking"] is None


def test_postrun_validator_keeps_unavailable_spark_as_gap(tmp_path):
    from harness.cross_harness_postrun import validate_postrun_comparison

    _run, run_root = _execute_pair(tmp_path, ready=False)

    report = validate_postrun_comparison(run_root)

    assert report["decision"] == "evidence_gap"
    assert "blocked_or_unavailable" in report["reasons"]
    assert report["counts"]["intended_attempts"] == 2
    assert report["counts"]["eligible_scored"] == 0
    assert {cell["provider_role"] for cell in report["cells"]} == set(ROLES)


def test_postrun_validator_classifies_legacy_unbound_scorecard(tmp_path):
    from harness.cross_harness_postrun import validate_postrun_comparison

    run_root = tmp_path / "legacy"; run_root.mkdir()
    (run_root / "comparison-input.json").write_text(json.dumps({"schema": "harness.cross-harness-task-scorecard/v1", "rows": [], "source_tree_state": "clean"}), encoding="utf-8")

    report = validate_postrun_comparison(run_root)

    assert report["decision"] == "evidence_gap"
    assert "legacy_intent_unverified" in report["reasons"]




def test_postrun_cli_writes_json_and_markdown_without_running_providers(tmp_path):
    from scripts.run_cross_harness_postrun_comparison import main

    _run, run_root = _execute_pair(tmp_path)
    out = tmp_path / "postrun.json"
    md = tmp_path / "postrun.md"

    code = main([str(run_root), "--out", str(out), "--markdown-out", str(md)])

    assert code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["schema"] == "harness.cross-harness-postrun-comparison/v1"
    assert data["decision"] == "completed_comparison"
    text = md.read_text(encoding="utf-8")
    assert "# Cross-harness post-run comparison" in text
    assert "completed_comparison" in text
    assert "does not run providers" in text


def test_postrun_validator_rejects_byte_valid_oracle_and_metrics_artifact_mismatch(tmp_path):
    from harness.cross_harness_postrun import validate_postrun_comparison

    run_root = tmp_path / "run"; attempt = run_root / "spark" / "codex_harness" / TASK_ID / "rep-001"
    attempt.mkdir(parents=True)
    intent = {"schema": "harness.cross-harness-postrun-intended-matrix/v1", "run_id": "run", "phase": "spark",
              "task_set_id": "set", "roles": ["codex_harness", "flywheel_harness"], "repetitions": [1],
              "execution_mode": "focused_run", "cache_state": "cold_declared", "source_commit": SOURCE_COMMIT,
              "source_snapshot_sha256": "a" * 64, "row_schema": "harness.cross-harness-task-scorecard/v1", "cells": [
                  {"task_set_id": "set", "task_id": TASK_ID, "repetition": 1, "provider_role": "codex_harness", "harness_id": "codex", "adapter_id": "codex_cli_json/v1", "model_id": "gpt-5.3-codex-spark", "requested_model_reference": "gpt-5.3-codex-spark"},
                  {"task_set_id": "set", "task_id": TASK_ID, "repetition": 1, "provider_role": "flywheel_harness", "harness_id": "flywheel", "adapter_id": "flywheel_router/v1", "model_id": "gpt-5.3-codex-spark", "requested_model_reference": "gpt-5.3-codex-spark"}]}
    intent_path = run_root / "intended-matrix.json"
    intent_path.write_text(json.dumps(intent, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    intent_sha = _sha(intent_path)
    row = {"schema": "harness.cross-harness-task-scorecard/v1", "run_id": "run", "phase": "spark", "task_set_id": "set", "task_id": TASK_ID,
           "repetition": 1, "provider_role": "codex_harness", "harness_id": "codex", "adapter_id": "codex_cli_json/v1",
           "model_id": "gpt-5.3-codex-spark", "requested_model_reference": "gpt-5.3-codex-spark", "model_observed": "gpt-5.3-codex-spark",
           "model_observation_basis": "structured_provider_response", "raw_prompt_sha256": "b" * 64, "input_sha256s": {}, "runtime_context_sha256": "c" * 64,
           "tool_policy_sha256": _canonical_sha(tool_policy_for()), "source_commit": SOURCE_COMMIT, "source_snapshot_sha256": "a" * 64,
           "workspace_snapshot_sha256": "d" * 64, "cache_state": "cold_declared", "execution_mode": "focused_run", "intended_matrix_sha256": intent_sha,
           "comparison_key": "0" * 64, "attempt_dir": str(attempt), "raw_output_path": str(attempt / "output.txt"), "raw_output_sha256": "",
           "tool_trace_path": str(attempt / "tool_trace.json"), "receipt_path": str(attempt / "receipt.json"), "metrics": {"latency_ms": 1},
           "oracle_evidence": {"reported_state": "pass", "failure_codes": []}, "execution_state": "returned", "oracle_state": "pass", "receipt_state": "verified",
           "orthogonal_states": {"execution_state": "returned", "oracle_state": "pass", "receipt_state": "verified"}, "primary_outcome": "completed", "status": "executed",
           "planned": True, "admitted": True, "blocked": False, "launched": True, "failure_class": "", "failure_detail": "", "enforcement_description": {"boundary": "codex"},
           "enforcement_sha256": _canonical_sha({"boundary": "codex"}), "adapter_verification_claim": "unverified_claim", "enforcement_verification_state": "unverified", "metric_null_reasons": {}}
    artifacts = {}
    for name, value in {"output.txt": "{}", "tool_trace.json": [], "oracle.json": {"reported_state": "fail", "failure_codes": ["semantic"]},
                        "metrics.json": {"latency_ms": 1}, "resource.json": {"latency_ms": 2}, "enforcement.json": {"boundary": "codex"}, "limitations.md": ""}.items():
        path = attempt / name
        if isinstance(value, str): path.write_text(value, encoding="utf-8")
        else: path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        artifacts[name] = path
    row["raw_output_sha256"] = _sha(attempt / "output.txt")
    row["comparison_key"] = _canonical_sha({"synthetic": "not executor"})
    bind_attempt_receipt(row, artifacts, attempt / "receipt.json")
    row["receipt_sha256"] = _sha(attempt / "receipt.json")
    rows = [row, {**row, "provider_role": "flywheel_harness", "harness_id": "flywheel", "adapter_id": "flywheel_router/v1", "attempt_dir": str(attempt)}]
    (run_root / "run.json").write_text(json.dumps({"schema": "harness.cross-harness-run-receipt/v1", "run_id": "run", "phase": "spark", "rows": rows,
        "source_snapshot_before": {"sha256": "a" * 64}, "source_snapshot_after": {"sha256": "a" * 64}, "source_tree_state": "clean",
        "intended_matrix_sha256": intent_sha, "intended_matrix_path": "intended-matrix.json"}, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    (run_root / "comparison-input.json").write_text(json.dumps({"schema": "harness.cross-harness-task-scorecard/v1", "rows": rows, "source_tree_state": "clean",
        "intended_matrix_sha256": intent_sha, "intended_matrix_path": "intended-matrix.json"}, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    write_artifact_index(run_root, [intent_path, run_root / "run.json", run_root / "comparison-input.json", *artifacts.values(), attempt / "receipt.json"])

    report = validate_postrun_comparison(run_root)

    assert report["decision"] == "evidence_gap"
    assert "oracle_artifact_row_mismatch" in report["reasons"]
    assert "metrics_artifact_row_mismatch" in report["reasons"]
    assert "comparison_key_mismatch" in report["reasons"]
    assert report["quality_ranking"] is None
