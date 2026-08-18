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
    assert steps["adapter_runtime_matrix"]["tier"] == "focused"
    assert steps["adapter_runtime_matrix"]["expected_schemas"] == ["harness.adapter-runtime-matrix/v1"]
    assert "blocking_gates" in steps["adapter_runtime_matrix"]["evidence_gates"]
    assert "adapter_runtime_matrix.json" in " ".join(steps["adapter_runtime_matrix"]["command"])
    assert steps["schematic_drift_check"]["tier"] == "dry"
    assert steps["schematic_drift_check"]["expected_schemas"] == ["harness.schematic-drift-check/v1"]
    assert "stale_prose_absent" in steps["schematic_drift_check"]["evidence_gates"]
    assert steps["cross_harness_manifest"]["tier"] == "dry"
    assert "harness.cross-harness-manifest/v1" in steps["cross_harness_manifest"]["expected_schemas"]
    assert "same_task_prompt_hashes" in steps["cross_harness_manifest"]["evidence_gates"]
    assert "spark-pilot" in " ".join(steps["coverage_after_execution"]["command"])
    assert steps["embodied_realtime_plan"]["tier"] == "dry"
    assert steps["embodied_realtime_plan"]["expected_schemas"] == ["harness.embodied-realtime-multimodal/v1"]
    assert "dry_scorecard_rows_not_executed" in steps["embodied_realtime_plan"]["evidence_gates"]
    assert steps["model_card_claim_table"]["tier"] == "dry"
    assert steps["model_card_claim_table"]["expected_schemas"] == ["harness.model-card-claim-table/v1"]
    assert "unresolved_fields" in steps["model_card_claim_table"]["evidence_gates"]
    assert "model_card_claim_table.json" in " ".join(steps["model_card_claim_table"]["command"])
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


def test_cross_harness_execution_is_after_gates_before_synthesis_and_spark_only_comparison():
    matrix = build_matrix(providers="codex,serve", run_id="run", artifact_dir="artifacts/matrix")
    steps = matrix["steps"]
    order = {row["step_id"]: index for index, row in enumerate(steps)}

    assert order["local_model_endpoint_gate"] < order["cross_harness_execution"]
    assert order["endpoint_auth_status"] < order["local_model_endpoint_gate"] < order["adapter_runtime_matrix"]
    assert order["cross_harness_execution"] < order["coverage_after_execution"]
    assert order["cross_harness_execution"] < order["harness_comparison"]
    comparison_command = " ".join(next(row["command"] for row in steps if row["step_id"] == "harness_comparison"))
    normalized = comparison_command.replace("\\", "/")
    assert "spark-pilot/run-spark/comparison-input.json" in normalized
    assert "local-baseline" not in normalized
    full = next(row for row in steps if row["step_id"] == "full_provider_matrix")
    assert full["executable"] is False
    assert full["blocked_reason"] == "84_attempt_expansion_prohibited"
    commands = " ".join(part for row in steps for part in row["command"])
    assert "C:/dev/local-model" not in commands
    profile = next(row for row in steps if row["step_id"] == "profile_contract")["command"]
    assert profile[profile.index("--benchmark-ids") + 1] == "cross_harness_reproducibility_matrix"
    assert profile[profile.index("--providers") + 1] == "codex_harness,flywheel_harness,local_14b,local_32b"
    runtime = next(row for row in steps if row["step_id"] == "adapter_runtime_matrix")["command"]
    assert all(flag in runtime for flag in ("--endpoint-auth-status", "--endpoint-gate", "--endpoint-gate-run-id", "--endpoint-gate-max-age-seconds"))
    mapping = next(row for row in steps if row["step_id"] == "cross_harness_integration_map")["command"]
    assert "--out" in mapping and "--markdown-out" in mapping
    auth = next(row for row in steps if row["step_id"] == "endpoint_auth_status")["command"]
    execution = next(row for row in steps if row["step_id"] == "cross_harness_execution")["command"]
    assert auth[auth.index("--require") + 1] == "codex_subscription"
    assert "--strict-exit" in execution and execution[execution.index("--benchmark-timeout-seconds") + 1] == "10800"
    stored = build_matrix(providers="codex", run_id="run", artifact_dir="artifacts/matrix", store_root="artifacts/store")
    stored_execution = next(row for row in stored["steps"] if row["step_id"] == "cross_harness_execution")["command"]
    assert stored_execution[stored_execution.index("--store-root") + 1] == "artifacts/store"
    stored_map = next(row for row in stored["steps"] if row["step_id"] == "cross_harness_integration_map")["command"]
    assert stored_map[stored_map.index("--store-root") + 1] == "artifacts/store"
    execution = next(row for row in steps if row["step_id"] == "cross_harness_execution")
    seed = execution["command"][execution["command"].index("--out") + 1]
    assert seed in execution["expected_artifacts"]
    outcome = next(row for row in steps if row["step_id"] == "outcome_synthesis")["command"]
    assert outcome[outcome.index("--input") + 1] == seed
    assert mapping[mapping.index("--seed") + 1] == seed
    coverage = next(row for row in steps if row["step_id"] == "coverage_after_execution")["command"]
    assert coverage[coverage.index("--artifacts") + 1].split(";") == execution["expected_artifacts"][1:]
    assert "--flywheel-role flywheel_harness --codex-role codex_harness" in comparison_command
    assert all(row["command_text"] == " ".join(row["command"]) for row in steps)
    assert order["lane_snapshot_before"] < order["endpoint_auth_status"] and order["outcome_synthesis"] < order["lane_snapshot_after"] < order["cross_harness_integration_map"]
    for lane_id, flag in (("lane_snapshot_before", "--lane-before"), ("lane_snapshot_after", "--lane-after")):
        producer = next(row for row in steps if row["step_id"] == lane_id)
        assert "lane_roster(probe=True)" in producer["command"][2] and producer["expected_artifacts"][0] == mapping[mapping.index(flag) + 1]
    source_commit = execution["command"][execution["command"].index("--cross-harness-source-commit") + 1]
    assert len(source_commit) == 40 and source_commit != "HEAD"
