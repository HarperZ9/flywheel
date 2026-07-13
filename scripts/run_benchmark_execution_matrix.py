"""Emit the benchmark execution matrix for the Codex/Flywheel harness.

This command does not run benchmarks. It records the intended run tiers,
provider matrix, commands, artifacts, schemas, and evidence gates needed to
turn the static benchmark contract into a reproducible experimental run.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.file_backed_store import FileBackedHarnessStore  # noqa: E402
from harness.provider_roles import PROVIDER_ROLES, provider_alias_map, provider_roles_for  # noqa: E402


SCHEMA = "harness.benchmark-execution-matrix/v1"
DEFAULT_PROVIDERS = "serve,codex,ollama,claude,opencode,dry"
DEFAULT_RUN_ID = "benchmark_matrix_20260709"
DEFAULT_ARTIFACT_DIR = "C:/tmp/harness_benchmark_matrix_20260709"


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def write_text(path_text: str, text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def command_step(
    *,
    step_id: str,
    tier: str,
    purpose: str,
    command: list[str],
    expected_artifacts: list[str],
    expected_schemas: list[str],
    evidence_gates: list[str],
    providers: list[str] | None = None,
    long_running: bool = False,
) -> dict[str, Any]:
    return {
        "schema": "harness.benchmark-execution-matrix.step/v1",
        "step_id": step_id,
        "tier": tier,
        "purpose": purpose,
        "command": command,
        "command_text": " ".join(command),
        "expected_artifacts": expected_artifacts,
        "expected_schemas": expected_schemas,
        "evidence_gates": evidence_gates,
        "providers": providers or [],
        "long_running": long_running,
        "executes_providers": long_running,
        "operator_approval_required": long_running,
    }


def artifact(artifact_dir: str, name: str) -> str:
    return str(Path(artifact_dir) / name)


def build_steps(*, providers: list[str], run_id: str, artifact_dir: str, store_root: str) -> list[dict[str, Any]]:
    provider_csv = ",".join(providers)
    profile_json = artifact(artifact_dir, "benchmark_profile_manifest.json")
    profile_md = artifact(artifact_dir, "benchmark_profile_manifest.md")
    coverage_json = artifact(artifact_dir, "benchmark_profile_coverage.json")
    coverage_md = artifact(artifact_dir, "benchmark_profile_coverage.md")
    comparison_json = artifact(artifact_dir, "harness_comparison_report.json")
    comparison_md = artifact(artifact_dir, "harness_comparison_report.md")
    outcome_json = artifact(artifact_dir, "harness_closed_loop_outcome.json")
    outcome_md = artifact(artifact_dir, "harness_closed_loop_outcome.md")
    seed_json = artifact(artifact_dir, "harness_closed_loop_seed.json")
    dry_plan_json = artifact(artifact_dir, "harness_closed_loop_dry_plan.json")
    endpoint_profiles_json = artifact(artifact_dir, "model_endpoint_profiles.json")
    endpoint_profiles_md = artifact(artifact_dir, "model_endpoint_profiles.md")
    adapter_runtime_json = artifact(artifact_dir, "adapter_runtime_matrix.json")
    adapter_runtime_md = artifact(artifact_dir, "adapter_runtime_matrix.md")
    schematic_json = artifact(artifact_dir, "schematic_drift_check.json")
    schematic_md = artifact(artifact_dir, "schematic_drift_check.md")
    endpoint_gate_json = artifact(artifact_dir, "model_endpoint_gate.json")
    endpoint_gate_md = artifact(artifact_dir, "model_endpoint_gate.md")
    classifier_json = artifact(artifact_dir, "classifier_friction_benchmark.json")
    classifier_md = artifact(artifact_dir, "classifier_friction_benchmark.md")
    index_receipt_json = artifact(artifact_dir, "index_context_envelope_fallback_receipt.json")
    index_context_json = artifact(artifact_dir, "index_context_envelope_fallback.json")
    m7_source_json = artifact(artifact_dir, "m7_source_mined_scorecard.json")
    m7_governed_json = artifact(artifact_dir, "m7_governed_scorecard.json")
    unisonai_json = artifact(artifact_dir, "unisonai_stateful_provider_matrix.json")
    cross_harness_json = artifact(artifact_dir, "cross_harness_manifest.json")
    cross_harness_md = artifact(artifact_dir, "cross_harness_manifest.md")
    embodied_json = artifact(artifact_dir, "embodied_realtime_multimodal_plan.json")
    embodied_md = artifact(artifact_dir, "embodied_realtime_multimodal_plan.md")
    model_card_claims_json = artifact(artifact_dir, "model_card_claim_table.json")
    model_card_claims_md = artifact(artifact_dir, "model_card_claim_table.md")
    artifact_list = ";".join([
        m7_source_json,
        m7_governed_json,
        unisonai_json,
        classifier_json,
        endpoint_gate_json,
        adapter_runtime_json,
        cross_harness_json,
        embodied_json,
        model_card_claims_json,
    ])
    store_args = ["--store-root", store_root, "--run-id", run_id] if store_root else ["--run-id", run_id]
    seed_store_args = ["--store-root", store_root] if store_root else []
    return [
        command_step(
            step_id="profile_contract",
            tier="dry",
            purpose="Emit the weighted benchmark contract before any provider execution.",
            command=[
                "python",
                "scripts/run_benchmark_profile_manifest.py",
                "--providers",
                provider_csv,
                "--artifact-roots",
                f"C:/tmp;{artifact_dir}",
                "--out",
                profile_json,
                "--markdown-out",
                profile_md,
                *store_args,
            ],
            expected_artifacts=[profile_json, profile_md],
            expected_schemas=["harness.benchmark-profile-manifest/v1"],
            evidence_gates=["metric_weight_sum", "dataset_lane_weight_sum", "benchmark_ids", "pressure_variables"],
        ),
        command_step(
            step_id="index_context_fallback",
            tier="dry",
            purpose="Capture workspace context through the Index CLI fallback when MCP transport is degraded.",
            command=[
                "python",
                "scripts/run_index_receipt.py",
                "--lane",
                "context-envelope",
                "--root",
                "C:/dev",
                "--index-root",
                "C:/dev/public/index",
                "--budget",
                "12000",
                "--focus",
                "local-model harness benchmark matrix providers endpoints",
                "--hops",
                "2",
                "--artifact-out",
                index_context_json,
                "--out",
                index_receipt_json,
                *store_args,
            ],
            expected_artifacts=[index_context_json, index_receipt_json],
            expected_schemas=["harness.index-cli-command/v1", "harness.index-cli-receipt/v1"],
            evidence_gates=["MATCH_or_DEGRADED_MATCH", "live_failure_code_recorded", "effective_output_source"],
        ),
        command_step(
            step_id="local_model_endpoint_profiles",
            tier="dry",
            purpose="Record local 14B/32B endpoint profile metadata before live endpoint gates.",
            command=[
                "python",
                "scripts/run_model_endpoint_profiles.py",
                "--models",
                "14B,32B",
                "--base-root",
                "E:/local-model-run",
                "--out",
                endpoint_profiles_json,
                "--markdown-out",
                endpoint_profiles_md,
                *store_args,
            ],
            expected_artifacts=[endpoint_profiles_json, endpoint_profiles_md],
            expected_schemas=["harness.model-endpoint-profiles/v1"],
            evidence_gates=["model_roots", "provider_roles", "health_paths", "generate_paths"],
        ),
        command_step(
            step_id="adapter_runtime_matrix",
            tier="dry",
            purpose="Join cross-harness adapter roles with endpoint profile metadata before live provider execution.",
            command=[
                "python",
                "scripts/run_adapter_runtime_matrix.py",
                "--contract",
                "C:/dev/local-model/benchmarks/cross-harness-adapter-contract-v1.json",
                "--endpoint-profiles",
                endpoint_profiles_json,
                "--out",
                adapter_runtime_json,
                "--markdown-out",
                adapter_runtime_md,
                *store_args,
            ],
            expected_artifacts=[adapter_runtime_json, adapter_runtime_md],
            expected_schemas=["harness.adapter-runtime-matrix/v1"],
            evidence_gates=["runtime_rows", "manifest_ready_roles", "blocking_gates", "no_provider_execution"],
        ),
        command_step(
            step_id="schematic_drift_check",
            tier="dry",
            purpose="Check the closed-loop schematic graph/report for stale nodes, edges, files, and prose.",
            command=[
                "python",
                "scripts/run_schematic_drift_check.py",
                "--graph",
                "C:/dev/local-model/project-docs/schematics/closed-loop-integration.graph.json",
                "--report",
                "C:/dev/local-model/project-docs/records/CLOSED-LOOP-INTEGRATION-SCHEMATIC-2026-07-09.md",
                "--out",
                schematic_json,
                "--markdown-out",
                schematic_md,
                *store_args,
            ],
            expected_artifacts=[schematic_json, schematic_md],
            expected_schemas=["harness.schematic-drift-check/v1"],
            evidence_gates=["required_nodes_present", "required_edges_present", "stale_prose_absent", "referenced_files_present"],
        ),
        command_step(
            step_id="cross_harness_manifest",
            tier="dry",
            purpose="Emit same-task cross-harness planned rows before provider execution.",
            command=[
                "python",
                "scripts/run_cross_harness_manifest.py",
                "--task-set",
                "C:/dev/local-model/benchmarks/agentic-task-set-v1.json",
                "--contract",
                "C:/dev/local-model/benchmarks/cross-harness-adapter-contract-v1.json",
                "--provider-roles",
                "codex_harness,flywheel_harness,claude_code,opencode,local_14b,local_32b,dry",
                "--artifact-dir",
                artifact(artifact_dir, "cross_harness_runs"),
                "--out",
                cross_harness_json,
                "--markdown-out",
                cross_harness_md,
                *store_args,
            ],
            expected_artifacts=[cross_harness_json, cross_harness_md],
            expected_schemas=["harness.cross-harness-manifest/v1", "harness.cross-harness-task-scorecard/v1"],
            evidence_gates=["same_task_prompt_hashes", "provider_role_plan_rows", "no_provider_execution", "comparison_receipt_requirements"],
        ),
        command_step(
            step_id="embodied_realtime_plan",
            tier="dry",
            purpose="Emit planned embodied realtime multimodal probe rows without provider, endpoint, renderer, or model-card execution.",
            command=[
                "python",
                "scripts/run_embodied_realtime_multimodal_plan.py",
                "--contract",
                "C:/dev/local-model/benchmarks/embodied-realtime-multimodal-v1.json",
                "--providers",
                "dry",
                "--latency-budgets-ms",
                "250,500,1000",
                "--artifact-dir",
                artifact(artifact_dir, "embodied_realtime_multimodal"),
                "--out",
                embodied_json,
                "--markdown-out",
                embodied_md,
                *store_args,
            ],
            expected_artifacts=[embodied_json, embodied_md],
            expected_schemas=["harness.embodied-realtime-multimodal/v1"],
            evidence_gates=["planned_probe_rows", "dry_scorecard_rows_not_executed", "model_leads_unverified"],
        ),
        command_step(
            step_id="model_card_claim_table",
            tier="dry",
            purpose="Emit model-card claim status for embodied realtime model leads before benchmark result claims.",
            command=[
                "python",
                "scripts/run_model_card_claim_table.py",
                "--contract",
                "C:/dev/local-model/benchmarks/embodied-realtime-multimodal-v1.json",
                "--artifact-dir",
                artifact(artifact_dir, "model_card_claims"),
                "--out",
                model_card_claims_json,
                "--markdown-out",
                model_card_claims_md,
                *store_args,
            ],
            expected_artifacts=[model_card_claims_json, model_card_claims_md],
            expected_schemas=["harness.model-card-claim-table/v1"],
            evidence_gates=["model_candidates", "required_claim_fields", "unresolved_fields", "no_network_fetch"],
        ),
        command_step(
            step_id="closed_loop_dry_plan",
            tier="dry",
            purpose="Emit the closed-loop seed plan without executing model or endpoint benchmarks.",
            command=[
                "python",
                "scripts/run_closed_loop_benchmark_seed.py",
                "--dry-plan",
                "--artifact-dir",
                artifact_dir,
                "--out",
                dry_plan_json,
                "--unisonai-repair-json",
                *seed_store_args,
            ],
            expected_artifacts=[dry_plan_json],
            expected_schemas=["harness.closed-loop-benchmark-seed/v1"],
            evidence_gates=["planned_steps_present", "shared_run_id", "no_provider_execution"],
        ),
        command_step(
            step_id="focused_closed_loop_seed",
            tier="focused",
            purpose="Run the bounded seed benchmark battery with shared receipts.",
            command=[
                "python",
                "scripts/run_closed_loop_benchmark_seed.py",
                "--artifact-dir",
                artifact_dir,
                "--out",
                seed_json,
                "--source-mined-providers",
                provider_csv,
                "--governed-providers",
                provider_csv,
                "--unisonai-providers",
                provider_csv,
                "--source-mined-max-cases",
                "2",
                "--governed-backend-max-scenarios",
                "2",
                "--unisonai-repair-json",
                *seed_store_args,
            ],
            expected_artifacts=[seed_json],
            expected_schemas=["harness.closed-loop-benchmark-seed/v1"],
            evidence_gates=["m7_source_mined", "m7_governed_agent", "unisonai_stateful_provider_matrix", "shared_run_id"],
            providers=providers,
            long_running=True,
        ),
        command_step(
            step_id="classifier_friction_matrix",
            tier="focused",
            purpose="Run guardrail-on/off/accountability-first prompt-layer comparison.",
            command=[
                "python",
                "scripts/run_classifier_friction_benchmark.py",
                "--providers",
                provider_csv,
                "--modes-to-test",
                "guardrail_on,guardrail_off,accountability_first",
                "--endpoint-model",
                "gpt-5.3-codex-spark",
                "--out",
                classifier_json,
                "--markdown-out",
                classifier_md,
                *store_args,
            ],
            expected_artifacts=[classifier_json, classifier_md],
            expected_schemas=["classifier-friction-benchmark/v1"],
            evidence_gates=["provider_x_mode_x_task_rows", "receipt_hash", "failure_class"],
            providers=providers,
            long_running=True,
        ),
        command_step(
            step_id="local_model_endpoint_gate",
            tier="focused",
            purpose="Probe local 14B/32B endpoint health and one bounded generation when endpoints exist.",
            command=[
                "python",
                "scripts/run_model_endpoint_gate.py",
                "--profile-artifact",
                endpoint_profiles_json,
                "--models",
                "14B,32B",
                "--out",
                endpoint_gate_json,
                "--markdown-out",
                endpoint_gate_md,
                *store_args,
            ],
            expected_artifacts=[endpoint_gate_json, endpoint_gate_md],
            expected_schemas=["harness.model-endpoint-gate/v1"],
            evidence_gates=["health_ok", "generation_ok", "quality_score", "receipt_hash"],
            providers=["serve", "ollama"],
            long_running=True,
        ),
        command_step(
            step_id="coverage_after_execution",
            tier="focused",
            purpose="Compare executed artifacts against the strict benchmark contract.",
            command=[
                "python",
                "scripts/run_benchmark_profile_coverage.py",
                "--profile",
                profile_json,
                "--artifacts",
                artifact_list,
                "--out",
                coverage_json,
                "--markdown-out",
                coverage_md,
                *store_args,
            ],
            expected_artifacts=[coverage_json, coverage_md],
            expected_schemas=["harness.benchmark-profile-coverage/v1"],
            evidence_gates=["benchmark_coverage_rate", "provider_unit_coverage_rate", "dataset_lane_coverage_rate", "pressure_variable_coverage_rate"],
        ),
        command_step(
            step_id="harness_comparison",
            tier="focused",
            purpose="Synthesize Codex-vs-Flywheel and cross-provider deltas from observed scorecards.",
            command=[
                "python",
                "scripts/run_harness_comparison_report.py",
                "--artifacts",
                artifact_list,
                "--out",
                comparison_json,
                "--markdown-out",
                comparison_md,
                *store_args,
            ],
            expected_artifacts=[comparison_json, comparison_md],
            expected_schemas=["harness.comparison-report/v1"],
            evidence_gates=["available_comparisons", "missing_counterparts", "quality_delta", "latency_delta"],
        ),
        command_step(
            step_id="outcome_synthesis",
            tier="focused",
            purpose="Produce the experimental outcome after the executed benchmark bundle exists.",
            command=[
                "python",
                "scripts/run_closed_loop_outcome_report.py",
                "--input",
                seed_json,
                "--out",
                outcome_json,
                "--markdown-out",
                outcome_md,
                *store_args,
            ],
            expected_artifacts=[outcome_json, outcome_md],
            expected_schemas=["harness.closed-loop-outcome/v1"],
            evidence_gates=["observations", "inferences", "unknowns", "next_checks"],
        ),
        command_step(
            step_id="full_provider_matrix",
            tier="full",
            purpose="Run the non-smoke full provider matrix after focused coverage gaps are understood.",
            command=[
                "python",
                "scripts/run_closed_loop_benchmark_seed.py",
                "--artifact-dir",
                artifact_dir,
                "--out",
                seed_json,
                "--source-mined-providers",
                provider_csv,
                "--governed-providers",
                provider_csv,
                "--unisonai-providers",
                provider_csv,
                "--source-mined-max-cases",
                "0",
                "--governed-backend-max-scenarios",
                "0",
                "--unisonai-repair-json",
                *seed_store_args,
            ],
            expected_artifacts=[seed_json],
            expected_schemas=["harness.closed-loop-benchmark-seed/v1"],
            evidence_gates=["all_declared_runnable_benchmarks", "full_provider_roles", "coverage_complete_or_typed_gaps"],
            providers=providers,
            long_running=True,
        ),
    ]


def build_matrix(
    *,
    providers: str = DEFAULT_PROVIDERS,
    run_id: str = DEFAULT_RUN_ID,
    artifact_dir: str = DEFAULT_ARTIFACT_DIR,
    store_root: str = "",
) -> dict[str, Any]:
    provider_list = split_csv(providers)
    steps = build_steps(providers=provider_list, run_id=run_id, artifact_dir=artifact_dir, store_root=store_root)
    tier_order = ["dry", "focused", "full"]
    return {
        "schema": SCHEMA,
        "created_utc": utc_now(),
        "matrix_id": "codex_flywheel_local_model_execution_matrix",
        "run_id": run_id,
        "artifact_dir": artifact_dir,
        "store_root": store_root,
        "providers": provider_list,
        "provider_roles": PROVIDER_ROLES,
        "expected_provider_roles": provider_roles_for(provider_list),
        "provider_aliases": provider_alias_map(),
        "tiers": [
            {
                "tier": tier,
                "step_count": sum(1 for step in steps if step["tier"] == tier),
                "long_running_steps": sum(1 for step in steps if step["tier"] == tier and step["long_running"]),
                "step_ids": [step["step_id"] for step in steps if step["tier"] == tier],
            }
            for tier in tier_order
        ],
        "steps": steps,
        "summary": {
            "steps": len(steps),
            "dry_steps": sum(1 for step in steps if step["tier"] == "dry"),
            "focused_steps": sum(1 for step in steps if step["tier"] == "focused"),
            "full_steps": sum(1 for step in steps if step["tier"] == "full"),
            "long_running_steps": sum(1 for step in steps if step["long_running"]),
            "operator_approval_required_steps": sum(1 for step in steps if step["operator_approval_required"]),
            "expected_artifacts": sum(len(step["expected_artifacts"]) for step in steps),
            "expected_schemas": sorted({schema for step in steps for schema in step["expected_schemas"]}),
            "evidence_gates": sorted({gate for step in steps for gate in step["evidence_gates"]}),
        },
        "execution_policy": {
            "does_not_execute": True,
            "run_order": tier_order,
            "focused_before_full": True,
            "full_run_requires_operator_approval": True,
            "secrets_policy": "Commands name environment/config surfaces only; they do not inline secrets.",
        },
    }


def render_markdown(matrix: dict[str, Any]) -> str:
    lines = [
        "# Benchmark execution matrix",
        "",
        f"- Schema: `{matrix['schema']}`",
        f"- Matrix id: `{matrix['matrix_id']}`",
        f"- Run id: `{matrix['run_id']}`",
        f"- Artifact dir: `{matrix['artifact_dir']}`",
        f"- Providers: `{', '.join(matrix['providers'])}`",
        f"- Expected provider roles: `{', '.join(matrix['expected_provider_roles'])}`",
        f"- Steps: `{matrix['summary']['steps']}`",
        f"- Long-running steps: `{matrix['summary']['long_running_steps']}`",
        "",
        "## Tiers",
        "",
        "| Tier | Steps | Long-running | Step ids |",
        "|---|---:|---:|---|",
    ]
    for tier in matrix["tiers"]:
        lines.append(
            f"| {tier['tier']} | {tier['step_count']} | {tier['long_running_steps']} | {', '.join(tier['step_ids'])} |"
        )
    lines.extend([
        "",
        "## Steps",
        "",
        "| Step | Tier | Providers | Expected schemas | Approval |",
        "|---|---|---|---|---|",
    ])
    for step in matrix["steps"]:
        lines.append(
            "| {step} | {tier} | {providers} | {schemas} | {approval} |".format(
                step=step["step_id"],
                tier=step["tier"],
                providers=", ".join(step["providers"]),
                schemas=", ".join(step["expected_schemas"]),
                approval=str(step["operator_approval_required"]).lower(),
            )
        )
    return "\n".join(lines) + "\n"


def store_matrix(
    matrix: dict[str, Any],
    *,
    store_root: str,
    run_id: str,
    artifacts: list[tuple[str, str]],
) -> list[dict[str, Any]]:
    if not store_root:
        return []
    store = FileBackedHarnessStore(Path(store_root))
    outputs = [
        store.put_receipt(
            kind="benchmark_execution_matrix",
            body=matrix,
            run_id=run_id,
            verdict="BENCHMARK_EXECUTION_MATRIX_RECORDED",
        )
    ]
    for path_text, label in artifacts:
        if path_text and Path(path_text).exists():
            outputs.append(store.copy_artifact(Path(path_text), run_id=run_id, label=label))
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--providers", default=DEFAULT_PROVIDERS)
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--artifact-dir", default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--store-root", default="")
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    args = parser.parse_args(argv)

    matrix = build_matrix(
        providers=args.providers,
        run_id=args.run_id,
        artifact_dir=args.artifact_dir,
        store_root=args.store_root,
    )
    json_text = json.dumps(matrix, indent=2, sort_keys=True)
    md_text = render_markdown(matrix)
    json_path = write_text(args.out, json_text)
    md_path = write_text(args.markdown_out, md_text)
    store_outputs = store_matrix(
        matrix,
        store_root=args.store_root,
        run_id=args.run_id,
        artifacts=[
            (json_path, "benchmark-execution-matrix-json"),
            (md_path, "benchmark-execution-matrix-markdown"),
        ],
    )
    if store_outputs:
        matrix = {**matrix, "store_outputs": store_outputs}
        json_text = json.dumps(matrix, indent=2, sort_keys=True)
    print(json_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
