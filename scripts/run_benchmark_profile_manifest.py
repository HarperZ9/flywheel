"""Emit a weighted benchmark profile manifest for the Codex/Flywheel loop."""

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


DEFAULT_PROVIDERS = "serve,codex,ollama,claude,opencode,dry"
DEFAULT_ARTIFACT_ROOTS = "C:/tmp;C:/dev/local-model/artifacts"


METRIC_WEIGHTS = [
    {
        "metric": "task_completion",
        "weight": 0.14,
        "measurement": "case pass rate, stateful action completion, and deterministic gate pass/fail",
    },
    {
        "metric": "quality",
        "weight": 0.12,
        "measurement": "weighted quality score, adversarial pressure score, and groundedness dimensions",
    },
    {
        "metric": "groundedness",
        "weight": 0.10,
        "measurement": "evidence citation coverage, source-to-claim traceability, and unsupported-claim penalties",
    },
    {
        "metric": "tool_use_success",
        "weight": 0.12,
        "measurement": "valid tool/action JSON, receipt-preserving repair, and tool-result integration",
    },
    {
        "metric": "workflow_state_management",
        "weight": 0.09,
        "measurement": "multi-turn state retention, dependency ordering, plan updates, and handoff continuity",
    },
    {
        "metric": "reliability",
        "weight": 0.10,
        "measurement": "non-timeout completion, retry posture, skipped-provider accounting, and stable schemas",
    },
    {
        "metric": "failure_mode_clarity",
        "weight": 0.08,
        "measurement": "typed failure classes instead of silent success or ambiguous prose",
    },
    {
        "metric": "latency",
        "weight": 0.07,
        "measurement": "mean latency, p95 latency, timeout pressure, and queue/setup overhead under comparable task sets",
    },
    {
        "metric": "cost_resource_use",
        "weight": 0.06,
        "measurement": "local/remote resource declaration, bounded case counts, memory, storage, and token/compute profile linkage",
    },
    {
        "metric": "reproducibility",
        "weight": 0.07,
        "measurement": "documented commands, shared run id, store receipt, deterministic inputs, and artifact paths",
    },
    {
        "metric": "accountability_receipts",
        "weight": 0.05,
        "measurement": "byte-witness, attached-witness, schema, and content-addressed receipt coverage",
    },
]


DATASET_LANES = [
    {
        "lane": "source_mined_codebase_tasks",
        "weight": 0.16,
        "purpose": "Mine tasks from real repositories, docs, scratch artifacts, and existing benchmark outputs.",
        "pressure_variables": ["large-context", "stale-docs", "cross-repo-links", "schematic-drift"],
    },
    {
        "lane": "agentic_tool_workflows",
        "weight": 0.15,
        "purpose": "Exercise multi-step tool use, repair loops, receipts, and provider handoffs.",
        "pressure_variables": ["tool-timeout", "malformed-json", "partial-state", "handoff-gap"],
    },
    {
        "lane": "adversarial_receipt_integrity",
        "weight": 0.13,
        "purpose": "Attack witness, provenance, cache, schema, and comparison-report integrity.",
        "pressure_variables": ["false-match", "unverifiable-promoted", "receipt-drift", "hash-mismatch"],
    },
    {
        "lane": "endpoint_release_gates",
        "weight": 0.12,
        "purpose": "Gate 14B/32B endpoint health, generation, release docs, checksums, and model-card readiness.",
        "pressure_variables": ["endpoint-down", "missing-checksum", "model-card-gap", "profile-drift"],
    },
    {
        "lane": "guardrail_accountability_friction",
        "weight": 0.10,
        "purpose": "Compare guardrail-on, guardrail-off, and accountability-first modes on the same safe tasks.",
        "pressure_variables": ["unnecessary-refusal", "over-compliance", "receipt-omission", "latency-tax"],
    },
    {
        "lane": "local_resource_pressure",
        "weight": 0.10,
        "purpose": "Measure smaller-model behavior under memory, context, storage, and concurrency pressure.",
        "pressure_variables": ["low-vram", "long-context", "parallel-runs", "disk-pressure"],
    },
    {
        "lane": "cross_harness_reproducibility",
        "weight": 0.10,
        "purpose": "Run equivalent tasks across Codex, flywheel, Claude Code, OpenCode, and direct local endpoints.",
        "pressure_variables": ["adapter-skew", "provider-skip", "schema-mismatch", "run-id-drift"],
    },
    {
        "lane": "replayable_causal_ledger_scaling",
        "weight": 0.08,
        "purpose": "Measure replayable causal ledger verification, deep payload hashing, redaction, checkpoint, and crash-recovery scaling.",
        "pressure_variables": ["entry-count-scale", "payload-byte-scale", "redaction-ratio", "crash-torn-final-write", "parent-chain-depth", "checkpoint-interval"],
    },
    {
        "lane": "embodied_realtime_multimodal",
        "weight": 0.06,
        "purpose": "Measure tiny/realtime local-model behavior for robotics-style sensing, code-drawn visual reasoning, and affective drift under strict latency budgets.",
        "pressure_variables": ["real-time-latency", "tiny-parameter-budget", "sensor-token-stream", "code-drawing-visual-grounding", "affective-possessiveness-drift"],
    },
]


