import json
import pytest
from harness.cross_harness_executor import comparison_key

from scripts.run_harness_comparison_report import build_report, main, metric_rows_from_artifact


def test_metric_rows_extract_m7_source_codex_and_flywheel_roles():
    data = {
        "schema": "m7-source-mined-scorecard/v1",
        "backend_rows": [
            {
                "provider": "serve",
                "provider_role": "flywheel",
                "pass_rate": 1.0,
                "mean_latency_ms": 10,
                "aggregate_metrics": {"mean_quality_score": 0.9},
            },
            {
                "provider": "codex",
                "provider_role": "codex",
                "pass_rate": 0.0,
                "mean_latency_ms": 50,
                "aggregate_metrics": {"mean_quality_score": 0.2},
            },
        ],
    }

    rows = metric_rows_from_artifact(data, "m7.json")

    assert [row["provider_role"] for row in rows] == ["flywheel", "codex"]
    assert rows[0]["benchmark_id"] == "m7_source_mined"
    assert rows[0]["quality_score"] == 0.9


def test_build_report_computes_flywheel_minus_codex_deltas(tmp_path):
    m7 = tmp_path / "m7.json"
    m7.write_text(json.dumps({
        "schema": "m7-source-mined-scorecard/v1",
        "backend_rows": [
            {
                "provider": "serve",
                "provider_role": "flywheel",
                "pass_rate": 1.0,
                "mean_latency_ms": 10,
                "aggregate_metrics": {"mean_quality_score": 0.9},
            },
            {
                "provider": "codex",
                "provider_role": "codex",
                "pass_rate": 0.5,
                "mean_latency_ms": 40,
                "aggregate_metrics": {"mean_quality_score": 0.4},
            },
        ],
    }), encoding="utf-8")

    report = build_report(artifact_paths=[m7])

    comparison = report["comparisons"][0]
    assert report["schema"] == "harness.comparison-report/v1"
    assert comparison["available"] is True
    assert comparison["pass_rate_delta_flywheel_minus_codex"] == 0.5
    assert comparison["quality_delta_flywheel_minus_codex"] == 0.5
    assert comparison["latency_delta_ms_flywheel_minus_codex"] == -30.0
    assert comparison["winner_by_quality"] == "flywheel"
    assert report["conclusion"]["verdict"] == "FLYWHEEL_BETTER_ON_OBSERVED_SLICE"


def test_build_report_keeps_missing_codex_as_insufficient_evidence(tmp_path):
    gate = tmp_path / "endpoint_gate.json"
    gate.write_text(json.dumps({
        "schema": "harness.model-endpoint-gate/v1",
        "rows": [
            {
                "model": "14B",
                "backend": "serve",
                "provider_role": "flywheel",
                "generation_ok": True,
                "quality_score": 1.0,
                "latency_ms": 12,
                "failure_class": "",
            }
        ],
    }), encoding="utf-8")

    report = build_report(artifact_paths=[gate])

    assert report["comparisons"][0]["available"] is False
    assert report["conclusion"]["verdict"] == "COMPARISON_INSUFFICIENT"


def test_main_writes_json_markdown_and_store_receipt(tmp_path):
    classifier = tmp_path / "classifier.json"
    classifier.write_text(json.dumps({
        "schema": "classifier-friction-benchmark/v1",
        "summary": {
            "rows": [
                {
                    "provider": "serve",
                    "mode": "accountability_first",
                    "pass_rate": 1.0,
                    "mean_quality_score": 0.8,
                    "mean_latency_ms": 10,
                },
                {
                    "provider": "codex",
                    "mode": "accountability_first",
                    "pass_rate": 0.0,
                    "mean_quality_score": 0.2,
                    "mean_latency_ms": 80,
                },
            ]
        },
    }), encoding="utf-8")
    out = tmp_path / "comparison.json"
    md = tmp_path / "comparison.md"
    store = tmp_path / "store"

    code = main([
        "--artifacts",
        str(classifier),
        "--out",
        str(out),
        "--markdown-out",
        str(md),
        "--store-root",
        str(store),
        "--run-id",
        "run_compare",
    ])

    data = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0
    assert data["schema"] == "harness.comparison-report/v1"
    assert data["store_outputs"][0]["schema"] == "harness.receipt/v1"
    assert "# Harness comparison report" in md.read_text(encoding="utf-8")


def _cross_row(role, task, repetition, *, oracle="pass", latency=10, unavailable=False):
    row = {"provider_role": role, "task_id": task, "repetition": repetition, "phase": "spark", "task_set_id": "set",
            "raw_prompt_sha256": "1" * 64, "input_sha256s": {"fixture": "2" * 64}, "tool_policy_sha256": "a" * 64,
            "model_id": "5.3-Codex-Spark", "cache_state": "cold_declared", "execution_mode": "focused_run",
            "source_snapshot_sha256": "3" * 64, "workspace_snapshot_sha256": "4" * 64,
            "enforcement_sha256": ("c" if role == "codex_harness" else "d") * 64,
            "policy_equivalence": "non_equivalent", "execution_state": "unavailable" if unavailable else "returned",
            "oracle_state": "not_run" if unavailable else oracle, "receipt_state": "verified",
            "metrics": {} if latency is None else {"latency_ms": latency}, "planned": True,
            "admitted": not unavailable, "blocked": unavailable, "launched": not unavailable}
    return {**row, "comparison_key": comparison_key(row)}


