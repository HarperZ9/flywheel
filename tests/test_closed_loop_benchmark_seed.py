from pathlib import Path

from scripts.run_closed_loop_benchmark_seed import build_report, build_steps, summarize_results


class Args:
    python = "python"
    store_root = "C:/tmp/store"
    preflight_timeout_seconds = 120.0
    index_timeout_seconds = 180.0
    benchmark_timeout_seconds = 600.0
    context_roots = "C:/tmp;C:/dev/local-model/.scratch"
    context_max_depth = 3
    context_max_entries_per_root = 500
    tool_readiness_tools = "index,forum,gather,crucible,telos,aleph,mneme,relay,plexus,pubscan"
    tool_readiness_base_root = "C:/dev/public"
    tool_readiness_tool_root = ["aleph=C:/dev/aleph"]
    model_release_models = "14B,32B"
    model_release_base_root = "E:/local-model-run"
    model_release_artifact_roots = "C:/dev/local-model/artifacts;C:/tmp"
    model_release_max_entries = 200
    model_publish_name_prefix = "Flywheel-Local-Coder"
    model_endpoint_gate_timeout_seconds = 30.0
    gather_readiness_root = "C:/dev/public/gather"
    gather_readiness_config_roots = "C:/dev/local-model/configs"
    gather_readiness_config_pattern = "gather-*.json"
    gather_readiness_credential_vars = "GATHER_DISCORD_BOT_TOKEN,DISCORD_TOKEN"
    gather_readiness_max_configs = 100
    skip_harness_registry = False
    skip_benchmark_execution_matrix = False
    benchmark_profile_providers = "serve,codex,ollama,claude,opencode,dry"
    benchmark_profile_artifact_roots = "C:/tmp;C:/dev/local-model/artifacts"
    benchmark_profile_max_artifacts = 200
    schematic_graph = "C:/dev/local-model/project-docs/schematics/closed-loop-integration.graph.json"
    schematic_report = "C:/dev/local-model/project-docs/records/CLOSED-LOOP-INTEGRATION-SCHEMATIC-2026-07-09.md"
    agentic_task_set = "C:/dev/local-model/benchmarks/agentic-task-set-v1.json"
    agentic_task_adapter = "C:/dev/local-model/benchmarks/agentic-task-set-adapter-v1.json"
    agentic_task_provider_roles = "dry"
    cross_harness_contract = "C:/dev/local-model/benchmarks/cross-harness-adapter-contract-v1.json"
    cross_harness_provider_roles = "codex_harness,flywheel_harness,claude_code,opencode,local_14b,local_32b,dry"
    embodied_realtime_contract = "C:/dev/local-model/benchmarks/embodied-realtime-multimodal-v1.json"
    embodied_realtime_providers = "dry"
    embodied_realtime_latency_budgets_ms = "250,500,1000"
    model_card_claim_contract = "C:/dev/local-model/benchmarks/embodied-realtime-multimodal-v1.json"
    model_card_claim_evidence = ""
    skip_benchmark_coverage = False
    workspace_root = "C:/dev"
    index_root = "C:/dev/public/index"
    index_context_root = "C:/dev/local-model"
    index_budget = 12000
    index_focus = "local-model harness"
    index_hops = 2
    source_mined_providers = "serve,codex"
    source_mined_max_cases = 2
    governed_providers = "serve,codex"
    governed_backend_max_scenarios = 2
    unisonai_providers = "dry,serve,codex"
    unisonai_repair_json = True
    classifier_friction_providers = "dry,serve,codex"
    classifier_friction_modes_to_test = "guardrail_on,guardrail_off,accountability_first"
    classifier_friction_provider_modes = "plan"
    classifier_friction_endpoint_model = "gpt-5.3-codex-spark"
    classifier_friction_local_model = "qwen2.5:7b"
    classifier_friction_max_tasks = 1
    classifier_friction_timeout_seconds = 120
    classifier_friction_max_tokens = 500
    classifier_friction_allow_online = False
    forum_route_text = []
    mcp_tool_health_tools = "index,forum,telos,gather,crucible,aleph,mneme,relay,plexus,pubscan,local-model"
    mcp_tool_health_observation = []
    skip_harness_manifest = False
    skip_context_inventory = False
    skip_tool_readiness = False
    skip_tool_hardening_plan = False
    skip_model_endpoint_profiles = False
    skip_adapter_runtime_matrix = False
    skip_model_endpoint_gate = False
    skip_model_release_readiness = False
    skip_model_publish_plan = False
    skip_gather_readiness = False
    skip_benchmark_profile = False
    skip_schematic_drift = False
    skip_agentic_task_manifest = False
    skip_cross_harness_manifest = False
    skip_embodied_realtime = False
    skip_model_card_claims = False
    skip_classifier_friction = False
    skip_m7_source_mined = False
    skip_m7_governed = False
    skip_unisonai = False
    skip_harness_comparison = False
    skip_forum_route_receipts = False
    skip_mcp_tool_health = False