BENCHMARK_ROWS = [
    {
        "id": "m7_source_mined",
        "status": "runnable",
        "suite": "seed",
        "purpose": "Compare Codex/Flywheel providers on source-mined benchmark cases.",
        "command_template": "python scripts/run_m7_eval.py --source-mined --source-mined-providers {providers} --source-mined-max-cases {max_cases}",
        "default_max_cases": 2,
        "evidence_schema": "m7-source-mined-scorecard/v1",
        "metrics": ["task_completion", "quality", "latency", "failure_mode_clarity", "reproducibility"],
        "failure_classes": ["provider_unavailable", "timeout", "low_quality", "missing_source_grounding"],
        "granularity": "provider x case x metric",
        "coverage_units": [
            "buildlang_buildc_compiler_receipts",
            "adversarial_pressure_weighted_benchmarks",
        ],
    },
    {
        "id": "m7_governed_agent",
        "status": "runnable",
        "suite": "seed",
        "purpose": "Exercise governed-agent workflow, maturity gates, and schematic/doc gates.",
        "command_template": "python scripts/run_m7_eval.py --governed-agent --governed-providers {providers} --governed-backend-max-scenarios {max_scenarios}",
        "default_max_scenarios": 2,
        "evidence_schema": "m7-governed-agent-scorecard/v1",
        "metrics": ["task_completion", "quality", "tool_use_success", "accountability_receipts", "reproducibility"],
        "failure_classes": ["malformed_action_json", "schematic_drift", "unauthorized_mutation", "provider_unavailable"],
        "granularity": "provider x scenario x gate",
        "coverage_units": [
            "maturity_tier_promotion",
            "schematic_drift_gate",
            "tool_action_receipts",
        ],
    },
    {
        "id": "unisonai_stateful_provider_matrix",
        "status": "runnable",
        "suite": "seed",
        "purpose": "Run stateful provider-action workflows across local, subscription, and harness providers.",
        "command_template": "python scripts/run_unisonai_stateful_benchmark.py --providers {providers} --repair-json",
        "evidence_schema": "unisonai.stateful-provider-matrix/v1",
        "metrics": ["task_completion", "tool_use_success", "workflow_state_management", "reliability", "failure_mode_clarity"],
        "failure_classes": ["malformed_action_json", "empty_repair_actions", "provider_skipped", "endpoint_error"],
        "granularity": "provider x action x repair outcome",
        "coverage_units": [
            "stateful_action_json",
            "repair_json",
            "provider_matrix",
        ],
    },
    {
        "id": "classifier_friction_accountability",
        "status": "runnable",
        "suite": "seed",
        "purpose": "Measure prompt-layer guardrail friction against accountability-first receipt workflows.",
        "command_template": "python scripts/run_classifier_friction_benchmark.py --providers {providers} --modes-to-test guardrail_on,guardrail_off,accountability_first",
        "evidence_schema": "classifier-friction-benchmark/v1",
        "metrics": ["quality", "groundedness", "latency", "failure_mode_clarity", "accountability_receipts", "reliability"],
        "failure_classes": [
            "provider_error",
            "unnecessary_refusal",
            "empty_response",
            "low_task_focus",
            "low_quality",
            "incomplete_receipt_witness",
        ],
        "granularity": "provider x prompt-layer mode x task x metric",
        "coverage_units": [
            "enterprise_vuln_triage_safe:guardrail_on",
            "enterprise_vuln_triage_safe:guardrail_off",
            "enterprise_vuln_triage_safe:accountability_first",
            "gram_access_control_eval:guardrail_on",
            "gram_access_control_eval:guardrail_off",
            "gram_access_control_eval:accountability_first",
            "workspace_receipt_audit:guardrail_on",
            "workspace_receipt_audit:guardrail_off",
            "workspace_receipt_audit:accountability_first",
        ],
    },
    {
        "id": "adversarial_pressure_full_matrix",
        "status": "planned_full",
        "suite": "full",
        "purpose": "Apply seven adversarial lanes across the full provider matrix with proof-backed graceful degradation.",
        "command_template": "python scripts/run_m7_eval.py --source-mined --source-mined-categories adversarial_pressure --source-mined-providers {providers}",
        "evidence_schema": "m7-source-mined-scorecard/v1",
        "metrics": ["quality", "groundedness", "failure_mode_clarity", "accountability_receipts", "reliability"],
        "failure_classes": ["false_match", "unverifiable_promoted", "receipt_drift", "untyped_escalation"],
        "granularity": "provider x adversarial lane x witness condition",
        "coverage_units": [
            "proof_integrity",
            "graceful_degradation",
            "cross_harness_consistency",
            "tool_failure_recovery",
            "release_dataset_provenance",
            "schematic_drift",
            "provider_refusal_accountability",
        ],
    },
    {
        "id": "local_model_release_gate_14b_32b",
        "status": "planned_full",
        "suite": "full",
        "purpose": "Gate 14B and 32B naming/publication through endpoint, checksum, model-card, and benchmark evidence.",
        "command_template": "python scripts/run_model_release_readiness.py --models 14B,32B --base-root E:/local-model-run",
        "evidence_schema": "harness.model-release-readiness/v1",
        "supporting_evidence_schemas": ["harness.model-endpoint-profiles/v1", "harness.model-endpoint-gate/v1"],
        "metrics": ["task_completion", "groundedness", "reproducibility", "cost_resource_use", "accountability_receipts"],
        "failure_classes": ["missing_weights", "missing_model_card", "missing_checksum", "missing_endpoint_profile"],
        "granularity": "model x release artifact x evidence gate",
        "coverage_units": [
            "14B",
            "32B",
        ],
    },
    {
        "id": "gather_live_source_intake",
        "status": "planned_full",
        "suite": "full",
        "purpose": "Run bounded source capture receipts when credentials and configs are present.",
        "command_template": "python scripts/run_gather_readiness.py --gather-root C:/dev/public/gather --config-roots C:/dev/local-model/configs",
        "evidence_schema": "harness.gather-readiness/v1",
        "metrics": ["groundedness", "reproducibility", "accountability_receipts", "failure_mode_clarity"],
        "failure_classes": ["missing_credential", "capture_skipped", "source_unavailable", "receipt_missing"],
        "granularity": "source x config x receipt item",
        "coverage_units": [
            "discord_channel_capture",
            "discord_guild_capture",
            "source_receipts",
        ],
    },
    {
        "id": "closed_loop_agentic_gauntlet",
        "status": "planned_full",
        "suite": "full",
        "purpose": "Run long-horizon agentic workflows that require context gathering, routing, tool repair, endpoint use, and outcome synthesis.",
        "command_template": "python scripts/run_closed_loop_benchmark_seed.py --source-mined-max-cases {max_cases} --unisonai-providers {providers}",
        "evidence_schema": "harness.closed-loop-seed/v1",
        "supporting_evidence_schemas": [
            "harness.tool-readiness/v1",
            "harness.model-endpoint-gate/v1",
            "harness.comparison-report/v1",
        ],
        "metrics": [
            "task_completion",
            "workflow_state_management",
            "tool_use_success",
            "reliability",
            "reproducibility",
            "accountability_receipts",
        ],
        "failure_classes": ["lost_state", "bad_step_order", "tool_repair_failed", "outcome_synthesis_gap"],
        "granularity": "provider x workflow x turn x tool boundary x receipt",
        "coverage_units": [
            "scratch_context_intake",
            "forum_routing",
            "index_fallback",
            "endpoint_gate",
            "comparison_report",
            "outcome_report",
        ],
    },
    {
        "id": "cross_harness_reproducibility_matrix",
        "status": "planned_full",
        "suite": "full",
        "purpose": "Replay equivalent tasks across Codex, flywheel, Claude Code, OpenCode, and direct local endpoints with shared run ids.",
        "command_template": "python scripts/run_harness_comparison_report.py --artifact-roots {artifact_roots}",
        "evidence_schema": "harness.comparison-report/v1",
        "metrics": ["task_completion", "quality", "latency", "reproducibility", "failure_mode_clarity"],
        "failure_classes": ["missing_counterpart", "adapter_schema_drift", "provider_role_unknown", "noncomparable_task"],
        "granularity": "task x provider_role x harness x metric delta",
        "coverage_units": [
            "codex_vs_flywheel",
            "codex_vs_claude_code",
            "codex_vs_opencode",
            "flywheel_vs_local_endpoint",
        ],
    },
    {
        "id": "local_resource_pressure_14b_32b",
        "status": "planned_full",
        "suite": "full",
        "purpose": "Stress 14B/32B local models under bounded context, memory, concurrency, and endpoint-restart conditions.",
        "command_template": "python scripts/run_model_endpoint_gate.py --models 14B,32B --base-root E:/local-model-run",
        "evidence_schema": "harness.model-endpoint-gate/v1",
        "metrics": ["task_completion", "latency", "cost_resource_use", "reliability", "failure_mode_clarity"],
        "failure_classes": ["endpoint_down", "generation_empty", "oom_pressure", "restart_required", "timeout"],
        "granularity": "model x endpoint x pressure mode x generation gate",
        "coverage_units": [
            "14B_low_memory",
            "14B_long_context",
            "32B_low_memory",
            "32B_long_context",
            "endpoint_restart",
        ],
    },
    {
        "id": "forum_ledger_deep_verify_scaling",
        "status": "planned_full",
        "suite": "full",
        "purpose": "Measure Forum replayable causal ledger verify(deep=True) scaling across entry count, payload size, storage mode, redaction, and tamper/crash controls.",
        "command_template": "python -m forum.cli bench-deep-verify --entries {entry_counts} --payload-bytes {payload_bytes} --storage memory --storage file-sync --storage file-batched --redaction-ratio {redaction_ratios} --json --out {out}",
        "evidence_schema": "forum.deep-verify-benchmark/v1",
        "metrics": ["latency", "cost_resource_use", "reproducibility", "accountability_receipts", "failure_mode_clarity"],
        "failure_classes": ["hash_mismatch", "payload_missing", "crash_torn_write", "checkpoint_drift", "timeout"],
        "granularity": "entry_count x payload_bytes x storage_mode x redaction_ratio x verify_mode",
        "coverage_units": [
            "verify_chain_only",
            "verify_payloads_present",
            "verify_deep_redacted",
            "file_storage_fsync_each",
            "file_storage_batched",
            "checkpoint_merkle_root",
            "crash_torn_final_write",
            "tamper_drop_reorder_substitute",
        ],
    },
    {
        "id": "embodied_realtime_multimodal_pressure",
        "status": "planned_full",
        "suite": "full",
        "purpose": "Turn Boris/ENBSeries-style robotics and multimodal curiosity into bounded probes for small-model real-time usefulness, visual-code spatial grounding, raw/simplified sensor streams, and affective failure modes.",
        "command_template": "planned: python scripts/run_embodied_realtime_multimodal_benchmark.py --providers {providers} --latency-budget-ms {latency_budget_ms}",
        "evidence_schema": "harness.embodied-realtime-multimodal/v1",
        "metrics": ["task_completion", "quality", "groundedness", "latency", "cost_resource_use", "reliability", "failure_mode_clarity"],
        "failure_classes": ["sensor_misgrounding", "visual_code_spatial_error", "latency_budget_exceeded", "possessive_affect_drift", "control_loop_unstable", "model_card_unverified"],
        "granularity": "provider x modality probe x latency budget x failure mode",
        "coverage_units": [
            "tiny_model_robotics_latency",
            "code_drawn_letter_grid_spatial_fix",
            "synthetic_vision_token_grounding",
            "raw_audio_projection_probe",
            "affective_jealousy_possessiveness_probe",
            "multimodal_model_card_verification",
        ],
    },
    {
        "id": "toolchain_failure_recovery_matrix",
        "status": "planned_full",
        "suite": "full",
        "purpose": "Inject index, gather, mneme, relay, plexus, and endpoint failures and require typed recovery receipts.",
        "command_template": "python scripts/run_tool_hardening_plan.py --readiness-artifact {tool_readiness_artifact}",
        "evidence_schema": "harness.tool-hardening-plan/v1",
        "metrics": ["tool_use_success", "workflow_state_management", "reliability", "failure_mode_clarity", "accountability_receipts"],
        "failure_classes": ["transport_closed", "missing_config", "stale_artifact", "readiness_unverifiable", "repair_unavailable"],
        "granularity": "tool x failure injection x recovery action x receipt",
        "coverage_units": [
            "index_transport_closed",
            "gather_config_missing",
            "mneme_ready_gap",
            "relay_ready_gap",
            "plexus_ready_gap",
        ],
    },
]


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _split_paths(value: str) -> list[Path]:
    return [Path(part.strip()) for part in value.split(";") if part.strip()]


