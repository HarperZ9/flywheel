from pathlib import Path

from scripts.run_harness_cli import (
    build_command,
    build_manifest,
    build_parser,
    build_registry_summary,
    format_command,
    render_manifest_markdown,
    render_registry_html,
)


def test_dispatcher_inserts_repo_root_before_harness_import():
    script = Path("scripts/run_harness_cli.py").read_text(encoding="utf-8")

    assert "sys.path.insert(0, str(Path(__file__).resolve().parent.parent))" in script
    assert script.index("sys.path.insert") < script.index("from harness.file_backed_store")


def parse(argv):
    return build_parser().parse_args(argv)


def test_plan_command_targets_closed_loop_dry_plan():
    args = parse(["plan", "--out", "C:/tmp/plan.json"])
    command = build_command(args, repo_root=Path("C:/dev/local-model"))

    assert command[:2] == [args.python, "scripts/run_closed_loop_benchmark_seed.py"]
    assert "--dry-plan" in command
    assert "C:/tmp/plan.json" in command


def test_benchmarks_command_targets_profile_manifest():
    args = parse([
        "benchmarks",
        "--providers",
        "serve,codex",
        "--artifact-roots",
        "C:/tmp",
        "--out",
        "C:/tmp/benchmark_profile.json",
    ])
    command = build_command(args, repo_root=Path("C:/dev/local-model"))

    assert command[:2] == [args.python, "scripts/run_benchmark_profile_manifest.py"]
    assert "--providers" in command
    assert "serve,codex" in command
    assert "--artifact-roots" in command
    assert "C:/tmp" in command


def test_forum_route_command_targets_route_receipt_generator():
    args = parse([
        "forum-route",
        "--route",
        "Route the closed-loop harness work.",
        "--observed-confidence",
        "0.5",
        "--observed-needs-escalation",
        "false",
        "--observed-domain",
        "model-foundry",
        "--out",
        "C:/tmp/forum_route_receipts.json",
    ])
    command = build_command(args, repo_root=Path("C:/dev/local-model"))

    assert command[:2] == [args.python, "scripts/run_forum_route_receipts.py"]
    assert "--route" in command
    assert "Route the closed-loop harness work." in command
    assert "--observed-confidence" in command
    assert "0.5" in command
    assert "--observed-needs-escalation" in command
    assert "false" in command
    assert "--observed-domain" in command
    assert "model-foundry" in command
    assert "C:/tmp/forum_route_receipts.json" in command


def test_mcp_health_command_targets_tool_health_generator():
    args = parse([
        "mcp-health",
        "--tools",
        "index,forum,telos",
        "--observation",
        "index=TRANSPORT_CLOSED|transport_closed|Transport closed",
        "--out",
        "C:/tmp/mcp_tool_health.json",
    ])
    command = build_command(args, repo_root=Path("C:/dev/local-model"))

    assert command[:2] == [args.python, "scripts/run_mcp_tool_health_receipts.py"]
    assert "--tools" in command
    assert "index,forum,telos" in command
    assert "--observation" in command
    assert "index=TRANSPORT_CLOSED|transport_closed|Transport closed" in command
    assert "C:/tmp/mcp_tool_health.json" in command


def test_benchmark_coverage_command_targets_profile_coverage_report():
    args = parse([
        "benchmark-coverage",
        "--profile",
        "C:/tmp/profile.json",
        "--artifacts",
        "C:/tmp/m7.json;C:/tmp/unisonai.json",
        "--out",
        "C:/tmp/coverage.json",
    ])
    command = build_command(args, repo_root=Path("C:/dev/local-model"))

    assert command[:2] == [args.python, "scripts/run_benchmark_profile_coverage.py"]
    assert "--profile" in command
    assert "C:/tmp/profile.json" in command
    assert "--artifacts" in command
    assert "C:/tmp/m7.json;C:/tmp/unisonai.json" in command


def test_comparison_command_targets_harness_comparison_report():
    args = parse([
        "comparison",
        "--artifacts",
        "C:/tmp/m7.json;C:/tmp/classifier.json",
        "--out",
        "C:/tmp/comparison.json",
    ])
    command = build_command(args, repo_root=Path("C:/dev/local-model"))

    assert command[:2] == [args.python, "scripts/run_harness_comparison_report.py"]
    assert "--artifacts" in command
    assert "C:/tmp/m7.json;C:/tmp/classifier.json" in command
    assert "--flywheel-role" in command
    assert "--codex-role" in command
    assert "C:/tmp/comparison.json" in command


