import json

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