def test_build_steps_thread_same_store_and_run_id_through_commands(tmp_path):
    steps = build_steps(Args(), run_id="run_123", artifact_dir=tmp_path)

    assert [step.step_id for step in steps] == [
        "endpoint_auth_status",
        "forum_route_receipts",
        "mcp_tool_health",
        "harness_executable_manifest",
        "harness_command_registry",
        "benchmark_execution_matrix",
        "benchmark_profile",
        "schematic_drift_check",
        "agentic_task_manifest",
        "cross_harness_manifest",
        "embodied_realtime_multimodal_plan",
        "model_card_claim_table",
        "context_inventory",
        "tool_readiness",
        "tool_hardening_plan",
        "model_endpoint_profiles",
        "adapter_runtime_matrix",
        "model_endpoint_gate",
        "model_release_readiness",
        "model_publish_plan",
        "gather_readiness",
        "pubscan_resource_profiles",
        "index_context_envelope",
        "classifier_friction",
        "m7_source_mined",
        "m7_governed_agent",
        "unisonai_stateful_provider_matrix",
        "benchmark_profile_coverage",
        "harness_comparison_report",
    ]
    for step in steps:
        assert "--store-root" in step.command
        assert "C:/tmp/store" in step.command
        assert "--run-id" in step.command
        assert "run_123" in step.command


def test_summarize_results_counts_failed_and_timeout_steps():
    summary = summarize_results([
        {"status": "ok", "expected_artifacts": ["a.json"]},
        {"status": "failed", "expected_artifacts": ["b.json"]},
        {"status": "timeout", "expected_artifacts": ["c.json"]},
    ])

    assert summary["steps"] == 3
    assert summary["ok_steps"] == 1
    assert summary["failed_steps"] == 1
    assert summary["timeout_steps"] == 1
    assert summary["artifact_paths"] == ["a.json", "b.json", "c.json"]


def test_build_report_dry_plan_preserves_planned_commands(tmp_path):
    steps = build_steps(Args(), run_id="dry_plan", artifact_dir=tmp_path)
    report = build_report(
        run_id="dry_plan",
        artifact_dir=Path(tmp_path),
        store_root="C:/tmp/store",
        steps=steps,
        results=[],
        dry_plan=True,
    )

    assert report["schema"] == "harness.closed-loop-benchmark-seed/v1"
    assert report["dry_plan"] is True
    assert report["summary"]["steps"] == len(steps)
    assert report["planned_steps"][0]["step_id"] == "endpoint_auth_status"
    assert report["planned_steps"][1]["step_id"] == "forum_route_receipts"
    assert report["planned_steps"][2]["step_id"] == "mcp_tool_health"
    assert report["planned_steps"][3]["step_id"] == "harness_executable_manifest"
    assert report["planned_steps"][4]["step_id"] == "harness_command_registry"
    assert report["planned_steps"][5]["step_id"] == "benchmark_execution_matrix"
    assert report["planned_steps"][6]["step_id"] == "benchmark_profile"
    assert report["planned_steps"][7]["step_id"] == "schematic_drift_check"
    assert report["planned_steps"][8]["step_id"] == "agentic_task_manifest"
    assert report["planned_steps"][9]["step_id"] == "cross_harness_manifest"
    assert report["planned_steps"][10]["step_id"] == "embodied_realtime_multimodal_plan"
    assert report["planned_steps"][11]["step_id"] == "model_card_claim_table"
    assert report["planned_steps"][12]["step_id"] == "context_inventory"
    assert report["planned_steps"][13]["step_id"] == "tool_readiness"
    assert report["planned_steps"][14]["step_id"] == "tool_hardening_plan"
    assert report["planned_steps"][15]["step_id"] == "model_endpoint_profiles"
    assert report["planned_steps"][16]["step_id"] == "adapter_runtime_matrix"
    assert report["planned_steps"][17]["step_id"] == "model_endpoint_gate"
    assert report["planned_steps"][18]["step_id"] == "model_release_readiness"
    assert report["planned_steps"][19]["step_id"] == "model_publish_plan"
    assert report["planned_steps"][20]["step_id"] == "gather_readiness"