def test_tool_hardening_command_targets_hardening_plan():
    args = parse([
        "tool-hardening",
        "--readiness-artifact",
        "C:/tmp/tool_readiness.json",
        "--out",
        "C:/tmp/tool_hardening_plan.json",
    ])
    command = build_command(args, repo_root=Path("C:/dev/local-model"))

    assert command[:2] == [args.python, "scripts/run_tool_hardening_plan.py"]
    assert "--readiness-artifact" in command
    assert "C:/tmp/tool_readiness.json" in command
    assert "C:/tmp/tool_hardening_plan.json" in command


def test_endpoint_gate_command_targets_model_endpoint_gate():
    args = parse([
        "endpoint-gate",
        "--profile-artifact",
        "C:/tmp/model_endpoint_profiles.json",
        "--models",
        "14B",
        "--backends",
        "serve",
        "--strict-exit",
        "--out",
        "C:/tmp/model_endpoint_gate.json",
    ])
    command = build_command(args, repo_root=Path("C:/dev/local-model"))

    assert command[:2] == [args.python, "scripts/run_model_endpoint_gate.py"]
    assert "--profile-artifact" in command
    assert "C:/tmp/model_endpoint_profiles.json" in command
    assert "--models" in command
    assert "14B" in command
    assert "--backends" in command
    assert "serve" in command
    assert "--strict-exit" in command
    assert "C:/tmp/model_endpoint_gate.json" in command


def test_model_publish_command_targets_publish_plan():
    args = parse([
        "model-publish",
        "--release-readiness-artifact",
        "C:/tmp/model_release_readiness.json",
        "--name-prefix",
        "Warden-Coder",
        "--out",
        "C:/tmp/model_publish_plan.json",
    ])
    command = build_command(args, repo_root=Path("C:/dev/local-model"))

    assert command[:2] == [args.python, "scripts/run_model_publish_plan.py"]
    assert "--release-readiness-artifact" in command
    assert "C:/tmp/model_release_readiness.json" in command
    assert "--name-prefix" in command
    assert "Warden-Coder" in command
    assert "C:/tmp/model_publish_plan.json" in command


def test_execution_matrix_command_targets_matrix_generator():
    args = parse([
        "execution-matrix",
        "--providers",
        "serve,codex",
        "--artifact-dir",
        "C:/tmp/matrix",
        "--out",
        "C:/tmp/benchmark_execution_matrix.json",
    ])
    command = build_command(args, repo_root=Path("C:/dev/local-model"))

    assert command[:2] == [args.python, "scripts/run_benchmark_execution_matrix.py"]
    assert "--providers" in command
    assert "serve,codex" in command
    assert "--artifact-dir" in command
    assert "C:/tmp/matrix" in command
    assert "C:/tmp/benchmark_execution_matrix.json" in command


def test_schematic_drift_command_targets_metadata_checker():
    args = parse([
        "schematic-drift",
        "--graph",
        "C:/tmp/graph.json",
        "--report",
        "C:/tmp/report.md",
        "--out",
        "C:/tmp/schematic_drift_check.json",
    ])
    command = build_command(args, repo_root=Path("C:/dev/local-model"))

    assert command[:2] == [args.python, "scripts/run_schematic_drift_check.py"]
    assert "--graph" in command
    assert "C:/tmp/graph.json" in command
    assert "--report" in command
    assert "C:/tmp/report.md" in command
    assert "C:/tmp/schematic_drift_check.json" in command


def test_agentic_tasks_command_targets_manifest_generator():
    args = parse([
        "agentic-tasks",
        "--task-set",
        "C:/tmp/tasks.json",
        "--adapter",
        "C:/tmp/adapter.json",
        "--artifact-dir",
        "C:/tmp/agentic-runs",
        "--provider-roles",
        "dry,codex_harness",
        "--out",
        "C:/tmp/agentic_task_manifest.json",
    ])
    command = build_command(args, repo_root=Path("C:/dev/local-model"))

    assert command[:2] == [args.python, "scripts/run_agentic_task_set_manifest.py"]
    assert "--task-set" in command
    assert "C:/tmp/tasks.json" in command
    assert "--adapter" in command
    assert "C:/tmp/adapter.json" in command
    assert "--provider-roles" in command
    assert "dry,codex_harness" in command
    assert "C:/tmp/agentic_task_manifest.json" in command