def _write(path_text: str, text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def _artifact_labels(name: str) -> list[str]:
    lowered = name.lower()
    labels = []
    for token, label in (
        ("m7", "m7"),
        ("unisonai", "unisonai"),
        ("benchmark", "benchmark"),
        ("classifier", "classifier"),
        ("scorecard", "scorecard"),
        ("friction", "friction"),
        ("closed_loop", "closed_loop"),
        ("adversarial", "adversarial"),
        ("governed", "governed"),
        ("source_mined", "source_mined"),
        ("model_release", "model_release"),
        ("gather", "gather"),
    ):
        if token in lowered:
            labels.append(label)
    return labels


def inventory_existing_artifacts(artifact_roots: str, *, max_artifacts: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for root in _split_paths(artifact_roots):
        if not root.exists():
            rows.append({
                "root": str(root),
                "exists": False,
                "path": "",
                "size_bytes": 0,
                "modified_utc": "",
                "labels": [],
            })
            continue
        for path in root.glob("*.json"):
            labels = _artifact_labels(path.name)
            if not labels:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            rows.append({
                "root": str(root),
                "exists": True,
                "path": str(path),
                "size_bytes": int(stat.st_size),
                "modified_utc": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat().replace("+00:00", "Z"),
                "labels": labels,
            })
    rows.sort(key=lambda row: (row.get("modified_utc", ""), row.get("path", "")), reverse=True)
    return rows[:max_artifacts]


def _suite_rows(benchmarks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    suites: dict[str, list[dict[str, Any]]] = {}
    for row in benchmarks:
        suites.setdefault(str(row.get("suite", "seed")), []).append(row)
    return [
        {
            "suite": name,
            "benchmark_count": len(rows),
            "benchmark_ids": [str(row.get("id", "")) for row in rows if row.get("id")],
            "runnable_count": sum(1 for row in rows if row.get("status") == "runnable"),
            "planned_count": sum(1 for row in rows if str(row.get("status", "")).startswith("planned")),
        }
        for name, rows in sorted(suites.items())
    ]


def build_profile(
    *,
    providers: str = DEFAULT_PROVIDERS,
    artifact_roots: str = DEFAULT_ARTIFACT_ROOTS,
    max_artifacts: int = 200,
) -> dict[str, Any]:
    provider_list = _split_csv(providers)
    provider_roles = provider_roles_for(provider_list)
    artifacts = inventory_existing_artifacts(artifact_roots, max_artifacts=max_artifacts)
    metrics = sorted({metric for row in BENCHMARK_ROWS for metric in row.get("metrics", [])})
    pressure_variables = sorted({
        variable
        for row in DATASET_LANES
        for variable in row.get("pressure_variables", [])
    })
    runnable = [row for row in BENCHMARK_ROWS if row.get("status") == "runnable"]
    return {
        "schema": "harness.benchmark-profile-manifest/v1",
        "timestamp_utc": _now(),
        "profile_id": "codex_flywheel_local_model_benchmark_profile",
        "mission": "Compare Codex, flywheel, Claude Code, OpenCode, and local-model harness behavior with weighted, receipt-backed agentic measurements.",
        "providers": provider_list,
        "provider_roles": PROVIDER_ROLES,
        "expected_provider_roles": provider_roles,
        "provider_aliases": provider_alias_map(),
        "metric_weights": METRIC_WEIGHTS,
        "metric_weight_sum": round(sum(float(row["weight"]) for row in METRIC_WEIGHTS), 6),
        "dataset_lanes": DATASET_LANES,
        "dataset_lane_weight_sum": round(sum(float(row["weight"]) for row in DATASET_LANES), 6),
        "pressure_variables": pressure_variables,
        "metrics": metrics,
        "benchmark_suites": _suite_rows(BENCHMARK_ROWS),
        "benchmarks": BENCHMARK_ROWS,
        "existing_artifacts": artifacts,
        "summary": {
            "providers": len(provider_list),
            "provider_names": provider_list,
            "provider_roles": len(provider_roles),
            "provider_role_ids": provider_roles,
            "benchmarks": len(BENCHMARK_ROWS),
            "runnable_benchmarks": len(runnable),
            "planned_full_benchmarks": len(BENCHMARK_ROWS) - len(runnable),
            "suites": len(_suite_rows(BENCHMARK_ROWS)),
            "metrics": len(metrics),
            "dataset_lanes": len(DATASET_LANES),
            "pressure_variables": len(pressure_variables),
            "coverage_units": sum(len(row.get("coverage_units", [])) for row in BENCHMARK_ROWS),
            "existing_artifacts": sum(1 for row in artifacts if row.get("path")),
            "missing_artifact_roots": sum(1 for row in artifacts if row.get("exists") is False and not row.get("path")),
        },
    }


def render_markdown(profile: dict[str, Any]) -> str:
    lines = [
        "# Benchmark profile manifest",
        "",
        f"- Schema: `{profile['schema']}`",
        f"- Timestamp UTC: `{profile['timestamp_utc']}`",
        f"- Profile id: `{profile['profile_id']}`",
        f"- Metric weight sum: `{profile['metric_weight_sum']}`",
        f"- Dataset lane weight sum: `{profile['dataset_lane_weight_sum']}`",
        f"- Providers: `{', '.join(profile['providers'])}`",
        f"- Provider roles: `{', '.join(profile['expected_provider_roles'])}`",
        "",
        "## Metric weights",
        "",
        "| Metric | Weight | Measurement |",
        "|---|---:|---|",
    ]
    for row in profile["metric_weights"]:
        lines.append(f"| {row['metric']} | {row['weight']} | {row['measurement']} |")
    lines.extend(["", "## Dataset lanes", "", "| Lane | Weight | Pressure variables |", "|---|---:|---|"])
    for row in profile["dataset_lanes"]:
        lines.append(
            f"| {row['lane']} | {row['weight']} | {', '.join(row.get('pressure_variables', []))} |"
        )
    lines.extend(["", "## Benchmark suites", "", "| Suite | Benchmarks | Runnable | Planned |", "|---|---:|---:|---:|"])
    for row in profile["benchmark_suites"]:
        lines.append(f"| {row['suite']} | {row['benchmark_count']} | {row['runnable_count']} | {row['planned_count']} |")
    lines.extend(["", "## Benchmarks", "", "| Benchmark | Status | Schema | Metrics | Units | Granularity |", "|---|---|---|---|---:|---|"])
    for row in profile["benchmarks"]:
        lines.append(
            "| {id} | {status} | {schema} | {metrics} | {units} | {granularity} |".format(
                id=row.get("id", ""),
                status=row.get("status", ""),
                schema=row.get("evidence_schema", ""),
                metrics=", ".join(row.get("metrics", [])),
                units=len(row.get("coverage_units", [])),
                granularity=row.get("granularity", ""),
            )
        )
    lines.extend([
        "",
        "## Existing artifact inventory",
        "",
        f"- Artifacts observed: `{profile['summary']['existing_artifacts']}`",
        f"- Missing roots: `{profile['summary']['missing_artifact_roots']}`",
    ])
    return "\n".join(lines) + "\n"


def store_profile(
    profile: dict[str, Any],
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
            kind="benchmark_profile_manifest",
            body=profile,
            run_id=run_id,
            verdict="BENCHMARK_PROFILE_RECORDED",
        )
    ]
    for path_text, label in artifacts:
        if path_text and Path(path_text).exists():
            outputs.append(store.copy_artifact(Path(path_text), run_id=run_id, label=label))
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--providers", default=DEFAULT_PROVIDERS)
    parser.add_argument("--artifact-roots", default=DEFAULT_ARTIFACT_ROOTS)
    parser.add_argument("--max-artifacts", type=int, default=200)
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    profile = build_profile(
        providers=args.providers,
        artifact_roots=args.artifact_roots,
        max_artifacts=args.max_artifacts,
    )
    json_text = json.dumps(profile, indent=2, sort_keys=True)
    md_text = render_markdown(profile)
    json_path = _write(args.out, json_text)
    md_path = _write(args.markdown_out, md_text)
    store_outputs = store_profile(
        profile,
        store_root=args.store_root,
        run_id=args.run_id,
        artifacts=[
            (json_path, "benchmark-profile-manifest-json"),
            (md_path, "benchmark-profile-manifest-markdown"),
        ],
    )
    if store_outputs:
        profile = {**profile, "store_outputs": store_outputs}
        json_text = json.dumps(profile, indent=2, sort_keys=True)
    print(json_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