def test_forum_route_receipts_step_records_route_text_without_calling_forum(tmp_path):
    steps = build_steps(Args(), run_id="run_123", artifact_dir=tmp_path)
    forum = [step for step in steps if step.step_id == "forum_route_receipts"][0]

    assert "scripts/run_forum_route_receipts.py" in forum.command
    assert "--route" in forum.command
    assert "Route the active Codex/Flywheel local-model closed-loop harness objective." in forum.command
    assert str(tmp_path / "forum_route_receipts.json") in forum.expected_artifacts
    assert str(tmp_path / "forum_route_receipts.md") in forum.expected_artifacts


def test_mcp_tool_health_step_records_tool_observation_metadata(tmp_path):
    steps = build_steps(Args(), run_id="run_123", artifact_dir=tmp_path)
    health = [step for step in steps if step.step_id == "mcp_tool_health"][0]

    assert "scripts/run_mcp_tool_health_receipts.py" in health.command
    assert "--tools" in health.command
    assert "index,forum,telos,gather,crucible,aleph,mneme,relay,plexus,pubscan,local-model" in health.command
    assert str(tmp_path / "mcp_tool_health.json") in health.expected_artifacts
    assert str(tmp_path / "mcp_tool_health.md") in health.expected_artifacts


def test_benchmark_execution_matrix_step_records_run_plan_without_running_providers(tmp_path):
    steps = build_steps(Args(), run_id="run_123", artifact_dir=tmp_path)
    matrix = [step for step in steps if step.step_id == "benchmark_execution_matrix"][0]

    assert "scripts/run_benchmark_execution_matrix.py" in matrix.command
    assert "--providers" in matrix.command
    assert "serve,codex,ollama,claude,opencode,dry" in matrix.command
    assert "--artifact-dir" in matrix.command
    assert str(tmp_path) in matrix.command
    assert str(tmp_path / "benchmark_execution_matrix.json") in matrix.expected_artifacts
    assert str(tmp_path / "benchmark_execution_matrix.md") in matrix.expected_artifacts


def test_tool_hardening_plan_step_consumes_tool_readiness_artifact(tmp_path):
    steps = build_steps(Args(), run_id="run_123", artifact_dir=tmp_path)
    hardening = [step for step in steps if step.step_id == "tool_hardening_plan"][0]

    assert "scripts/run_tool_hardening_plan.py" in hardening.command
    assert "--readiness-artifact" in hardening.command
    assert str(tmp_path / "tool_readiness.json") in hardening.command
    assert str(tmp_path / "tool_hardening_plan.json") in hardening.expected_artifacts


def test_tool_readiness_step_covers_flagship_tools_and_aleph_root(tmp_path):
    steps = build_steps(Args(), run_id="run_123", artifact_dir=tmp_path)
    readiness = [step for step in steps if step.step_id == "tool_readiness"][0]

    assert "scripts/run_tool_readiness_receipts.py" in readiness.command
    assert "--tools" in readiness.command
    assert "index,forum,gather,crucible,telos,aleph,mneme,relay,plexus,pubscan" in readiness.command
    assert "--tool-root" in readiness.command
    assert "aleph=C:/dev/aleph" in readiness.command


def test_index_context_step_uses_bounded_context_root(tmp_path):
    steps = build_steps(Args(), run_id="run_123", artifact_dir=tmp_path)
    index = [step for step in steps if step.step_id == "index_context_envelope"][0]

    assert "scripts/run_index_receipt.py" in index.command
    root_pos = index.command.index("--root")
    assert index.command[root_pos + 1] == "C:/dev/local-model"
    assert "--focus" in index.command
    assert "local-model harness" in index.command


def test_classifier_friction_step_writes_deterministic_artifacts(tmp_path):
    steps = build_steps(Args(), run_id="run_123", artifact_dir=tmp_path)
    classifier = [step for step in steps if step.step_id == "classifier_friction"][0]

    assert "scripts/run_classifier_friction_benchmark.py" in classifier.command
    assert "--providers" in classifier.command
    assert "dry,serve,codex" in classifier.command
    assert str(tmp_path / "classifier_friction_benchmark.json") in classifier.expected_artifacts
    assert str(tmp_path / "classifier_friction_benchmark.md") in classifier.expected_artifacts


def test_model_release_step_consumes_model_endpoint_profile_artifact(tmp_path):
    steps = build_steps(Args(), run_id="run_123", artifact_dir=tmp_path)
    release = [step for step in steps if step.step_id == "model_release_readiness"][0]

    assert "--endpoint-profile-artifacts" in release.command
    assert str(tmp_path / "model_endpoint_profiles.json") in release.command


