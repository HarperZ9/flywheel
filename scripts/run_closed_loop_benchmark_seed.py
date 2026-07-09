"""Orchestrate the store-backed closed-loop benchmark seed run.

The command creates one run id, executes the current profile/preflight/index/
benchmark seed commands with the same file-backed store root, and writes a
final orchestration receipt. Use --dry-plan to inspect the commands without
running them.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.file_backed_store import FileBackedHarnessStore  # noqa: E402


DEFAULT_FORUM_ROUTE_TEXTS = [
    "Route the active Codex/Flywheel local-model closed-loop harness objective.",
    "Route same-task Codex versus Flywheel versus Claude Code versus OpenCode benchmark comparison work.",
    "Route local 14B and 32B endpoint-readiness and release-gate work.",
]


def utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


@dataclass(frozen=True)
class OrchestrationStep:
    step_id: str
    purpose: str
    command: list[str]
    timeout_seconds: float
    expected_artifacts: list[str]

    def to_json(self) -> dict:
        return {
            "step_id": self.step_id,
            "purpose": self.purpose,
            "command": self.command,
            "timeout_seconds": self.timeout_seconds,
            "expected_artifacts": self.expected_artifacts,
        }


def _path(base: Path, name: str) -> str:
    return str(base / name)


def build_steps(args, *, run_id: str, artifact_dir: Path) -> list[OrchestrationStep]:
    py = args.python
    store = args.store_root
    steps: list[OrchestrationStep] = []

    endpoint_json = _path(artifact_dir, "endpoint_auth_status.json")
    endpoint_md = _path(artifact_dir, "endpoint_auth_status.md")
    steps.append(OrchestrationStep(
        step_id="endpoint_auth_status",
        purpose="Record non-secret Claude/Codex account lane preflight posture.",
        command=[
            py,
            "scripts/run_endpoint_auth_status.py",
            "--out",
            endpoint_json,
            "--markdown-out",
            endpoint_md,
            "--store-root",
            store,
            "--run-id",
            run_id,
        ],
        timeout_seconds=args.preflight_timeout_seconds,
        expected_artifacts=[endpoint_json, endpoint_md],
    ))

    forum_route_json = _path(artifact_dir, "forum_route_receipts.json")
    forum_route_md = _path(artifact_dir, "forum_route_receipts.md")
    if not args.skip_forum_route_receipts:
        command = [
            py,
            "scripts/run_forum_route_receipts.py",
            "--out",
            forum_route_json,
            "--markdown-out",
            forum_route_md,
            "--store-root",
            store,
            "--run-id",
            run_id,
        ]
        for route_text in args.forum_route_text or DEFAULT_FORUM_ROUTE_TEXTS:
            command.extend(["--route", route_text])
        steps.append(OrchestrationStep(
            step_id="forum_route_receipts",
            purpose="Record Forum routing prompt hashes and optional route-frame observation metadata.",
            command=command,
            timeout_seconds=args.preflight_timeout_seconds,
            expected_artifacts=[forum_route_json, forum_route_md],
        ))

    mcp_health_json = _path(artifact_dir, "mcp_tool_health.json")
    mcp_health_md = _path(artifact_dir, "mcp_tool_health.md")
    if not args.skip_mcp_tool_health:
        command = [
            py,
            "scripts/run_mcp_tool_health_receipts.py",
            "--tools",
            args.mcp_tool_health_tools,
            "--out",
            mcp_health_json,
            "--markdown-out",
            mcp_health_md,
            "--store-root",
            store,
            "--run-id",
            run_id,
        ]
        for observation in args.mcp_tool_health_observation:
            command.extend(["--observation", observation])
        steps.append(OrchestrationStep(
            step_id="mcp_tool_health",
            purpose="Record configured MCP/tool roots and optional non-secret live tool observations.",
            command=command,
            timeout_seconds=args.preflight_timeout_seconds,
            expected_artifacts=[mcp_health_json, mcp_health_md],
        ))

    manifest_json = _path(artifact_dir, "harness_executable_manifest.json")
    manifest_md = _path(artifact_dir, "harness_executable_manifest.md")
    if not args.skip_harness_manifest:
        steps.append(OrchestrationStep(
            step_id="harness_executable_manifest",
            purpose="Record the harness executable subcommand/schema/evidence surface.",
            command=[
                py,
                "scripts/run_harness_cli.py",
                "manifest",
                "--out",
                manifest_json,
                "--markdown-out",
                manifest_md,
                "--store-root",
                store,
                "--run-id",
                run_id,
            ],
            timeout_seconds=args.preflight_timeout_seconds,
            expected_artifacts=[manifest_json, manifest_md],
        ))

    registry_json = _path(artifact_dir, "harness_command_registry.json")
    registry_html = _path(artifact_dir, "harness_command_registry.html")
    if not args.skip_harness_registry:
        steps.append(OrchestrationStep(
            step_id="harness_command_registry",
            purpose="Record the local static command registry and machine-readable command/risk summary.",
            command=[
                py,
                "scripts/run_harness_cli.py",
                "registry",
                "--out",
                registry_html,
                "--summary-out",
                registry_json,
                "--store-root",
                store,
                "--run-id",
                run_id,
            ],
            timeout_seconds=args.preflight_timeout_seconds,
            expected_artifacts=[registry_json, registry_html],
        ))

    execution_matrix_json = _path(artifact_dir, "benchmark_execution_matrix.json")
    execution_matrix_md = _path(artifact_dir, "benchmark_execution_matrix.md")
    if not args.skip_benchmark_execution_matrix:
        steps.append(OrchestrationStep(
            step_id="benchmark_execution_matrix",
            purpose="Record the non-executing dry/focused/full benchmark run matrix and evidence gates.",
            command=[
                py,
                "scripts/run_benchmark_execution_matrix.py",
                "--providers",
                args.benchmark_profile_providers,
                "--run-id",
                run_id,
                "--artifact-dir",
                str(artifact_dir),
                "--out",
                execution_matrix_json,
                "--markdown-out",
                execution_matrix_md,
                "--store-root",
                store,
            ],
            timeout_seconds=args.preflight_timeout_seconds,
            expected_artifacts=[execution_matrix_json, execution_matrix_md],
        ))

    benchmark_profile_json = _path(artifact_dir, "benchmark_profile_manifest.json")
    benchmark_profile_md = _path(artifact_dir, "benchmark_profile_manifest.md")
    if not args.skip_benchmark_profile:
        steps.append(OrchestrationStep(
            step_id="benchmark_profile",
            purpose="Record weighted benchmark definitions, provider matrix, and existing artifact inventory.",
            command=[
                py,
                "scripts/run_benchmark_profile_manifest.py",
                "--providers",
                args.benchmark_profile_providers,
                "--artifact-roots",
                args.benchmark_profile_artifact_roots,
                "--max-artifacts",
                str(args.benchmark_profile_max_artifacts),
                "--out",
                benchmark_profile_json,
                "--markdown-out",
                benchmark_profile_md,
                "--store-root",
                store,
                "--run-id",
                run_id,
            ],
            timeout_seconds=args.preflight_timeout_seconds,
            expected_artifacts=[benchmark_profile_json, benchmark_profile_md],
        ))

    schematic_json = _path(artifact_dir, "schematic_drift_check.json")
    schematic_md = _path(artifact_dir, "schematic_drift_check.md")
    if not args.skip_schematic_drift:
        steps.append(OrchestrationStep(
            step_id="schematic_drift_check",
            purpose="Check closed-loop graph/report drift without running validation, endpoints, providers, or benchmarks.",
            command=[
                py,
                "scripts/run_schematic_drift_check.py",
                "--graph",
                args.schematic_graph,
                "--report",
                args.schematic_report,
                "--out",
                schematic_json,
                "--markdown-out",
                schematic_md,
                "--store-root",
                store,
                "--run-id",
                run_id,
            ],
            timeout_seconds=args.preflight_timeout_seconds,
            expected_artifacts=[schematic_json, schematic_md],
        ))

    agentic_manifest_json = _path(artifact_dir, "agentic_task_manifest.json")
    agentic_manifest_md = _path(artifact_dir, "agentic_task_manifest.md")
    if not args.skip_agentic_task_manifest:
        steps.append(OrchestrationStep(
            step_id="agentic_task_manifest",
            purpose="Expand the custom agentic task set into prompt hashes, planned artifacts, and manifest-only scorecard rows.",
            command=[
                py,
                "scripts/run_agentic_task_set_manifest.py",
                "--task-set",
                args.agentic_task_set,
                "--adapter",
                args.agentic_task_adapter,
                "--artifact-dir",
                _path(artifact_dir, "agentic_task_runs"),
                "--provider-roles",
                args.agentic_task_provider_roles,
                "--out",
                agentic_manifest_json,
                "--markdown-out",
                agentic_manifest_md,
                "--store-root",
                store,
                "--run-id",
                run_id,
            ],
            timeout_seconds=args.preflight_timeout_seconds,
            expected_artifacts=[agentic_manifest_json, agentic_manifest_md],
        ))

    cross_harness_json = _path(artifact_dir, "cross_harness_manifest.json")
    cross_harness_md = _path(artifact_dir, "cross_harness_manifest.md")
    if not args.skip_cross_harness_manifest:
        steps.append(OrchestrationStep(
            step_id="cross_harness_manifest",
            purpose="Expand same-task cross-harness prompt hashes and planned provider-role receipt rows without executing providers.",
            command=[
                py,
                "scripts/run_cross_harness_manifest.py",
                "--task-set",
                args.agentic_task_set,
                "--contract",
                args.cross_harness_contract,
                "--provider-roles",
                args.cross_harness_provider_roles,
                "--artifact-dir",
                _path(artifact_dir, "cross_harness_runs"),
                "--out",
                cross_harness_json,
                "--markdown-out",
                cross_harness_md,
                "--store-root",
                store,
                "--run-id",
                run_id,
            ],
            timeout_seconds=args.preflight_timeout_seconds,
            expected_artifacts=[cross_harness_json, cross_harness_md],
        ))

    embodied_json = _path(artifact_dir, "embodied_realtime_multimodal_plan.json")
    embodied_md = _path(artifact_dir, "embodied_realtime_multimodal_plan.md")
    if not args.skip_embodied_realtime:
        steps.append(OrchestrationStep(
            step_id="embodied_realtime_multimodal_plan",
            purpose="Expand embodied realtime multimodal probes into planned rows, prompt hashes, and dry scorecard placeholders.",
            command=[
                py,
                "scripts/run_embodied_realtime_multimodal_plan.py",
                "--contract",
                args.embodied_realtime_contract,
                "--providers",
                args.embodied_realtime_providers,
                "--latency-budgets-ms",
                args.embodied_realtime_latency_budgets_ms,
                "--artifact-dir",
                _path(artifact_dir, "embodied_realtime_multimodal"),
                "--out",
                embodied_json,
                "--markdown-out",
                embodied_md,
                "--store-root",
                store,
                "--run-id",
                run_id,
            ],
            timeout_seconds=args.preflight_timeout_seconds,
            expected_artifacts=[embodied_json, embodied_md],
        ))

    model_card_claims_json = _path(artifact_dir, "model_card_claim_table.json")
    model_card_claims_md = _path(artifact_dir, "model_card_claim_table.md")
    if not args.skip_model_card_claims:
        command = [
            py,
            "scripts/run_model_card_claim_table.py",
            "--contract",
            args.model_card_claim_contract,
            "--artifact-dir",
            _path(artifact_dir, "model_card_claims"),
            "--out",
            model_card_claims_json,
            "--markdown-out",
            model_card_claims_md,
            "--store-root",
            store,
            "--run-id",
            run_id,
        ]
        if args.model_card_claim_evidence:
            command.extend(["--evidence", args.model_card_claim_evidence])
        steps.append(OrchestrationStep(
            step_id="model_card_claim_table",
            purpose="Record model-card claim status for embodied realtime model leads without network, endpoint, provider, or weight access.",
            command=command,
            timeout_seconds=args.preflight_timeout_seconds,
            expected_artifacts=[model_card_claims_json, model_card_claims_md],
        ))

    context_json = _path(artifact_dir, "context_inventory.json")
    context_md = _path(artifact_dir, "context_inventory.md")
    if not args.skip_context_inventory:
        steps.append(OrchestrationStep(
            step_id="context_inventory",
            purpose="Record metadata-only scratch/temp/session/artifact context shapes.",
            command=[
                py,
                "scripts/run_context_inventory.py",
                "--roots",
                args.context_roots,
                "--max-depth",
                str(args.context_max_depth),
                "--max-entries-per-root",
                str(args.context_max_entries_per_root),
                "--out",
                context_json,
                "--markdown-out",
                context_md,
                "--store-root",
                store,
                "--run-id",
                run_id,
            ],
            timeout_seconds=args.preflight_timeout_seconds,
            expected_artifacts=[context_json, context_md],
        ))

    tool_readiness_json = _path(artifact_dir, "tool_readiness.json")
    tool_readiness_md = _path(artifact_dir, "tool_readiness.md")
    if not args.skip_tool_readiness:
        steps.append(OrchestrationStep(
            step_id="tool_readiness",
            purpose="Record static enterprise-readiness posture for the flagship/pubscan tool set.",
            command=[
                py,
                "scripts/run_tool_readiness_receipts.py",
                "--tools",
                args.tool_readiness_tools,
                "--base-root",
                args.tool_readiness_base_root,
                "--out",
                tool_readiness_json,
                "--markdown-out",
                tool_readiness_md,
                "--store-root",
                store,
                "--run-id",
                run_id,
            ],
            timeout_seconds=args.preflight_timeout_seconds,
            expected_artifacts=[tool_readiness_json, tool_readiness_md],
        ))
        for tool_root in args.tool_readiness_tool_root:
            steps[-1].command.extend(["--tool-root", tool_root])

    tool_hardening_json = _path(artifact_dir, "tool_hardening_plan.json")
    tool_hardening_md = _path(artifact_dir, "tool_hardening_plan.md")
    if not args.skip_tool_hardening_plan:
        steps.append(OrchestrationStep(
            step_id="tool_hardening_plan",
            purpose="Convert flagship tool readiness gaps into prioritized enterprise hardening actions.",
            command=[
                py,
                "scripts/run_tool_hardening_plan.py",
                "--readiness-artifact",
                tool_readiness_json,
                "--out",
                tool_hardening_json,
                "--markdown-out",
                tool_hardening_md,
                "--store-root",
                store,
                "--run-id",
                run_id,
            ],
            timeout_seconds=args.preflight_timeout_seconds,
            expected_artifacts=[tool_hardening_json, tool_hardening_md],
        ))

    model_endpoint_json = _path(artifact_dir, "model_endpoint_profiles.json")
    model_endpoint_md = _path(artifact_dir, "model_endpoint_profiles.md")
    if not args.skip_model_endpoint_profiles:
        steps.append(OrchestrationStep(
            step_id="model_endpoint_profiles",
            purpose="Record metadata-only local model endpoint profiles for 14B/32B serve and Ollama paths.",
            command=[
                py,
                "scripts/run_model_endpoint_profiles.py",
                "--models",
                args.model_release_models,
                "--base-root",
                args.model_release_base_root,
                "--out",
                model_endpoint_json,
                "--markdown-out",
                model_endpoint_md,
                "--store-root",
                store,
                "--run-id",
                run_id,
            ],
            timeout_seconds=args.preflight_timeout_seconds,
            expected_artifacts=[model_endpoint_json, model_endpoint_md],
        ))

    adapter_runtime_json = _path(artifact_dir, "adapter_runtime_matrix.json")
    adapter_runtime_md = _path(artifact_dir, "adapter_runtime_matrix.md")
    if not args.skip_adapter_runtime_matrix:
        steps.append(OrchestrationStep(
            step_id="adapter_runtime_matrix",
            purpose="Join cross-harness adapter roles with endpoint profile and account-lane metadata without executing providers.",
            command=[
                py,
                "scripts/run_adapter_runtime_matrix.py",
                "--contract",
                args.cross_harness_contract,
                "--endpoint-profiles",
                model_endpoint_json,
                "--endpoint-auth-status",
                endpoint_json,
                "--out",
                adapter_runtime_json,
                "--markdown-out",
                adapter_runtime_md,
                "--store-root",
                store,
                "--run-id",
                run_id,
            ],
            timeout_seconds=args.preflight_timeout_seconds,
            expected_artifacts=[adapter_runtime_json, adapter_runtime_md],
        ))

    model_endpoint_gate_json = _path(artifact_dir, "model_endpoint_gate.json")
    model_endpoint_gate_md = _path(artifact_dir, "model_endpoint_gate.md")
    if not args.skip_model_endpoint_gate:
        steps.append(OrchestrationStep(
            step_id="model_endpoint_gate",
            purpose="Run bounded live health/generation gates against local 14B/32B endpoint profiles.",
            command=[
                py,
                "scripts/run_model_endpoint_gate.py",
                "--profile-artifact",
                model_endpoint_json,
                "--models",
                args.model_release_models,
                "--timeout-seconds",
                str(args.model_endpoint_gate_timeout_seconds),
                "--out",
                model_endpoint_gate_json,
                "--markdown-out",
                model_endpoint_gate_md,
                "--store-root",
                store,
                "--run-id",
                run_id,
            ],
            timeout_seconds=args.model_endpoint_gate_timeout_seconds * 6,
            expected_artifacts=[model_endpoint_gate_json, model_endpoint_gate_md],
        ))

    model_release_json = _path(artifact_dir, "model_release_readiness.json")
    model_release_md = _path(artifact_dir, "model_release_readiness.md")
    if not args.skip_model_release_readiness:
        command = [
                py,
                "scripts/run_model_release_readiness.py",
                "--models",
                args.model_release_models,
                "--base-root",
                args.model_release_base_root,
                "--artifact-roots",
                args.model_release_artifact_roots,
        ]
        if not args.skip_model_endpoint_profiles:
            command.extend(["--endpoint-profile-artifacts", model_endpoint_json])
        if not args.skip_model_endpoint_gate:
            command.extend(["--endpoint-gate-artifacts", model_endpoint_gate_json])
        command.extend([
                "--max-entries",
                str(args.model_release_max_entries),
                "--out",
                model_release_json,
                "--markdown-out",
                model_release_md,
                "--store-root",
                store,
                "--run-id",
                run_id,
        ])
        steps.append(OrchestrationStep(
            step_id="model_release_readiness",
            purpose="Record static release-readiness posture for the 14B and 32B local model tracks.",
            command=command,
            timeout_seconds=args.preflight_timeout_seconds,
            expected_artifacts=[model_release_json, model_release_md],
        ))

    model_publish_json = _path(artifact_dir, "model_publish_plan.json")
    model_publish_md = _path(artifact_dir, "model_publish_plan.md")
    if not args.skip_model_publish_plan:
        steps.append(OrchestrationStep(
            step_id="model_publish_plan",
            purpose="Generate 14B/32B candidate names, blockers, and operator-gated publication plan.",
            command=[
                py,
                "scripts/run_model_publish_plan.py",
                "--release-readiness-artifact",
                model_release_json,
                "--name-prefix",
                args.model_publish_name_prefix,
                "--out",
                model_publish_json,
                "--markdown-out",
                model_publish_md,
                "--store-root",
                store,
                "--run-id",
                run_id,
            ],
            timeout_seconds=args.preflight_timeout_seconds,
            expected_artifacts=[model_publish_json, model_publish_md],
        ))

    gather_json = _path(artifact_dir, "gather_readiness.json")
    gather_md = _path(artifact_dir, "gather_readiness.md")
    if not args.skip_gather_readiness:
        steps.append(OrchestrationStep(
            step_id="gather_readiness",
            purpose="Record metadata-only gather/source-intake readiness without live capture.",
            command=[
                py,
                "scripts/run_gather_readiness.py",
                "--gather-root",
                args.gather_readiness_root,
                "--config-roots",
                args.gather_readiness_config_roots,
                "--config-pattern",
                args.gather_readiness_config_pattern,
                "--credential-vars",
                args.gather_readiness_credential_vars,
                "--max-configs",
                str(args.gather_readiness_max_configs),
                "--out",
                gather_json,
                "--markdown-out",
                gather_md,
                "--store-root",
                store,
                "--run-id",
                run_id,
            ],
            timeout_seconds=args.preflight_timeout_seconds,
            expected_artifacts=[gather_json, gather_md],
        ))

    pubscan_json = _path(artifact_dir, "pubscan_resource_profiles.json")
    pubscan_md = _path(artifact_dir, "pubscan_resource_profiles.md")
    steps.append(OrchestrationStep(
        step_id="pubscan_resource_profiles",
        purpose="Profile pubscan tools, native rendering candidates, compute, and storage.",
        command=[
            py,
            "scripts/run_pubscan_resource_profiles.py",
            "--out",
            pubscan_json,
            "--markdown-out",
            pubscan_md,
            "--store-root",
            store,
            "--run-id",
            run_id,
        ],
        timeout_seconds=args.preflight_timeout_seconds,
        expected_artifacts=[pubscan_json, pubscan_md],
    ))

    index_json = _path(artifact_dir, "index_context_envelope.json")
    index_receipt = _path(artifact_dir, "index_context_envelope_receipt.json")
    index_context_root = args.index_context_root or args.workspace_root
    steps.append(OrchestrationStep(
        step_id="index_context_envelope",
        purpose="Capture bounded repository context through the Index CLI fallback receipt lane.",
        command=[
            py,
            "scripts/run_index_receipt.py",
            "--lane",
            "context-envelope",
            "--root",
            index_context_root,
            "--index-root",
            args.index_root,
            "--budget",
            str(args.index_budget),
            "--focus",
            args.index_focus,
            "--hops",
            str(args.index_hops),
            "--artifact-out",
            index_json,
            "--out",
            index_receipt,
            "--store-root",
            store,
            "--run-id",
            run_id,
        ],
        timeout_seconds=args.index_timeout_seconds,
        expected_artifacts=[index_json, index_receipt],
    ))

    if not args.skip_classifier_friction:
        classifier_json = _path(artifact_dir, "classifier_friction_benchmark.json")
        classifier_md = _path(artifact_dir, "classifier_friction_benchmark.md")
        command = [
            py,
            "scripts/run_classifier_friction_benchmark.py",
            "--providers",
            args.classifier_friction_providers,
            "--modes-to-test",
            args.classifier_friction_modes_to_test,
            "--endpoint-model",
            args.classifier_friction_endpoint_model,
            "--modes",
            args.classifier_friction_provider_modes,
            "--local-model",
            args.classifier_friction_local_model,
            "--max-tasks",
            str(args.classifier_friction_max_tasks),
            "--timeout-seconds",
            str(args.classifier_friction_timeout_seconds),
            "--max-tokens",
            str(args.classifier_friction_max_tokens),
            "--out",
            classifier_json,
            "--markdown-out",
            classifier_md,
            "--store-root",
            store,
            "--run-id",
            run_id,
        ]
        if args.classifier_friction_allow_online:
            command.append("--allow-online")
        steps.append(OrchestrationStep(
            step_id="classifier_friction",
            purpose="Measure local guardrail-wrapper friction against accountability-first receipt workflows.",
            command=command,
            timeout_seconds=args.benchmark_timeout_seconds,
            expected_artifacts=[classifier_json, classifier_md],
        ))

    if not args.skip_m7_source_mined:
        m7_source = _path(artifact_dir, "m7_source_mined_scorecard.json")
        steps.append(OrchestrationStep(
            step_id="m7_source_mined",
            purpose="Run shared source-mined cases across the configured provider set.",
            command=[
                py,
                "scripts/run_m7_eval.py",
                "--source-mined",
                "--source-mined-providers",
                args.source_mined_providers,
                "--source-mined-max-cases",
                str(args.source_mined_max_cases),
                "--out",
                m7_source,
                "--store-root",
                store,
                "--run-id",
                run_id,
            ],
            timeout_seconds=args.benchmark_timeout_seconds,
            expected_artifacts=[m7_source],
        ))

    if not args.skip_m7_governed:
        m7_governed = _path(artifact_dir, "m7_governed_agent_scorecard.json")
        steps.append(OrchestrationStep(
            step_id="m7_governed_agent",
            purpose="Run governed-agent workflow and schematic gates across providers.",
            command=[
                py,
                "scripts/run_m7_eval.py",
                "--governed-agent",
                "--governed-providers",
                args.governed_providers,
                "--governed-backend-max-scenarios",
                str(args.governed_backend_max_scenarios),
                "--out",
                m7_governed,
                "--store-root",
                store,
                "--run-id",
                run_id,
            ],
            timeout_seconds=args.benchmark_timeout_seconds,
            expected_artifacts=[m7_governed],
        ))

    if not args.skip_unisonai:
        unisonai_json = _path(artifact_dir, "unisonai_stateful_provider_matrix.json")
        unisonai_md = _path(artifact_dir, "unisonai_stateful_provider_matrix.md")
        command = [
            py,
            "scripts/run_unisonai_stateful_benchmark.py",
            "--providers",
            args.unisonai_providers,
            "--out",
            unisonai_json,
            "--markdown-out",
            unisonai_md,
            "--store-root",
            store,
            "--run-id",
            run_id,
        ]
        if args.unisonai_repair_json:
            command.append("--repair-json")
        steps.append(OrchestrationStep(
            step_id="unisonai_stateful_provider_matrix",
            purpose="Run executable stateful provider-action matrix.",
            command=command,
            timeout_seconds=args.benchmark_timeout_seconds,
            expected_artifacts=[unisonai_json, unisonai_md],
        ))

    if not args.skip_benchmark_coverage:
        coverage_json = _path(artifact_dir, "benchmark_profile_coverage.json")
        coverage_md = _path(artifact_dir, "benchmark_profile_coverage.md")
        coverage_artifacts = ";".join([
            _path(artifact_dir, "m7_source_mined_scorecard.json"),
            _path(artifact_dir, "m7_governed_agent_scorecard.json"),
            _path(artifact_dir, "unisonai_stateful_provider_matrix.json"),
            _path(artifact_dir, "classifier_friction_benchmark.json"),
            _path(artifact_dir, "model_endpoint_profiles.json"),
            _path(artifact_dir, "model_endpoint_gate.json"),
            _path(artifact_dir, "model_release_readiness.json"),
            _path(artifact_dir, "gather_readiness.json"),
            _path(artifact_dir, "adapter_runtime_matrix.json"),
            _path(artifact_dir, "agentic_task_manifest.json"),
            _path(artifact_dir, "cross_harness_manifest.json"),
            _path(artifact_dir, "embodied_realtime_multimodal_plan.json"),
            _path(artifact_dir, "model_card_claim_table.json"),
        ])
        steps.append(OrchestrationStep(
            step_id="benchmark_profile_coverage",
            purpose="Compare the weighted benchmark profile against observed scorecard artifacts and flag missing coverage.",
            command=[
                py,
                "scripts/run_benchmark_profile_coverage.py",
                "--profile",
                _path(artifact_dir, "benchmark_profile_manifest.json"),
                "--artifacts",
                coverage_artifacts,
                "--out",
                coverage_json,
                "--markdown-out",
                coverage_md,
                "--store-root",
                store,
                "--run-id",
                run_id,
            ],
            timeout_seconds=args.preflight_timeout_seconds,
            expected_artifacts=[coverage_json, coverage_md],
        ))

    if not args.skip_harness_comparison:
        comparison_json = _path(artifact_dir, "harness_comparison_report.json")
        comparison_md = _path(artifact_dir, "harness_comparison_report.md")
        comparison_artifacts = ";".join([
            _path(artifact_dir, "m7_source_mined_scorecard.json"),
            _path(artifact_dir, "m7_governed_agent_scorecard.json"),
            _path(artifact_dir, "unisonai_stateful_provider_matrix.json"),
            _path(artifact_dir, "classifier_friction_benchmark.json"),
            _path(artifact_dir, "model_endpoint_gate.json"),
        ])
        steps.append(OrchestrationStep(
            step_id="harness_comparison_report",
            purpose="Synthesize Codex-vs-Flywheel deltas from observed scorecard artifacts.",
            command=[
                py,
                "scripts/run_harness_comparison_report.py",
                "--artifacts",
                comparison_artifacts,
                "--out",
                comparison_json,
                "--markdown-out",
                comparison_md,
                "--store-root",
                store,
                "--run-id",
                run_id,
            ],
            timeout_seconds=args.preflight_timeout_seconds,
            expected_artifacts=[comparison_json, comparison_md],
        ))

    return steps


def run_step(step: OrchestrationStep, *, cwd: Path, log_dir: Path) -> dict:
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / f"{step.step_id}.stdout.txt"
    stderr_path = log_dir / f"{step.step_id}.stderr.txt"
    started = perf_counter()
    timed_out = False
    try:
        completed = subprocess.run(
            step.command,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=step.timeout_seconds,
            check=False,
        )
        returncode = completed.returncode
        stdout = completed.stdout.decode("utf-8", errors="replace")
        stderr = completed.stderr.decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = None
        stdout = (exc.stdout or b"").decode("utf-8", errors="replace")
        stderr = (exc.stderr or b"").decode("utf-8", errors="replace")
    elapsed_ms = int((perf_counter() - started) * 1000)
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    return {
        **step.to_json(),
        "status": "timeout" if timed_out else ("ok" if returncode == 0 else "failed"),
        "returncode": returncode,
        "elapsed_ms": elapsed_ms,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }


def summarize_results(results: list[dict]) -> dict:
    return {
        "steps": len(results),
        "ok_steps": sum(1 for row in results if row.get("status") == "ok"),
        "failed_steps": sum(1 for row in results if row.get("status") == "failed"),
        "timeout_steps": sum(1 for row in results if row.get("status") == "timeout"),
        "artifact_paths": [
            artifact
            for row in results
            for artifact in row.get("expected_artifacts", [])
        ],
    }


def build_report(
    *,
    run_id: str,
    artifact_dir: Path,
    store_root: str,
    steps: list[OrchestrationStep],
    results: list[dict],
    dry_plan: bool,
) -> dict:
    return {
        "schema": "harness.closed-loop-benchmark-seed/v1",
        "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "run_id": run_id,
        "store_root": store_root,
        "artifact_dir": str(artifact_dir),
        "dry_plan": dry_plan,
        "planned_steps": [step.to_json() for step in steps],
        "results": results,
        "summary": summarize_results(results) if results else {
            "steps": len(steps),
            "ok_steps": 0,
            "failed_steps": 0,
            "timeout_steps": 0,
            "artifact_paths": [artifact for step in steps for artifact in step.expected_artifacts],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store-root", default="C:/tmp/harness_file_store")
    parser.add_argument("--artifact-dir", default="")
    parser.add_argument("--workspace-root", default="C:/dev")
    parser.add_argument("--index-root", default="C:/dev/public/index")
    parser.add_argument("--index-context-root", default="C:/dev/local-model")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--out", default="")
    parser.add_argument("--run-title", default="closed-loop benchmark seed")
    parser.add_argument("--dry-plan", action="store_true")
    parser.add_argument("--strict-exit", action="store_true")
    parser.add_argument("--forum-route-text", action="append", default=[])
    parser.add_argument("--mcp-tool-health-tools", default="index,forum,telos,gather,crucible,aleph,mneme,relay,plexus,pubscan,local-model")
    parser.add_argument("--mcp-tool-health-observation", action="append", default=[])
    parser.add_argument("--preflight-timeout-seconds", type=float, default=120.0)
    parser.add_argument("--index-timeout-seconds", type=float, default=180.0)
    parser.add_argument("--benchmark-timeout-seconds", type=float, default=600.0)
    parser.add_argument(
        "--context-roots",
        default=(
            "C:/dev/local-model/.scratch;"
            "C:/dev/local-model/scratch;"
            "C:/dev/local-model/artifacts;"
            "C:/tmp;"
            "C:/Users/Zain/.codex;"
            "C:/Users/Zain/.claude;"
            "C:/Users/Zain/AppData/Roaming/opencode;"
            "C:/Users/Zain/AppData/Local/Programs/@opencode-aidesktop"
        ),
    )
    parser.add_argument("--context-max-depth", type=int, default=3)
    parser.add_argument("--context-max-entries-per-root", type=int, default=500)
    parser.add_argument("--tool-readiness-tools", default="index,forum,gather,crucible,telos,aleph,mneme,relay,plexus,pubscan")
    parser.add_argument("--tool-readiness-base-root", default="C:/dev/public")
    parser.add_argument("--tool-readiness-tool-root", action="append", default=["aleph=C:/dev/aleph"])
    parser.add_argument("--model-release-models", default="14B,32B")
    parser.add_argument("--model-release-base-root", default="E:/local-model-run")
    parser.add_argument("--model-release-artifact-roots", default="C:/dev/local-model/artifacts;C:/tmp")
    parser.add_argument("--model-release-max-entries", type=int, default=200)
    parser.add_argument("--model-publish-name-prefix", default="Flywheel-Local-Coder")
    parser.add_argument("--model-endpoint-gate-timeout-seconds", type=float, default=30.0)
    parser.add_argument("--gather-readiness-root", default="C:/dev/public/gather")
    parser.add_argument("--gather-readiness-config-roots", default="C:/dev/local-model/configs")
    parser.add_argument("--gather-readiness-config-pattern", default="gather-*.json")
    parser.add_argument("--gather-readiness-credential-vars", default="GATHER_DISCORD_BOT_TOKEN,DISCORD_TOKEN")
    parser.add_argument("--gather-readiness-max-configs", type=int, default=100)
    parser.add_argument("--benchmark-profile-providers", default="serve,codex,ollama,claude,opencode,dry")
    parser.add_argument("--benchmark-profile-artifact-roots", default="C:/tmp;C:/dev/local-model/artifacts")
    parser.add_argument("--benchmark-profile-max-artifacts", type=int, default=200)
    parser.add_argument("--schematic-graph", default="C:/dev/local-model/project-docs/schematics/closed-loop-integration.graph.json")
    parser.add_argument("--schematic-report", default="C:/dev/local-model/project-docs/records/CLOSED-LOOP-INTEGRATION-SCHEMATIC-2026-07-09.md")
    parser.add_argument("--agentic-task-set", default="C:/dev/local-model/benchmarks/agentic-task-set-v1.json")
    parser.add_argument("--agentic-task-adapter", default="C:/dev/local-model/benchmarks/agentic-task-set-adapter-v1.json")
    parser.add_argument("--agentic-task-provider-roles", default="dry")
    parser.add_argument("--cross-harness-contract", default="C:/dev/local-model/benchmarks/cross-harness-adapter-contract-v1.json")
    parser.add_argument("--cross-harness-provider-roles", default="codex_harness,flywheel_harness,claude_code,opencode,local_14b,local_32b,dry")
    parser.add_argument("--embodied-realtime-contract", default="C:/dev/local-model/benchmarks/embodied-realtime-multimodal-v1.json")
    parser.add_argument("--embodied-realtime-providers", default="dry")
    parser.add_argument("--embodied-realtime-latency-budgets-ms", default="250,500,1000")
    parser.add_argument("--model-card-claim-contract", default="C:/dev/local-model/benchmarks/embodied-realtime-multimodal-v1.json")
    parser.add_argument("--model-card-claim-evidence", default="")
    parser.add_argument("--index-budget", type=int, default=12000)
    parser.add_argument(
        "--index-focus",
        default="local-model",
    )
    parser.add_argument("--index-hops", type=int, default=2)
    parser.add_argument("--source-mined-providers", default="serve,codex")
    parser.add_argument("--source-mined-max-cases", type=int, default=2)
    parser.add_argument("--governed-providers", default="serve,codex")
    parser.add_argument("--governed-backend-max-scenarios", type=int, default=2)
    parser.add_argument("--unisonai-providers", default="dry,serve,ollama,codex,claude,opencode")
    parser.add_argument("--unisonai-repair-json", action="store_true")
    parser.add_argument("--classifier-friction-providers", default="dry,serve,codex")
    parser.add_argument("--classifier-friction-modes-to-test", default="guardrail_on,guardrail_off,accountability_first")
    parser.add_argument("--classifier-friction-provider-modes", default="plan")
    parser.add_argument("--classifier-friction-endpoint-model", default="gpt-5.3-codex-spark")
    parser.add_argument("--classifier-friction-local-model", default="qwen2.5:7b")
    parser.add_argument("--classifier-friction-max-tasks", type=int, default=1)
    parser.add_argument("--classifier-friction-timeout-seconds", type=int, default=120)
    parser.add_argument("--classifier-friction-max-tokens", type=int, default=500)
    parser.add_argument("--classifier-friction-allow-online", action="store_true")
    parser.add_argument("--skip-harness-manifest", action="store_true")
    parser.add_argument("--skip-harness-registry", action="store_true")
    parser.add_argument("--skip-forum-route-receipts", action="store_true")
    parser.add_argument("--skip-mcp-tool-health", action="store_true")
    parser.add_argument("--skip-benchmark-execution-matrix", action="store_true")
    parser.add_argument("--skip-benchmark-profile", action="store_true")
    parser.add_argument("--skip-schematic-drift", action="store_true")
    parser.add_argument("--skip-agentic-task-manifest", action="store_true")
    parser.add_argument("--skip-cross-harness-manifest", action="store_true")
    parser.add_argument("--skip-embodied-realtime", action="store_true")
    parser.add_argument("--skip-model-card-claims", action="store_true")
    parser.add_argument("--skip-context-inventory", action="store_true")
    parser.add_argument("--skip-tool-readiness", action="store_true")
    parser.add_argument("--skip-tool-hardening-plan", action="store_true")
    parser.add_argument("--skip-model-endpoint-profiles", action="store_true")
    parser.add_argument("--skip-adapter-runtime-matrix", action="store_true")
    parser.add_argument("--skip-model-endpoint-gate", action="store_true")
    parser.add_argument("--skip-model-release-readiness", action="store_true")
    parser.add_argument("--skip-model-publish-plan", action="store_true")
    parser.add_argument("--skip-gather-readiness", action="store_true")
    parser.add_argument("--skip-classifier-friction", action="store_true")
    parser.add_argument("--skip-m7-source-mined", action="store_true")
    parser.add_argument("--skip-m7-governed", action="store_true")
    parser.add_argument("--skip-unisonai", action="store_true")
    parser.add_argument("--skip-benchmark-coverage", action="store_true")
    parser.add_argument("--skip-harness-comparison", action="store_true")
    args = parser.parse_args(argv)

    label = utc_stamp()
    artifact_dir = Path(args.artifact_dir or f"C:/tmp/harness_closed_loop_seed_{label}")
    artifact_dir.mkdir(parents=True, exist_ok=True)

    if args.dry_plan:
        run_id = f"dry_plan_{label}"
    else:
        store = FileBackedHarnessStore(Path(args.store_root))
        run = store.create_run(
            kind="closed_loop_benchmark_seed",
            title=args.run_title,
            inputs={
                "artifact_dir": str(artifact_dir),
                "benchmark_execution_matrix": not args.skip_benchmark_execution_matrix,
                "schematic_drift": not args.skip_schematic_drift,
                "agentic_task_manifest": not args.skip_agentic_task_manifest,
                "cross_harness_manifest": not args.skip_cross_harness_manifest,
                "embodied_realtime": not args.skip_embodied_realtime,
                "model_card_claims": not args.skip_model_card_claims,
                "tool_readiness_tools": args.tool_readiness_tools,
                "index_context_root": args.index_context_root,
                "tool_hardening_plan": not args.skip_tool_hardening_plan,
                "model_release_models": args.model_release_models,
                "model_endpoint_profiles": not args.skip_model_endpoint_profiles,
                "adapter_runtime_matrix": not args.skip_adapter_runtime_matrix,
                "model_endpoint_gate": not args.skip_model_endpoint_gate,
                "model_publish_plan": not args.skip_model_publish_plan,
                "gather_readiness_root": args.gather_readiness_root,
                "benchmark_profile_providers": args.benchmark_profile_providers,
                "source_mined_providers": args.source_mined_providers,
                "governed_providers": args.governed_providers,
                "unisonai_providers": args.unisonai_providers,
                "classifier_friction_providers": args.classifier_friction_providers,
                "classifier_friction": not args.skip_classifier_friction,
                "harness_comparison": not args.skip_harness_comparison,
            },
        )
        run_id = run["run_id"]

    steps = build_steps(args, run_id=run_id, artifact_dir=artifact_dir)
    results: list[dict] = []
    if not args.dry_plan:
        store = FileBackedHarnessStore(Path(args.store_root))
        log_dir = artifact_dir / "logs"
        for step in steps:
            store.append_event(
                run_id=run_id,
                event_type="orchestration.step.started",
                payload={"step_id": step.step_id, "command": step.command},
            )
            result = run_step(step, cwd=Path(__file__).resolve().parent.parent, log_dir=log_dir)
            results.append(result)
            store.append_event(
                run_id=run_id,
                event_type="orchestration.step.finished",
                payload={
                    "step_id": step.step_id,
                    "status": result["status"],
                    "returncode": result["returncode"],
                    "elapsed_ms": result["elapsed_ms"],
                },
            )
            for log_path, label_name in (
                (result.get("stdout_path", ""), f"{step.step_id}-stdout"),
                (result.get("stderr_path", ""), f"{step.step_id}-stderr"),
            ):
                if log_path:
                    store.copy_artifact(Path(log_path), run_id=run_id, label=label_name)

    report = build_report(
        run_id=run_id,
        artifact_dir=artifact_dir,
        store_root=args.store_root,
        steps=steps,
        results=results,
        dry_plan=args.dry_plan,
    )

    if not args.dry_plan:
        summary = report["summary"]
        verdict = (
            "ORCHESTRATION_RECORDED"
            if summary["failed_steps"] == 0 and summary["timeout_steps"] == 0
            else "ORCHESTRATION_PARTIAL"
        )
        store = FileBackedHarnessStore(Path(args.store_root))
        report["store_outputs"] = [
            store.put_receipt(
                kind="closed_loop_benchmark_seed",
                body=report,
                run_id=run_id,
                verdict=verdict,
            )
        ]

    out_path = Path(args.out) if args.out else artifact_dir / "closed_loop_benchmark_seed.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    if not args.dry_plan:
        store = FileBackedHarnessStore(Path(args.store_root))
        report.setdefault("store_outputs", []).append(
            store.copy_artifact(out_path, run_id=run_id, label="closed-loop-seed-report-json")
        )

    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)

    if args.strict_exit and not args.dry_plan:
        summary = report["summary"]
        if summary["failed_steps"] or summary["timeout_steps"]:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