def test_cross_harness_command_targets_manifest_generator():
    args = parse([
        "cross-harness",
        "--task-set",
        "C:/tmp/tasks.json",
        "--contract",
        "C:/tmp/cross.json",
        "--artifact-dir",
        "C:/tmp/cross-runs",
        "--provider-roles",
        "codex_harness,flywheel_harness",
        "--out",
        "C:/tmp/cross_harness_manifest.json",
    ])
    command = build_command(args, repo_root=Path("C:/dev/local-model"))

    assert command[:2] == [args.python, "scripts/run_cross_harness_manifest.py"]
    assert "--task-set" in command
    assert "C:/tmp/tasks.json" in command
    assert "--contract" in command
    assert "C:/tmp/cross.json" in command
    assert "--provider-roles" in command
    assert "codex_harness,flywheel_harness" in command
    assert "C:/tmp/cross_harness_manifest.json" in command


def test_adapter_runtime_command_targets_matrix_generator():
    args = parse([
        "adapter-runtime",
        "--contract",
        "C:/tmp/cross.json",
        "--endpoint-profiles",
        "C:/tmp/model_endpoint_profiles.json",
        "--endpoint-auth-status",
        "C:/tmp/endpoint_auth_status.json",
        "--out",
        "C:/tmp/adapter_runtime_matrix.json",
    ])
    command = build_command(args, repo_root=Path("C:/dev/local-model"))

    assert command[:2] == [args.python, "scripts/run_adapter_runtime_matrix.py"]
    assert "--contract" in command
    assert "C:/tmp/cross.json" in command
    assert "--endpoint-profiles" in command
    assert "C:/tmp/model_endpoint_profiles.json" in command
    assert "--endpoint-auth-status" in command
    assert "C:/tmp/endpoint_auth_status.json" in command
    assert "C:/tmp/adapter_runtime_matrix.json" in command


def test_embodied_realtime_command_targets_metadata_plan_generator():
    args = parse([
        "embodied-realtime",
        "--contract",
        "C:/tmp/embodied.json",
        "--providers",
        "dry,codex",
        "--latency-budgets-ms",
        "250,500",
        "--artifact-dir",
        "C:/tmp/embodied-runs",
        "--out",
        "C:/tmp/embodied_plan.json",
    ])
    command = build_command(args, repo_root=Path("C:/dev/local-model"))

    assert command[:2] == [args.python, "scripts/run_embodied_realtime_multimodal_plan.py"]
    assert "--contract" in command
    assert "C:/tmp/embodied.json" in command
    assert "--providers" in command
    assert "dry,codex" in command
    assert "--latency-budgets-ms" in command
    assert "250,500" in command
    assert "--artifact-dir" in command
    assert "C:/tmp/embodied-runs" in command
    assert "C:/tmp/embodied_plan.json" in command


def test_model_card_claims_command_targets_claim_table_generator():
    args = parse([
        "model-card-claims",
        "--contract",
        "C:/tmp/embodied.json",
        "--evidence",
        "C:/tmp/evidence.json",
        "--artifact-dir",
        "C:/tmp/model-card-claims",
        "--out",
        "C:/tmp/model_card_claim_table.json",
    ])
    command = build_command(args, repo_root=Path("C:/dev/local-model"))

    assert command[:2] == [args.python, "scripts/run_model_card_claim_table.py"]
    assert "--contract" in command
    assert "C:/tmp/embodied.json" in command
    assert "--evidence" in command
    assert "C:/tmp/evidence.json" in command
    assert "--artifact-dir" in command
    assert "C:/tmp/model-card-claims" in command
    assert "C:/tmp/model_card_claim_table.json" in command


def test_classifier_friction_command_targets_classifier_runner():
    args = parse([
        "classifier-friction",
        "--providers",
        "dry,codex",
        "--allow-online",
        "--task-id",
        "workspace_receipt_audit",
        "--out",
        "C:/tmp/classifier.json",
    ])
    command = build_command(args, repo_root=Path("C:/dev/local-model"))

    assert command[:2] == [args.python, "scripts/run_classifier_friction_benchmark.py"]
    assert "--providers" in command
    assert "dry,codex" in command
    assert "--allow-online" in command
    assert "--task-id" in command
    assert "workspace_receipt_audit" in command
    assert "C:/tmp/classifier.json" in command


