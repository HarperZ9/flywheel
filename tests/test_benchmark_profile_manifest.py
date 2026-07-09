import json

from scripts.run_benchmark_profile_manifest import (
    build_profile,
    inventory_existing_artifacts,
    render_markdown,
)


def test_profile_weights_sum_to_one_and_cover_required_metrics(tmp_path):
    profile = build_profile(
        providers="serve,codex,opencode",
        artifact_roots=str(tmp_path),
        max_artifacts=10,
    )

    assert profile["schema"] == "harness.benchmark-profile-manifest/v1"
    assert profile["metric_weight_sum"] == 1.0
    assert "task_completion" in profile["metrics"]
    assert "tool_use_success" in profile["metrics"]
    assert "groundedness" in profile["metrics"]
    assert "workflow_state_management" in profile["metrics"]
    assert "accountability_receipts" in profile["metrics"]
    assert profile["dataset_lane_weight_sum"] == 1.0
    assert profile["summary"]["dataset_lanes"] >= 7
    assert profile["summary"]["pressure_variables"] >= 20
    assert profile["summary"]["provider_names"] == ["serve", "codex", "opencode"]
    assert profile["summary"]["provider_role_ids"] == ["flywheel", "codex", "opencode"]
    assert profile["provider_aliases"]["gpt-5.3-codex-spark"] == "codex"
    assert profile["provider_aliases"]["open-code"] == "opencode"
    assert profile["summary"]["coverage_units"] > profile["summary"]["benchmarks"]
    classifier = [row for row in profile["benchmarks"] if row["id"] == "classifier_friction_accountability"][0]
    assert classifier["evidence_schema"] == "classifier-friction-benchmark/v1"
    assert "workspace_receipt_audit:accountability_first" in classifier["coverage_units"]
    lanes = {row["lane"]: row for row in profile["dataset_lanes"]}
    assert "cross_harness_reproducibility" in lanes
    assert "adapter-skew" in lanes["cross_harness_reproducibility"]["pressure_variables"]
    assert "replayable_causal_ledger_scaling" in lanes
    assert "entry-count-scale" in lanes["replayable_causal_ledger_scaling"]["pressure_variables"]
    assert "embodied_realtime_multimodal" in lanes
    assert "real-time-latency" in lanes["embodied_realtime_multimodal"]["pressure_variables"]
    forum = [row for row in profile["benchmarks"] if row["id"] == "forum_ledger_deep_verify_scaling"][0]
    assert forum["evidence_schema"] == "forum.deep-verify-benchmark/v1"
    assert "verify_deep_redacted" in forum["coverage_units"]
    embodied = [row for row in profile["benchmarks"] if row["id"] == "embodied_realtime_multimodal_pressure"][0]
    assert embodied["evidence_schema"] == "harness.embodied-realtime-multimodal/v1"
    assert "affective_jealousy_possessiveness_probe" in embodied["coverage_units"]


def test_existing_artifact_inventory_is_metadata_only_and_bounded(tmp_path):
    artifact = tmp_path / "m7_existing_bench_dry.json"
    artifact.write_text(json.dumps({"secret": "not-read-by-inventory"}), encoding="utf-8")
    ignored = tmp_path / "notes.txt"
    ignored.write_text("ignore", encoding="utf-8")

    rows = inventory_existing_artifacts(str(tmp_path), max_artifacts=1)

    assert len(rows) == 1
    assert rows[0]["path"] == str(artifact)
    assert rows[0]["size_bytes"] > 0
    assert "m7" in rows[0]["labels"]


def test_profile_groups_seed_and_full_benchmark_suites(tmp_path):
    profile = build_profile(artifact_roots=str(tmp_path), max_artifacts=10)
    suites = {row["suite"]: row for row in profile["benchmark_suites"]}

    assert suites["seed"]["runnable_count"] >= 4
    assert suites["full"]["planned_count"] >= 5
    assert profile["summary"]["runnable_benchmarks"] >= 4
    source = [row for row in profile["benchmarks"] if row["id"] == "m7_source_mined"][0]
    assert "buildlang_buildc_compiler_receipts" in source["coverage_units"]
    gauntlet = [row for row in profile["benchmarks"] if row["id"] == "closed_loop_agentic_gauntlet"][0]
    assert "workflow_state_management" in gauntlet["metrics"]
    assert "index_fallback" in gauntlet["coverage_units"]


def test_render_markdown_includes_weights_suites_and_artifact_summary(tmp_path):
    profile = build_profile(artifact_roots=str(tmp_path), max_artifacts=10)

    markdown = render_markdown(profile)

    assert "# Benchmark profile manifest" in markdown
    assert "## Metric weights" in markdown
    assert "## Dataset lanes" in markdown
    assert "## Benchmark suites" in markdown
    assert "m7_source_mined" in markdown
