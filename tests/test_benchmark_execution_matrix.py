import json

from scripts.run_benchmark_execution_matrix import build_matrix, main, render_markdown


def test_matrix_defines_dry_focused_and_full_tiers_without_execution():
    matrix = build_matrix(
        providers="serve,gpt-5.3-codex-spark,open-code",
        run_id="run_test",
        artifact_dir="C:/tmp/test_matrix",
        store_root="C:/tmp/store",
    )

    assert matrix["schema"] == "harness.benchmark-execution-matrix/v1"
    assert matrix["execution_policy"]["does_not_execute"] is True
    assert [tier["tier"] for tier in matrix["tiers"]] == ["dry", "focused", "full"]
    assert matrix["expected_provider_roles"] == ["flywheel", "codex", "opencode"]
    assert matrix["summary"]["long_running_steps"] > 0
    assert matrix["summary"]["operator_approval_required_steps"] == matrix["summary"]["long_running_steps"]


def test_matrix_records_reproducible_commands_and_evidence_gates():
    matrix = build_matrix(providers="serve,codex,opencode", run_id="run_test", artifact_dir="C:/tmp/test_matrix")
    steps = {step["step_id"]: step for step in matrix["steps"]}

    assert steps["profile_contract"]["tier"] == "dry"
    assert steps["profile_contract"]["expected_schemas"] == ["harness.benchmark-profile-manifest/v1"]
    assert "dataset_lane_weight_sum" in steps["profile_contract"]["evidence_gates"]
    assert steps["focused_closed_loop_seed"]["operator_approval_required"] is True
    assert "serve,codex,opencode" in steps["focused_closed_loop_seed"]["command"]
    assert "harness.benchmark-profile-coverage/v1" in steps["coverage_after_execution"]["expected_schemas"]
    assert "pressure_variable_coverage_rate" in steps["coverage_after_execution"]["evidence_gates"]
    assert "harness.comparison-report/v1" in steps["harness_comparison"]["expected_schemas"]
    assert "harness.model-endpoint-profiles/v1" in steps["local_model_endpoint_profiles"]["expected_schemas"]
    assert steps["adapter_runtime_matrix"]["tier"] == "dry"
    assert steps["adapter_runtime_matrix"]["expected_schemas"] == ["harness.adapter-runtime-matrix/v1"]
    assert "blocking_gates" in steps["adapter_runtime_matrix"]["evidence_gates"]
    assert "adapter_runtime_matrix.json" in " ".join(steps["adapter_runtime_matrix"]["command"])
    assert steps["schematic_drift_check"]["tier"] == "dry"
    assert steps["schematic_drift_check"]["expected_schemas"] == ["harness.schematic-drift-check/v1"]
    assert "stale_prose_absent" in steps["schematic_drift_check"]["evidence_gates"]
    assert steps["cross_harness_manifest"]["tier"] == "dry"
    assert "harness.cross-harness-manifest/v1" in steps["cross_harness_manifest"]["expected_schemas"]
    assert "same_task_prompt_hashes" in steps["cross_harness_manifest"]["evidence_gates"]
    assert "cross_harness_manifest.json" in " ".join(steps["coverage_after_execution"]["command"])
    assert steps["embodied_realtime_plan"]["tier"] == "dry"
    assert steps["embodied_realtime_plan"]["expected_schemas"] == ["harness.embodied-realtime-multimodal/v1"]
    assert "dry_scorecard_rows_not_executed" in steps["embodied_realtime_plan"]["evidence_gates"]
    assert "embodied_realtime_multimodal_plan.json" in " ".join(steps["coverage_after_execution"]["command"])
    assert steps["model_card_claim_table"]["tier"] == "dry"
    assert steps["model_card_claim_table"]["expected_schemas"] == ["harness.model-card-claim-table/v1"]
    assert "unresolved_fields" in steps["model_card_claim_table"]["evidence_gates"]
    assert "model_card_claim_table.json" in " ".join(steps["model_card_claim_table"]["command"])
    assert "model_card_claim_table.json" in " ".join(steps["coverage_after_execution"]["command"])
    assert "--profile-artifact" in steps["local_model_endpoint_gate"]["command"]
    assert "model_endpoint_profiles.json" in " ".join(steps["local_model_endpoint_gate"]["command"])
    assert "--run-id" not in steps["focused_closed_loop_seed"]["command"]
    assert "--store-root" not in steps["focused_closed_loop_seed"]["command"]


def test_render_markdown_surfaces_tiers_and_approval():
    matrix = build_matrix(providers="serve,codex", run_id="run_test", artifact_dir="C:/tmp/test_matrix")

    markdown = render_markdown(matrix)

    assert "# Benchmark execution matrix" in markdown
    assert "## Tiers" in markdown
    assert "focused_closed_loop_seed" in markdown
    assert "true" in markdown


def test_main_writes_json_and_markdown(tmp_path, capsys):
    out = tmp_path / "matrix.json"
    md = tmp_path / "matrix.md"

    rc = main([
        "--providers",
        "serve,codex",
        "--run-id",
        "run_test",
        "--artifact-dir",
        str(tmp_path / "artifacts"),
        "--out",
        str(out),
        "--markdown-out",
        str(md),
    ])

    assert rc == 0
    assert json.loads(out.read_text(encoding="utf-8"))["schema"] == "harness.benchmark-execution-matrix/v1"
    assert "# Benchmark execution matrix" in md.read_text(encoding="utf-8")
    assert json.loads(capsys.readouterr().out)["summary"]["steps"] > 0