def test_seed_command_preserves_store_artifact_and_repair_flags():
    args = parse([
        "seed",
        "--store-root",
        "C:/tmp/store",
        "--artifact-dir",
        "C:/tmp/seed",
        "--out",
        "C:/tmp/seed.json",
        "--unisonai-repair-json",
    ])
    command = build_command(args, repo_root=Path("C:/dev/local-model"))

    assert command[:2] == [args.python, "scripts/run_closed_loop_benchmark_seed.py"]
    assert "--store-root" in command
    assert "C:/tmp/store" in command
    assert "--artifact-dir" in command
    assert "C:/tmp/seed" in command
    assert "--unisonai-repair-json" in command


def test_readiness_command_dispatches_model_release():
    args = parse([
        "readiness",
        "model-release",
        "--out",
        "C:/tmp/models.json",
        "--markdown-out",
        "C:/tmp/models.md",
    ])
    command = build_command(args, repo_root=Path("C:/dev/local-model"))

    assert command[:2] == [args.python, "scripts/run_model_release_readiness.py"]
    assert "--out" in command
    assert "C:/tmp/models.json" in command


def test_readiness_command_dispatches_model_endpoint_profiles():
    args = parse([
        "readiness",
        "model-endpoints",
        "--base-root",
        "E:/local-model-run",
        "--out",
        "C:/tmp/model_endpoints.json",
    ])
    command = build_command(args, repo_root=Path("C:/dev/local-model"))

    assert command[:2] == [args.python, "scripts/run_model_endpoint_profiles.py"]
    assert "--base-root" in command
    assert "E:/local-model-run" in command
    assert "C:/tmp/model_endpoints.json" in command


def test_format_command_quotes_spaces():
    text = format_command(["python", "script.py", "C:/path with spaces/out.json"])

    assert '"C:/path with spaces/out.json"' in text


def test_manifest_lists_front_controller_commands_and_evidence_surfaces():
    manifest = build_manifest(store_root="C:/tmp/store")

    assert manifest["schema"] == "harness.executable-manifest/v1"
    assert manifest["entrypoint"] == "harness.cmd"
    names = [row["name"] for row in manifest["commands"]]
    assert names == ["manifest", "registry", "benchmarks", "forum-route", "mcp-health", "benchmark-coverage", "comparison", "execution-matrix", "schematic-drift", "agentic-tasks", "cross-harness", "adapter-runtime", "embodied-realtime", "model-card-claims", "tool-hardening", "classifier-friction", "endpoint-gate", "model-publish", "plan", "seed", "outcome", "query", "readiness"]
    readiness = [row for row in manifest["commands"] if row["name"] == "readiness"][0]
    assert "model-endpoints" in readiness["targets"]
    assert "model-release" in readiness["targets"]
    assert "harness.model-endpoint-profiles/v1" in readiness["schemas"]
    assert "harness.model-release-readiness/v1" in readiness["schemas"]
    assert manifest["store_root_default"] == "C:/tmp/store"
    seed = [row for row in manifest["commands"] if row["name"] == "seed"][0]
    assert seed["long_running_risk"] == "high"
    assert "C:/tmp/harness_closed_loop_seed.json" in seed["default_artifacts"]
    assert "tests/test_closed_loop_benchmark_seed.py" in seed["recommended_validation_slice"]


def test_render_manifest_markdown_includes_command_table():
    markdown = render_manifest_markdown(build_manifest(store_root="C:/tmp/store"))

    assert "# Harness executable manifest" in markdown
    assert "| manifest |" in markdown
    assert "| seed |" in markdown
    assert "high" in markdown
    assert "harness.closed-loop-benchmark-seed/v1" in markdown


def test_registry_html_exposes_risk_runway_and_escapes_content():
    manifest = build_manifest(store_root="C:/tmp/store")
    manifest["commands"][0]["purpose"] = "<script>alert(1)</script>"

    html = render_registry_html(manifest)

    assert "<!doctype html>" in html
    assert "Risk runway" in html
    assert "harness command registry" in html
    assert "high risk" in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html


def test_manifest_includes_registry_command():
    manifest = build_manifest(store_root="C:/tmp/store")
    registry = [row for row in manifest["commands"] if row["name"] == "registry"][0]

    assert registry["schemas"] == ["harness.command-registry-html/v1"]
    assert registry["long_running_risk"] == "low"
    assert "C:/tmp/harness_command_registry.html" in registry["default_artifacts"]
    assert "C:/tmp/harness_command_registry.json" in registry["default_artifacts"]