def test_model_endpoint_gate_step_consumes_endpoint_profiles(tmp_path):
    steps = build_steps(Args(), run_id="run_123", artifact_dir=tmp_path)
    gate = [step for step in steps if step.step_id == "model_endpoint_gate"][0]

    assert "scripts/run_model_endpoint_gate.py" in gate.command
    assert "--profile-artifact" in gate.command
    assert str(tmp_path / "model_endpoint_profiles.json") in gate.command
    assert str(tmp_path / "model_endpoint_gate.json") in gate.expected_artifacts


def test_adapter_runtime_matrix_step_consumes_endpoint_and_auth_metadata(tmp_path):
    steps = build_steps(Args(), run_id="run_123", artifact_dir=tmp_path)
    matrix = [step for step in steps if step.step_id == "adapter_runtime_matrix"][0]

    assert "scripts/run_adapter_runtime_matrix.py" in matrix.command
    assert "--contract" in matrix.command
    assert "C:/dev/local-model/benchmarks/cross-harness-adapter-contract-v1.json" in matrix.command
    assert "--endpoint-profiles" in matrix.command
    assert str(tmp_path / "model_endpoint_profiles.json") in matrix.command
    assert "--endpoint-auth-status" in matrix.command
    assert str(tmp_path / "endpoint_auth_status.json") in matrix.command
    assert str(tmp_path / "adapter_runtime_matrix.json") in matrix.expected_artifacts
    assert str(tmp_path / "adapter_runtime_matrix.md") in matrix.expected_artifacts


def test_model_publish_plan_step_consumes_model_release_readiness(tmp_path):
    steps = build_steps(Args(), run_id="run_123", artifact_dir=tmp_path)
    publish = [step for step in steps if step.step_id == "model_publish_plan"][0]

    assert "scripts/run_model_publish_plan.py" in publish.command
    assert "--release-readiness-artifact" in publish.command
    assert str(tmp_path / "model_release_readiness.json") in publish.command
    assert str(tmp_path / "model_publish_plan.json") in publish.expected_artifacts


def test_registry_step_writes_html_and_json_summary(tmp_path):
    steps = build_steps(Args(), run_id="run_123", artifact_dir=tmp_path)
    registry = [step for step in steps if step.step_id == "harness_command_registry"][0]

    assert "registry" in registry.command
    assert "--summary-out" in registry.command
    assert str(tmp_path / "harness_command_registry.json") in registry.expected_artifacts
    assert str(tmp_path / "harness_command_registry.html") in registry.expected_artifacts


def test_benchmark_profile_step_records_weighted_suite_manifest(tmp_path):
    steps = build_steps(Args(), run_id="run_123", artifact_dir=tmp_path)
    profile = [step for step in steps if step.step_id == "benchmark_profile"][0]

    assert "scripts/run_benchmark_profile_manifest.py" in profile.command
    assert "--providers" in profile.command
    assert str(tmp_path / "benchmark_profile_manifest.json") in profile.expected_artifacts
    assert str(tmp_path / "benchmark_profile_manifest.md") in profile.expected_artifacts


def test_agentic_task_manifest_step_is_metadata_only(tmp_path):
    steps = build_steps(Args(), run_id="run_123", artifact_dir=tmp_path)
    manifest = [step for step in steps if step.step_id == "agentic_task_manifest"][0]

    assert "scripts/run_agentic_task_set_manifest.py" in manifest.command
    assert "--task-set" in manifest.command
    assert "C:/dev/local-model/benchmarks/agentic-task-set-v1.json" in manifest.command
    assert "--provider-roles" in manifest.command
    assert "dry" in manifest.command
    assert str(tmp_path / "agentic_task_manifest.json") in manifest.expected_artifacts
    assert str(tmp_path / "agentic_task_manifest.md") in manifest.expected_artifacts


def test_schematic_drift_step_is_metadata_only(tmp_path):
    steps = build_steps(Args(), run_id="run_123", artifact_dir=tmp_path)
    drift = [step for step in steps if step.step_id == "schematic_drift_check"][0]

    assert "scripts/run_schematic_drift_check.py" in drift.command
    assert "--graph" in drift.command
    assert "C:/dev/local-model/project-docs/schematics/closed-loop-integration.graph.json" in drift.command
    assert "--report" in drift.command
    assert "C:/dev/local-model/project-docs/records/CLOSED-LOOP-INTEGRATION-SCHEMATIC-2026-07-09.md" in drift.command
    assert str(tmp_path / "schematic_drift_check.json") in drift.expected_artifacts
    assert str(tmp_path / "schematic_drift_check.md") in drift.expected_artifacts