def test_cross_harness_spark_comparison_uses_deterministic_quality_and_latency_distribution(tmp_path):
    rows = []
    for role in ("codex_harness", "flywheel_harness"):
        rows.extend([_cross_row(role, "agt-001-index-fallback-integrity", 1, oracle="pass", latency=10),
                     _cross_row(role, "agt-001-index-fallback-integrity", 2, oracle="fail", latency=30),
                     _cross_row(role, "agt-001-index-fallback-integrity", 3, oracle="unverifiable", latency=20)])
    artifact = tmp_path / "spark-comparison-input.json"
    artifact.write_text(json.dumps({"schema": "harness.cross-harness-task-scorecard/v1", "rows": rows}), encoding="utf-8")

    report = build_report(artifact_paths=[artifact], flywheel_role="flywheel_harness", codex_role="codex_harness")
    comparison = report["comparisons"][0]

    assert comparison["comparison_type"] == "orchestration_stack"
    assert comparison["policy_equivalence"] == "non_equivalent"
    assert comparison["codex"]["quality_n"] == 2
    assert comparison["codex"]["quality_score"] == 0.5
    assert comparison["codex"]["latency_ms"] == 20
    assert comparison["codex"]["latency_range_ms"] == [10, 30]
    assert comparison["codex"]["latency_n"] == 3
    assert comparison["declared_tool_policy_sha256"] == "a" * 64
    assert comparison["codex"]["enforcement_sha256s"] == ["c" * 64]
    assert comparison["flywheel"]["enforcement_sha256s"] == ["d" * 64]


def test_cross_harness_comparison_rejects_pair_or_policy_hash_mismatch(tmp_path):
    for field in ("comparison_key", "tool_policy_sha256"):
        rows = [_cross_row("codex_harness", "agt-001-index-fallback-integrity", 1),
                _cross_row("flywheel_harness", "agt-001-index-fallback-integrity", 1)]
        rows[1][field] = "e" * 64
        artifact = tmp_path / f"bad-{field}.json"
        artifact.write_text(json.dumps({"schema": "harness.cross-harness-task-scorecard/v1", "rows": rows}), encoding="utf-8")
        with pytest.raises(ValueError, match="cross-harness .* hash mismatch"):
            build_report(artifact_paths=[artifact], flywheel_role="flywheel_harness", codex_role="codex_harness")


def test_cross_harness_rejects_single_stale_key_and_null_quality_is_insufficient(tmp_path):
    stale = _cross_row("codex_harness", "agt-001-index-fallback-integrity", 1); stale["raw_prompt_sha256"] = "9" * 64
    artifact = tmp_path / "stale.json"; artifact.write_text(json.dumps({"schema": "harness.cross-harness-task-scorecard/v1", "rows": [stale]}), encoding="utf-8")
    with pytest.raises(ValueError, match="cross-harness comparison hash mismatch"): build_report(artifact_paths=[artifact])
    rows = [_cross_row(role, "agt-001-index-fallback-integrity", 1, oracle="unverifiable") for role in ("codex_harness", "flywheel_harness")]
    artifact.write_text(json.dumps({"schema": "harness.cross-harness-task-scorecard/v1", "rows": rows}), encoding="utf-8")
    conclusion = build_report(artifact_paths=[artifact], flywheel_role="flywheel_harness", codex_role="codex_harness")["conclusion"]
    assert conclusion["verdict"] == "COMPARISON_INSUFFICIENT"
    assert "deterministic quality evidence" in conclusion["claim"]


def test_returned_receipt_drift_counts_reliability_latency_not_quality(tmp_path):
    rows = [_cross_row(role, "agt-001-index-fallback-integrity", 1, latency=17) for role in ("codex_harness", "flywheel_harness")]
    for row in rows: row["receipt_state"] = "drift"
    artifact = tmp_path / "drift.json"; artifact.write_text(json.dumps({"schema": "harness.cross-harness-task-scorecard/v1", "rows": rows}), encoding="utf-8")
    comparison = build_report(artifact_paths=[artifact], flywheel_role="flywheel_harness", codex_role="codex_harness")["comparisons"][0]
    assert comparison["codex"]["pass_rate"] == 1.0 and comparison["codex"]["latency_ms"] == 17
    assert comparison["codex"]["quality_score"] is None and comparison["codex"]["receipt_states"]["drift"] == 1
    missing = dict(rows[0]); missing.pop("phase")
    assert metric_rows_from_artifact({"schema": "harness.cross-harness-task-scorecard/v1", "rows": [missing]}, "missing-phase.json") == []


def test_cross_harness_comparison_excludes_local_phase_and_preserves_null_metrics(tmp_path):
    rows = [_cross_row("codex_harness", "agt-001-index-fallback-integrity", 1, latency=None, unavailable=True),
            _cross_row("flywheel_harness", "agt-001-index-fallback-integrity", 1, latency=None, unavailable=True),
            {**_cross_row("local_14b", "agt-001-index-fallback-integrity", 1), "phase": "local"}]
    artifact = tmp_path / "mixed.json"
    artifact.write_text(json.dumps({"schema": "harness.cross-harness-task-scorecard/v1", "rows": rows}), encoding="utf-8")
    report = build_report(artifact_paths=[artifact], flywheel_role="flywheel_harness", codex_role="codex_harness")

    assert report["summary"]["provider_roles_observed"] == ["codex_harness", "flywheel_harness"]
    assert report["metric_rows"][0]["quality_score"] is None
    assert report["metric_rows"][0]["latency_ms"] is None