def test_manifest_includes_agentic_tasks_command():
    manifest = build_manifest(store_root="C:/tmp/store")
    agentic = [row for row in manifest["commands"] if row["name"] == "agentic-tasks"][0]

    assert "harness.agentic-task-manifest/v1" in agentic["schemas"]
    assert agentic["long_running_risk"] == "low"
    assert "scripts/run_agentic_task_set_manifest.py" in agentic["delegates_to"]


def test_manifest_includes_schematic_drift_command():
    manifest = build_manifest(store_root="C:/tmp/store")
    drift = [row for row in manifest["commands"] if row["name"] == "schematic-drift"][0]

    assert "harness.schematic-drift-check/v1" in drift["schemas"]
    assert drift["long_running_risk"] == "low"
    assert "scripts/run_schematic_drift_check.py" in drift["delegates_to"]


def test_manifest_includes_forum_route_command():
    manifest = build_manifest(store_root="C:/tmp/store")
    route = [row for row in manifest["commands"] if row["name"] == "forum-route"][0]

    assert "harness.forum-route-receipts/v1" in route["schemas"]
    assert route["long_running_risk"] == "low"
    assert "scripts/run_forum_route_receipts.py" in route["delegates_to"]


def test_manifest_includes_mcp_health_command():
    manifest = build_manifest(store_root="C:/tmp/store")
    health = [row for row in manifest["commands"] if row["name"] == "mcp-health"][0]

    assert "harness.mcp-tool-health/v1" in health["schemas"]
    assert health["long_running_risk"] == "low"
    assert "scripts/run_mcp_tool_health_receipts.py" in health["delegates_to"]


def test_manifest_includes_cross_harness_command():
    manifest = build_manifest(store_root="C:/tmp/store")
    cross = [row for row in manifest["commands"] if row["name"] == "cross-harness"][0]

    assert "harness.cross-harness-manifest/v1" in cross["schemas"]
    assert "harness.cross-harness-task-scorecard/v1" in cross["schemas"]
    assert cross["long_running_risk"] == "low"
    assert "scripts/run_cross_harness_manifest.py" in cross["delegates_to"]


def test_manifest_includes_adapter_runtime_command():
    manifest = build_manifest(store_root="C:/tmp/store")
    runtime = [row for row in manifest["commands"] if row["name"] == "adapter-runtime"][0]

    assert "harness.adapter-runtime-matrix/v1" in runtime["schemas"]
    assert runtime["long_running_risk"] == "low"
    assert "scripts/run_adapter_runtime_matrix.py" in runtime["delegates_to"]


def test_manifest_includes_embodied_realtime_command():
    manifest = build_manifest(store_root="C:/tmp/store")
    embodied = [row for row in manifest["commands"] if row["name"] == "embodied-realtime"][0]

    assert "harness.embodied-realtime-multimodal/v1" in embodied["schemas"]
    assert embodied["long_running_risk"] == "low"
    assert "scripts/run_embodied_realtime_multimodal_plan.py" in embodied["delegates_to"]


def test_manifest_includes_model_card_claims_command():
    manifest = build_manifest(store_root="C:/tmp/store")
    claims = [row for row in manifest["commands"] if row["name"] == "model-card-claims"][0]

    assert "harness.model-card-claim-table/v1" in claims["schemas"]
    assert claims["long_running_risk"] == "low"
    assert "scripts/run_model_card_claim_table.py" in claims["delegates_to"]


def test_registry_parser_accepts_summary_output_path():
    args = parse([
        "registry",
        "--out",
        "C:/tmp/registry.html",
        "--summary-out",
        "C:/tmp/registry.json",
    ])

    assert args.out == "C:/tmp/registry.html"
    assert args.summary_out == "C:/tmp/registry.json"


def test_registry_summary_records_risk_counts_and_command_names():
    manifest = build_manifest(store_root="C:/tmp/store")

    summary = build_registry_summary(manifest, html_path="C:/tmp/registry.html")

    assert summary["schema"] == "harness.command-registry-html/v1"
    assert summary["html_path"] == "C:/tmp/registry.html"
    assert summary["command_count"] == len(manifest["commands"])
    assert "registry" in summary["command_names"]
    assert summary["risk_counts"]["high"] == 1