def test_embodied_realtime_step_is_metadata_only(tmp_path):
    steps = build_steps(Args(), run_id="run_123", artifact_dir=tmp_path)
    embodied = [step for step in steps if step.step_id == "embodied_realtime_multimodal_plan"][0]

    assert "scripts/run_embodied_realtime_multimodal_plan.py" in embodied.command
    assert "--contract" in embodied.command
    assert "C:/dev/local-model/benchmarks/embodied-realtime-multimodal-v1.json" in embodied.command
    assert "--providers" in embodied.command
    assert "dry" in embodied.command
    assert "--latency-budgets-ms" in embodied.command
    assert "250,500,1000" in embodied.command
    assert str(tmp_path / "embodied_realtime_multimodal_plan.json") in embodied.expected_artifacts
    assert str(tmp_path / "embodied_realtime_multimodal_plan.md") in embodied.expected_artifacts


def test_model_card_claim_table_step_is_metadata_only(tmp_path):
    steps = build_steps(Args(), run_id="run_123", artifact_dir=tmp_path)
    claims = [step for step in steps if step.step_id == "model_card_claim_table"][0]

    assert "scripts/run_model_card_claim_table.py" in claims.command
    assert "--contract" in claims.command
    assert "C:/dev/local-model/benchmarks/embodied-realtime-multimodal-v1.json" in claims.command
    assert "--artifact-dir" in claims.command
    assert str(tmp_path / "model_card_claim_table.json") in claims.expected_artifacts
    assert str(tmp_path / "model_card_claim_table.md") in claims.expected_artifacts


def test_cross_harness_manifest_step_is_metadata_only(tmp_path):
    steps = build_steps(Args(), run_id="run_123", artifact_dir=tmp_path)
    manifest = [step for step in steps if step.step_id == "cross_harness_manifest"][0]

    assert "scripts/run_cross_harness_manifest.py" in manifest.command
    assert "--task-set" in manifest.command
    assert "C:/dev/local-model/benchmarks/agentic-task-set-v1.json" in manifest.command
    assert "--contract" in manifest.command
    assert "C:/dev/local-model/benchmarks/cross-harness-adapter-contract-v1.json" in manifest.command
    assert "--provider-roles" in manifest.command
    assert "codex_harness,flywheel_harness,claude_code,opencode,local_14b,local_32b,dry" in manifest.command
    assert str(tmp_path / "cross_harness_manifest.json") in manifest.expected_artifacts
    assert str(tmp_path / "cross_harness_manifest.md") in manifest.expected_artifacts


def test_benchmark_profile_coverage_step_compares_profile_against_scorecards(tmp_path):
    steps = build_steps(Args(), run_id="run_123", artifact_dir=tmp_path)
    coverage = [step for step in steps if step.step_id == "benchmark_profile_coverage"][0]

    assert "scripts/run_benchmark_profile_coverage.py" in coverage.command
    assert "--profile" in coverage.command
    assert str(tmp_path / "benchmark_profile_manifest.json") in coverage.command
    assert "--artifacts" in coverage.command
    assert str(tmp_path / "model_endpoint_profiles.json") in coverage.command
    assert str(tmp_path / "model_endpoint_gate.json") in coverage.command
    assert str(tmp_path / "adapter_runtime_matrix.json") in coverage.command
    assert str(tmp_path / "agentic_task_manifest.json") in coverage.command
    assert str(tmp_path / "cross_harness_manifest.json") in coverage.command
    assert str(tmp_path / "embodied_realtime_multimodal_plan.json") in coverage.command
    assert str(tmp_path / "model_card_claim_table.json") in coverage.command
    assert str(tmp_path / "classifier_friction_benchmark.json") in coverage.command
    assert str(tmp_path / "m7_source_mined_scorecard.json") in coverage.command
    assert str(tmp_path / "benchmark_profile_coverage.json") in coverage.expected_artifacts


def test_harness_comparison_step_consumes_scorecard_artifacts(tmp_path):
    steps = build_steps(Args(), run_id="run_123", artifact_dir=tmp_path)
    comparison = [step for step in steps if step.step_id == "harness_comparison_report"][0]

    assert "scripts/run_harness_comparison_report.py" in comparison.command
    assert "--artifacts" in comparison.command
    assert str(tmp_path / "m7_source_mined_scorecard.json") in comparison.command
    assert str(tmp_path / "classifier_friction_benchmark.json") in comparison.command
    assert str(tmp_path / "harness_comparison_report.json") in comparison.expected_artifacts


def test_seed_report_artifact_label_is_stable():
    expected_label = "closed-loop-seed-report-json"

    assert expected_label == "closed-loop-seed-report-json"
