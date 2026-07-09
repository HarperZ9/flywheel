"""Synthesize a closed-loop benchmark seed report into an outcome document."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.file_backed_store import FileBackedHarnessStore  # noqa: E402


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def find_seed_report_in_store(*, store_root: str, run_id: str) -> str:
    if not store_root or not run_id:
        return ""
    store = FileBackedHarnessStore(Path(store_root))
    candidates = [
        row
        for row in store.artifacts_for_run(run_id)
        if row.get("label") == "closed-loop-seed-report-json"
    ]
    if not candidates:
        return ""
    return str(candidates[-1].get("stored_path", ""))


def _step_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    results = report.get("results")
    if isinstance(results, list) and results:
        return [row for row in results if isinstance(row, dict)]
    planned = report.get("planned_steps")
    if isinstance(planned, list):
        return [
            {
                **row,
                "status": "planned",
                "returncode": None,
                "elapsed_ms": 0,
            }
            for row in planned
            if isinstance(row, dict)
        ]
    return []


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _read_child_json(path_text: str) -> tuple[dict[str, Any] | None, str]:
    if not path_text or not path_text.lower().endswith(".json"):
        return None, "not_json_artifact"
    path = Path(path_text)
    try:
        return json.loads(path.read_text(encoding="utf-8")), ""
    except FileNotFoundError:
        return None, "missing_artifact"
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"unreadable_artifact:{type(exc).__name__}"


def _source_mined_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    rows = data.get("backend_rows") if isinstance(data.get("backend_rows"), list) else []
    return {
        "artifact_path": path_text,
        "schema": data.get("schema", ""),
        "kind": "m7_source_mined",
        "comparison": data.get("summary", {}).get("comparison", {}),
        "provider_metrics": [
            {
                "provider": row.get("provider", ""),
                "backend_name": row.get("backend_name", ""),
                "live": bool(row.get("live")),
                "skipped": bool(row.get("skipped")),
                "operational": bool(row.get("operational")),
                "pass_rate": _safe_float(row.get("pass_rate")),
                "quality": _safe_float(row.get("aggregate_metrics", {}).get("mean_quality_score")),
                "latency_ms": _safe_float(row.get("mean_latency_ms")),
                "failure_class_counts": row.get("aggregate_metrics", {}).get("failure_class_counts", {}),
            }
            for row in rows
            if isinstance(row, dict)
        ],
    }


def _governed_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    rows = data.get("backend_rows") if isinstance(data.get("backend_rows"), list) else []
    return {
        "artifact_path": path_text,
        "schema": data.get("schema", ""),
        "kind": "m7_governed_agent",
        "comparison": data.get("summary", {}).get("comparison", {}),
        "provider_metrics": [
            {
                "provider": row.get("provider", ""),
                "backend_name": row.get("backend_name", ""),
                "live": bool(row.get("live")),
                "skipped": bool(row.get("skipped")),
                "operational": bool(row.get("operational")),
                "pass_rate": _safe_float(row.get("pass_rate")),
                "quality": _safe_float(row.get("mean_quality_score")),
                "latency_ms": _safe_float(row.get("mean_latency_ms")),
                "error_rate": _safe_float(row.get("error_rate")),
            }
            for row in rows
            if isinstance(row, dict)
        ],
    }


def _unisonai_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    rows = data.get("rows") if isinstance(data.get("rows"), list) else []
    return {
        "artifact_path": path_text,
        "schema": data.get("schema", ""),
        "kind": "unisonai_stateful_provider_matrix",
        "summary": data.get("summary", {}),
        "provider_metrics": [
            {
                "provider": row.get("provider", ""),
                "backend_name": row.get("backend_name", ""),
                "live": bool(row.get("live")),
                "skipped": bool(row.get("skipped")),
                "operational": bool(row.get("operational")),
                "passed": bool(row.get("passed")),
                "pass_rate": _safe_float(row.get("pass_rate")),
                "failure_class": row.get("failure_class", ""),
                "action_count": int(row.get("action_count", 0) or 0),
            }
            for row in rows
            if isinstance(row, dict)
        ],
    }


def _classifier_friction_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    rows = summary.get("rows") if isinstance(summary.get("rows"), list) else []
    skipped = data.get("skipped") if isinstance(data.get("skipped"), list) else []
    return {
        "artifact_path": path_text,
        "schema": data.get("schema", ""),
        "kind": "classifier_friction_accountability",
        "comparison": {"deltas": data.get("deltas", []) if isinstance(data.get("deltas"), list) else []},
        "provider_native_safety_note": data.get("provider_native_safety_note", ""),
        "tasks": data.get("tasks", []) if isinstance(data.get("tasks"), list) else [],
        "modes": data.get("modes", []) if isinstance(data.get("modes"), list) else [],
        "skipped": [
            {
                "provider": row.get("provider", ""),
                "reason": row.get("reason", ""),
            }
            for row in skipped
            if isinstance(row, dict)
        ],
        "provider_metrics": [
            {
                "provider": row.get("provider", ""),
                "backend_name": row.get("mode", ""),
                "mode": row.get("mode", ""),
                "live": True,
                "skipped": False,
                "operational": _safe_float(row.get("error_rate")) < 1.0,
                "pass_rate": _safe_float(row.get("pass_rate")),
                "quality": _safe_float(row.get("mean_quality_score")),
                "latency_ms": _safe_float(row.get("mean_latency_ms")),
                "failure_class": "classifier_friction",
                "refusal_rate": _safe_float(row.get("refusal_rate")),
                "unnecessary_refusal_rate": _safe_float(row.get("unnecessary_refusal_rate")),
                "provider_native_guardrail_observed_rate": _safe_float(row.get("provider_native_guardrail_observed_rate")),
                "mean_accountability_score": _safe_float(row.get("mean_accountability_score")),
                "mean_proof_surface_score": _safe_float(row.get("mean_proof_surface_score")),
                "mean_byte_witness_score": _safe_float(row.get("mean_byte_witness_score")),
                "mean_workspace_limit_score": _safe_float(row.get("mean_workspace_limit_score")),
            }
            for row in rows
            if isinstance(row, dict)
        ],
    }


def _context_inventory_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    roots = data.get("roots") if isinstance(data.get("roots"), list) else []
    return {
        "artifact_path": path_text,
        "schema": data.get("schema", ""),
        "kind": "context_inventory",
        "summary": {
            "roots": int(summary.get("roots", 0) or 0),
            "existing_roots": int(summary.get("existing_roots", 0) or 0),
            "entries": int(summary.get("entries", 0) or 0),
            "files": int(summary.get("files", 0) or 0),
            "directories": int(summary.get("directories", 0) or 0),
            "sensitive_name_entries": int(summary.get("sensitive_name_entries", 0) or 0),
            "label_counts": summary.get("label_counts", {}),
        },
        "roots": [
            {
                "root": row.get("root", ""),
                "exists": bool(row.get("exists")),
                "observed_entries": int(row.get("observed_entries", 0) or 0),
                "truncated": bool(row.get("truncated")),
            }
            for row in roots
            if isinstance(row, dict)
        ],
    }


def _tool_readiness_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    rows = data.get("tools") if isinstance(data.get("tools"), list) else []
    return {
        "artifact_path": path_text,
        "schema": data.get("schema", ""),
        "kind": "tool_readiness",
        "summary": data.get("summary", {}),
        "tool_metrics": [
            {
                "tool": row.get("tool", ""),
                "root_exists": bool(row.get("root_exists")),
                "enterprise_ready": bool(row.get("enterprise_ready")),
                "verdict": row.get("verdict", ""),
                "score": _safe_float(row.get("score")),
                "core_score": _safe_float(row.get("categories", {}).get("core", {}).get("score")),
                "enterprise_score": _safe_float(row.get("categories", {}).get("enterprise", {}).get("score")),
                "integration_score": _safe_float(row.get("categories", {}).get("integration", {}).get("score")),
            }
            for row in rows
            if isinstance(row, dict)
        ],
    }


def _tool_hardening_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    actions = data.get("actions") if isinstance(data.get("actions"), list) else []
    gates = data.get("release_gates") if isinstance(data.get("release_gates"), list) else []
    return {
        "artifact_path": path_text,
        "schema": data.get("schema", ""),
        "kind": "tool_hardening_plan",
        "summary": summary,
        "action_metrics": [
            {
                "tool": row.get("tool", ""),
                "priority": row.get("priority", ""),
                "category": row.get("category", ""),
                "owner": row.get("owner", ""),
                "path": row.get("path", ""),
            }
            for row in actions
            if isinstance(row, dict)
        ],
        "release_gate_metrics": [
            {
                "tool": row.get("tool", ""),
                "gate_id": row.get("gate_id", ""),
                "category": row.get("category", ""),
                "passed": bool(row.get("passed")),
            }
            for row in gates
            if isinstance(row, dict)
        ],
    }


def _model_release_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    rows = data.get("models") if isinstance(data.get("models"), list) else []
    return {
        "artifact_path": path_text,
        "schema": data.get("schema", ""),
        "kind": "model_release_readiness",
        "summary": data.get("summary", {}),
        "model_metrics": [
            {
                "model": row.get("model", ""),
                "root_exists": bool(row.get("root_exists")),
                "enterprise_release_ready": bool(row.get("enterprise_release_ready")),
                "verdict": row.get("verdict", ""),
                "weight_file_count": int(row.get("weight_file_count", 0) or 0),
                "weight_total_size_bytes": int(row.get("weight_total_size_bytes", 0) or 0),
                "release_doc_score": _safe_float(row.get("release_doc_score")),
                "endpoint_profile_count": int(row.get("endpoint_profile_count", 0) or 0),
                "endpoint_gate_row_count": int(row.get("endpoint_gate_row_count", 0) or 0),
                "endpoint_gate_generation_ok_count": int(row.get("endpoint_gate_generation_ok_count", 0) or 0),
                "benchmark_artifact_count": int(row.get("benchmark_artifact_count", 0) or 0),
            }
            for row in rows
            if isinstance(row, dict)
        ],
    }


def _model_publish_plan_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    rows = data.get("models") if isinstance(data.get("models"), list) else []
    return {
        "artifact_path": path_text,
        "schema": data.get("schema", ""),
        "kind": "model_publish_plan",
        "summary": summary,
        "model_publish_metrics": [
            {
                "model": row.get("model", ""),
                "candidate_name": row.get("candidate_name", ""),
                "candidate_slug": row.get("candidate_slug", ""),
                "publish_status": row.get("publish_status", ""),
                "blockers": len(row.get("blockers", []) if isinstance(row.get("blockers"), list) else []),
                "actions": len(row.get("actions", []) if isinstance(row.get("actions"), list) else []),
            }
            for row in rows
            if isinstance(row, dict)
        ],
    }


def _model_endpoint_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    rows = data.get("profiles") if isinstance(data.get("profiles"), list) else []
    return {
        "artifact_path": path_text,
        "schema": data.get("schema", ""),
        "kind": "model_endpoint_profiles",
        "summary": data.get("summary", {}),
        "endpoint_metrics": [
            {
                "profile_id": row.get("profile_id", ""),
                "model": row.get("model", ""),
                "backend": row.get("backend", ""),
                "provider_role": row.get("provider_role", ""),
                "root_exists": bool(row.get("root_exists")),
                "supports_agentic_workflow": bool(row.get("supports_agentic_workflow")),
                "live_probed": bool(row.get("live_probed")),
                "endpoint_url": row.get("endpoint_url", ""),
                "agentic_backend": row.get("agentic_backend", ""),
            }
            for row in rows
            if isinstance(row, dict)
        ],
    }


def _model_endpoint_gate_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    rows = data.get("rows") if isinstance(data.get("rows"), list) else []
    return {
        "artifact_path": path_text,
        "schema": data.get("schema", ""),
        "kind": "model_endpoint_gate",
        "summary": data.get("summary", {}),
        "endpoint_gate_metrics": [
            {
                "model": row.get("model", ""),
                "backend": row.get("backend", ""),
                "provider_role": row.get("provider_role", ""),
                "health_ok": bool(row.get("health_ok")),
                "generation_ok": bool(row.get("generation_ok")),
                "failure_class": row.get("failure_class", ""),
                "latency_ms": _safe_float(row.get("latency_ms")),
            }
            for row in rows
            if isinstance(row, dict)
        ],
    }


def _gather_readiness_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    return {
        "artifact_path": path_text,
        "schema": data.get("schema", ""),
        "kind": "gather_readiness",
        "summary": summary,
        "gather_metrics": {
            "root_exists": bool(summary.get("root_exists")),
            "config_count": int(summary.get("config_count", 0) or 0),
            "credential_present": bool(summary.get("credential_present")),
            "core_score": _safe_float(summary.get("core_score")),
            "discord_score": _safe_float(summary.get("discord_score")),
            "verdict": summary.get("verdict", ""),
        },
    }


def _executable_manifest_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    rows = data.get("commands") if isinstance(data.get("commands"), list) else []
    return {
        "artifact_path": path_text,
        "schema": data.get("schema", ""),
        "kind": "harness_executable_manifest",
        "entrypoint": data.get("entrypoint", ""),
        "dispatcher": data.get("dispatcher", ""),
        "command_metrics": [
            {
                "name": row.get("name", ""),
                "delegates_to": row.get("delegates_to", ""),
                "schema_count": len(row.get("schemas", []) if isinstance(row.get("schemas"), list) else []),
                "schemas": row.get("schemas", []),
                "target_count": len(row.get("targets", []) if isinstance(row.get("targets"), list) else []),
                "evidence_surface": row.get("evidence_surface", ""),
            }
            for row in rows
            if isinstance(row, dict)
        ],
    }


def _command_registry_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    names = data.get("command_names") if isinstance(data.get("command_names"), list) else []
    risk_counts = data.get("risk_counts") if isinstance(data.get("risk_counts"), dict) else {}
    schemas = data.get("schemas") if isinstance(data.get("schemas"), list) else []
    return {
        "artifact_path": path_text,
        "schema": data.get("schema", ""),
        "kind": "harness_command_registry",
        "entrypoint": data.get("entrypoint", ""),
        "html_path": data.get("html_path", ""),
        "command_count": int(data.get("command_count", 0) or 0),
        "command_names": [str(name) for name in names if name],
        "risk_counts": {str(key): int(value or 0) for key, value in risk_counts.items()},
        "schema_count": int(data.get("schema_count", 0) or 0),
        "schemas": [str(schema) for schema in schemas if schema],
    }


def _benchmark_profile_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    suites = data.get("benchmark_suites") if isinstance(data.get("benchmark_suites"), list) else []
    benchmarks = data.get("benchmarks") if isinstance(data.get("benchmarks"), list) else []
    artifacts = data.get("existing_artifacts") if isinstance(data.get("existing_artifacts"), list) else []
    providers = data.get("providers") if isinstance(data.get("providers"), list) else []
    metrics = data.get("metrics") if isinstance(data.get("metrics"), list) else []
    dataset_lanes = data.get("dataset_lanes") if isinstance(data.get("dataset_lanes"), list) else []
    pressure_variables = data.get("pressure_variables") if isinstance(data.get("pressure_variables"), list) else []
    return {
        "artifact_path": path_text,
        "schema": data.get("schema", ""),
        "kind": "benchmark_profile_manifest",
        "profile_id": data.get("profile_id", ""),
        "metric_weight_sum": _safe_float(data.get("metric_weight_sum")),
        "dataset_lane_weight_sum": _safe_float(data.get("dataset_lane_weight_sum")),
        "providers": [str(provider) for provider in providers if provider],
        "metrics": [str(metric) for metric in metrics if metric],
        "dataset_lanes": [
            str(row.get("lane", ""))
            for row in dataset_lanes
            if isinstance(row, dict) and row.get("lane")
        ],
        "pressure_variables": [str(variable) for variable in pressure_variables if variable],
        "suite_metrics": [
            {
                "suite": row.get("suite", ""),
                "benchmark_count": int(row.get("benchmark_count", 0) or 0),
                "runnable_count": int(row.get("runnable_count", 0) or 0),
                "planned_count": int(row.get("planned_count", 0) or 0),
            }
            for row in suites
            if isinstance(row, dict)
        ],
        "benchmark_metrics": [
            {
                "id": row.get("id", ""),
                "status": row.get("status", ""),
                "evidence_schema": row.get("evidence_schema", ""),
                "granularity": row.get("granularity", ""),
                "coverage_units": row.get("coverage_units", []) if isinstance(row.get("coverage_units"), list) else [],
            }
            for row in benchmarks
            if isinstance(row, dict)
        ],
        "summary": {
            "benchmarks": int(summary.get("benchmarks", len(benchmarks)) or 0),
            "runnable_benchmarks": int(summary.get("runnable_benchmarks", 0) or 0),
            "planned_full_benchmarks": int(summary.get("planned_full_benchmarks", 0) or 0),
            "coverage_units": int(summary.get("coverage_units", 0) or 0),
            "existing_artifacts": int(
                summary.get(
                    "existing_artifacts",
                    len([row for row in artifacts if isinstance(row, dict) and row.get("path")]),
                )
                or 0
            ),
        },
    }


def _benchmark_execution_matrix_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    tiers = data.get("tiers") if isinstance(data.get("tiers"), list) else []
    steps = data.get("steps") if isinstance(data.get("steps"), list) else []
    providers = data.get("providers") if isinstance(data.get("providers"), list) else []
    provider_roles = data.get("expected_provider_roles") if isinstance(data.get("expected_provider_roles"), list) else []
    return {
        "artifact_path": path_text,
        "schema": data.get("schema", ""),
        "kind": "benchmark_execution_matrix",
        "matrix_id": data.get("matrix_id", ""),
        "run_id": data.get("run_id", ""),
        "providers": [str(provider) for provider in providers if provider],
        "expected_provider_roles": [str(role) for role in provider_roles if role],
        "tier_metrics": [
            {
                "tier": row.get("tier", ""),
                "step_count": int(row.get("step_count", 0) or 0),
                "long_running_steps": int(row.get("long_running_steps", 0) or 0),
                "step_ids": [str(step_id) for step_id in row.get("step_ids", []) if step_id]
                if isinstance(row.get("step_ids"), list)
                else [],
            }
            for row in tiers
            if isinstance(row, dict)
        ],
        "step_metrics": [
            {
                "step_id": row.get("step_id", ""),
                "tier": row.get("tier", ""),
                "long_running": bool(row.get("long_running")),
                "operator_approval_required": bool(row.get("operator_approval_required")),
                "expected_schemas": [str(schema) for schema in row.get("expected_schemas", []) if schema]
                if isinstance(row.get("expected_schemas"), list)
                else [],
                "evidence_gates": [str(gate) for gate in row.get("evidence_gates", []) if gate]
                if isinstance(row.get("evidence_gates"), list)
                else [],
            }
            for row in steps
            if isinstance(row, dict)
        ],
        "summary": {
            "steps": int(summary.get("steps", len(steps)) or 0),
            "dry_steps": int(summary.get("dry_steps", 0) or 0),
            "focused_steps": int(summary.get("focused_steps", 0) or 0),
            "full_steps": int(summary.get("full_steps", 0) or 0),
            "long_running_steps": int(summary.get("long_running_steps", 0) or 0),
            "operator_approval_required_steps": int(summary.get("operator_approval_required_steps", 0) or 0),
            "expected_schemas": [str(schema) for schema in summary.get("expected_schemas", []) if schema]
            if isinstance(summary.get("expected_schemas"), list)
            else [],
            "evidence_gates": [str(gate) for gate in summary.get("evidence_gates", []) if gate]
            if isinstance(summary.get("evidence_gates"), list)
            else [],
        },
    }


def _benchmark_coverage_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    return {
        "artifact_path": path_text,
        "schema": data.get("schema", ""),
        "kind": "benchmark_profile_coverage",
        "verdict": summary.get("verdict", ""),
        "benchmark_coverage_rate": _safe_float(summary.get("benchmark_coverage_rate")),
        "unit_coverage_rate": _safe_float(summary.get("unit_coverage_rate")),
        "unit_metric_completeness_rate": _safe_float(summary.get("unit_metric_completeness_rate")),
        "unit_metric_validity_rate": _safe_float(summary.get("unit_metric_validity_rate")),
        "provider_coverage_rate": _safe_float(summary.get("provider_coverage_rate")),
        "provider_unit_coverage_rate": _safe_float(summary.get("provider_unit_coverage_rate")),
        "provider_unit_validity_rate": _safe_float(summary.get("provider_unit_validity_rate")),
        "raw_expected_providers": [
            str(item)
            for item in (summary.get("raw_expected_providers") if isinstance(summary.get("raw_expected_providers"), list) else [])
            if item
        ],
        "provider_aliases": {
            str(key): str(value)
            for key, value in (summary.get("provider_aliases") if isinstance(summary.get("provider_aliases"), dict) else {}).items()
            if key and value
        },
        "dataset_lane_coverage_rate": _safe_float(summary.get("dataset_lane_coverage_rate")),
        "pressure_variable_coverage_rate": _safe_float(summary.get("pressure_variable_coverage_rate")),
        "declared_dataset_lanes": [
            str(item)
            for item in (summary.get("declared_dataset_lanes") if isinstance(summary.get("declared_dataset_lanes"), list) else [])
            if item
        ],
        "observed_dataset_lanes": [
            str(item)
            for item in (summary.get("observed_dataset_lanes") if isinstance(summary.get("observed_dataset_lanes"), list) else [])
            if item
        ],
        "missing_dataset_lanes": [
            str(item)
            for item in (summary.get("missing_dataset_lanes") if isinstance(summary.get("missing_dataset_lanes"), list) else [])
            if item
        ],
        "declared_pressure_variables": [
            str(item)
            for item in (summary.get("declared_pressure_variables") if isinstance(summary.get("declared_pressure_variables"), list) else [])
            if item
        ],
        "observed_pressure_variables": [
            str(item)
            for item in (summary.get("observed_pressure_variables") if isinstance(summary.get("observed_pressure_variables"), list) else [])
            if item
        ],
        "missing_pressure_variables": [
            str(item)
            for item in (summary.get("missing_pressure_variables") if isinstance(summary.get("missing_pressure_variables"), list) else [])
            if item
        ],
        "missing_runnable_benchmark_ids": [
            str(item)
            for item in (summary.get("missing_runnable_benchmark_ids") if isinstance(summary.get("missing_runnable_benchmark_ids"), list) else [])
            if item
        ],
        "missing_providers": [
            str(item)
            for item in (summary.get("missing_providers") if isinstance(summary.get("missing_providers"), list) else [])
            if item
        ],
        "observed_benchmark_ids": [
            str(item)
            for item in (summary.get("observed_benchmark_ids") if isinstance(summary.get("observed_benchmark_ids"), list) else [])
            if item
        ],
        "observed_providers": [
            str(item)
            for item in (summary.get("observed_providers") if isinstance(summary.get("observed_providers"), list) else [])
            if item
        ],
        "missing_units_by_benchmark": {
            str(key): [str(item) for item in value if item]
            for key, value in (summary.get("missing_units_by_benchmark") if isinstance(summary.get("missing_units_by_benchmark"), dict) else {}).items()
            if isinstance(value, list)
        },
        "observed_units_by_benchmark": {
            str(key): [str(item) for item in value if item]
            for key, value in (summary.get("observed_units_by_benchmark") if isinstance(summary.get("observed_units_by_benchmark"), dict) else {}).items()
            if isinstance(value, list)
        },
        "incomplete_units_by_benchmark": {
            str(key): {
                str(unit_id): [str(item) for item in missing if item]
                for unit_id, missing in value.items()
                if isinstance(missing, list)
            }
            for key, value in (summary.get("incomplete_units_by_benchmark") if isinstance(summary.get("incomplete_units_by_benchmark"), dict) else {}).items()
            if isinstance(value, dict)
        },
        "invalid_units_by_benchmark": {
            str(key): {
                str(unit_id): [str(item) for item in invalid if item]
                for unit_id, invalid in value.items()
                if isinstance(invalid, list)
            }
            for key, value in (summary.get("invalid_units_by_benchmark") if isinstance(summary.get("invalid_units_by_benchmark"), dict) else {}).items()
            if isinstance(value, dict)
        },
        "missing_provider_units_by_benchmark": {
            str(key): {
                str(provider): [str(item) for item in units if item]
                for provider, units in value.items()
                if isinstance(units, list)
            }
            for key, value in (summary.get("missing_provider_units_by_benchmark") if isinstance(summary.get("missing_provider_units_by_benchmark"), dict) else {}).items()
            if isinstance(value, dict)
        },
        "invalid_provider_units_by_benchmark": {
            str(key): {
                str(provider): {
                    str(unit_id): [str(item) for item in invalid if item]
                    for unit_id, invalid in units.items()
                    if isinstance(invalid, list)
                }
                for provider, units in value.items()
                if isinstance(units, dict)
            }
            for key, value in (summary.get("invalid_provider_units_by_benchmark") if isinstance(summary.get("invalid_provider_units_by_benchmark"), dict) else {}).items()
            if isinstance(value, dict)
        },
        "load_errors": int(summary.get("load_errors", 0) or 0),
    }


def _agentic_task_manifest_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    task_rows = data.get("task_rows") if isinstance(data.get("task_rows"), list) else []
    scorecard_rows = data.get("dry_scorecard_rows") if isinstance(data.get("dry_scorecard_rows"), list) else []
    benchmark_ids = sorted({
        str(row.get("benchmark_id", ""))
        for row in task_rows
        if isinstance(row, dict) and row.get("benchmark_id")
    })
    dataset_lanes = sorted({
        str(row.get("dataset_lane", ""))
        for row in task_rows
        if isinstance(row, dict) and row.get("dataset_lane")
    })
    coverage_units = sorted({
        str(row.get("coverage_unit") or row.get("task_id") or "")
        for row in task_rows
        if isinstance(row, dict) and (row.get("coverage_unit") or row.get("task_id"))
    })
    provider_roles = sorted({
        str(row.get("provider_role", ""))
        for row in scorecard_rows
        if isinstance(row, dict) and row.get("provider_role")
    } | {
        str(role)
        for role in (data.get("provider_roles") if isinstance(data.get("provider_roles"), list) else [])
        if role
    })
    prompt_hashes = sorted({
        str(row.get("prompt_hash", ""))
        for row in task_rows
        if isinstance(row, dict) and row.get("prompt_hash")
    } | {
        str(row.get("prompt_sha256", ""))
        for row in task_rows
        if isinstance(row, dict) and row.get("prompt_sha256")
    })
    return {
        "artifact_path": path_text,
        "schema": data.get("schema", ""),
        "kind": "agentic_task_manifest",
        "task_count": int(data.get("task_count", len(task_rows)) or 0),
        "planned_scorecard_rows": len(scorecard_rows),
        "benchmark_ids": benchmark_ids,
        "dataset_lanes": dataset_lanes,
        "coverage_units": coverage_units,
        "provider_roles": provider_roles,
        "prompt_hashes": prompt_hashes,
    }


def _cross_harness_manifest_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    task_rows = data.get("task_rows") if isinstance(data.get("task_rows"), list) else []
    scorecard_rows = data.get("dry_scorecard_rows") if isinstance(data.get("dry_scorecard_rows"), list) else []
    prompt_hashes = sorted({
        str(row.get("raw_prompt_sha256", ""))
        for row in task_rows
        if isinstance(row, dict) and row.get("raw_prompt_sha256")
    })
    return {
        "artifact_path": path_text,
        "schema": data.get("schema", ""),
        "kind": "cross_harness_manifest",
        "task_count": int(data.get("task_count", len(task_rows)) or 0),
        "planned_scorecard_rows": len(scorecard_rows),
        "benchmark_ids": [str(item) for item in data.get("benchmark_ids", []) if item]
        if isinstance(data.get("benchmark_ids"), list)
        else [str(data.get("benchmark_id", ""))] if data.get("benchmark_id") else [],
        "dataset_lanes": [str(item) for item in data.get("dataset_lanes", []) if item]
        if isinstance(data.get("dataset_lanes"), list)
        else [],
        "coverage_units": [
            str(row.get("coverage_unit") or row.get("task_id") or "")
            for row in task_rows
            if isinstance(row, dict) and (row.get("coverage_unit") or row.get("task_id"))
        ],
        "provider_roles": [str(role) for role in data.get("provider_roles", []) if role]
        if isinstance(data.get("provider_roles"), list)
        else [],
        "prompt_hashes": prompt_hashes,
    }


def _schematic_drift_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    return {
        "artifact_path": path_text,
        "schema": data.get("schema", ""),
        "kind": "schematic_drift_check",
        "verdict": data.get("verdict", ""),
        "missing_nodes": int(summary.get("missing_nodes", 0) or 0),
        "missing_edges": int(summary.get("missing_edges", 0) or 0),
        "missing_files": int(summary.get("missing_files", 0) or 0),
        "stale_phrases": int(summary.get("stale_phrases", 0) or 0),
    }


def _forum_deep_verify_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    cases = data.get("cases") if isinstance(data.get("cases"), list) else []
    return {
        "artifact_path": path_text,
        "schema": data.get("schema", ""),
        "kind": "forum_deep_verify_benchmark",
        "case_metrics": [
            {
                "entry_count": int(row.get("entry_count", 0) or 0),
                "payload_body_bytes": int(row.get("payload_body_bytes", 0) or 0),
                "storage_mode": row.get("storage_mode", ""),
                "redaction_ratio": _safe_float(row.get("redaction_ratio")),
                "payloads_present": int(row.get("payloads_present", 0) or 0),
                "payloads_redacted": int(row.get("payloads_redacted", 0) or 0),
                "verify_chain_mean_ms": _safe_float(row.get("verify_chain", {}).get("mean_ms")),
                "verify_payloads_mean_ms": _safe_float(row.get("verify_payloads", {}).get("mean_ms")),
                "verify_deep_mean_ms": _safe_float(row.get("verify_deep", {}).get("mean_ms")),
            }
            for row in cases
            if isinstance(row, dict)
        ],
    }


def _embodied_realtime_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    rows = data.get("probe_rows") if isinstance(data.get("probe_rows"), list) else []
    dry_rows = data.get("dry_scorecard_rows") if isinstance(data.get("dry_scorecard_rows"), list) else []
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    return {
        "artifact_path": path_text,
        "schema": data.get("schema", ""),
        "kind": "embodied_realtime_multimodal_plan",
        "benchmark_id": data.get("benchmark_id", ""),
        "provider_roles": [str(role) for role in data.get("provider_roles", []) if role]
        if isinstance(data.get("provider_roles"), list)
        else [],
        "latency_budgets_ms": [int(value) for value in data.get("latency_budgets_ms", [])]
        if isinstance(data.get("latency_budgets_ms"), list)
        else [],
        "dataset_lanes": [str(lane) for lane in data.get("dataset_lanes", []) if lane]
        if isinstance(data.get("dataset_lanes"), list)
        else [],
        "pressure_variables": [str(variable) for variable in data.get("pressure_variables", []) if variable]
        if isinstance(data.get("pressure_variables"), list)
        else [],
        "model_leads_unverified": [str(item) for item in data.get("model_leads_unverified", []) if item]
        if isinstance(data.get("model_leads_unverified"), list)
        else [],
        "probe_metrics": [
            {
                "probe_id": row.get("probe_id", ""),
                "provider_role": row.get("provider_role", ""),
                "latency_budget_ms": int(row.get("latency_budget_ms", 0) or 0),
                "coverage_unit": row.get("coverage_unit", ""),
                "measurement_count": len(row.get("measurements", []) if isinstance(row.get("measurements"), list) else []),
            }
            for row in rows
            if isinstance(row, dict)
        ],
        "planned_scorecard_rows": len(dry_rows),
        "summary": {
            "probes": int(summary.get("probes", 0) or 0),
            "planned_probe_rows": int(summary.get("planned_probe_rows", len(rows)) or 0),
            "planned_scorecard_rows": int(summary.get("planned_scorecard_rows", len(dry_rows)) or 0),
            "execution_status": summary.get("execution_status", ""),
        },
    }


def _model_card_claim_table_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    rows = data.get("model_rows") if isinstance(data.get("model_rows"), list) else []
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    claim_metrics = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        fields = row.get("claim_fields") if isinstance(row.get("claim_fields"), list) else []
        statuses: dict[str, int] = {}
        for field in fields:
            if not isinstance(field, dict):
                continue
            status = str(field.get("status", ""))
            statuses[status] = statuses.get(status, 0) + 1
        claim_metrics.append({
            "model_id": row.get("model_id", ""),
            "overall_claim_status": row.get("overall_claim_status", ""),
            "primary_model_card_url": row.get("primary_model_card_url", ""),
            "claim_fields": len(fields),
            "status_counts": statuses,
        })
    return {
        "artifact_path": path_text,
        "schema": data.get("schema", ""),
        "kind": "model_card_claim_table",
        "source_label": data.get("source_label", ""),
        "claim_status_values": data.get("claim_status_values", []) if isinstance(data.get("claim_status_values"), list) else [],
        "required_claim_fields": data.get("required_claim_fields", []) if isinstance(data.get("required_claim_fields"), list) else [],
        "assumptions_to_verify_before_result_claims": data.get("assumptions_to_verify_before_result_claims", [])
        if isinstance(data.get("assumptions_to_verify_before_result_claims"), list)
        else [],
        "summary": summary,
        "claim_metrics": claim_metrics,
        "unresolved_fields": data.get("unresolved_fields", []) if isinstance(data.get("unresolved_fields"), list) else [],
    }


def _adapter_runtime_matrix_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    rows = data.get("runtime_rows") if isinstance(data.get("runtime_rows"), list) else []
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    return {
        "artifact_path": path_text,
        "schema": data.get("schema", ""),
        "kind": "adapter_runtime_matrix",
        "summary": summary,
        "runtime_metrics": [
            {
                "provider_role": row.get("provider_role", ""),
                "harness_id": row.get("harness_id", ""),
                "target_model": row.get("target_model", ""),
                "adapter_state": row.get("adapter_state", ""),
                "manifest_ready": bool(row.get("manifest_ready")),
                "focused_run_ready": bool(row.get("focused_run_ready")),
                "endpoint_profile_ready": bool(row.get("endpoint_profile_ready")),
                "endpoint_gate_ready": bool(row.get("endpoint_gate_ready")),
                "auth_ready": bool(row.get("auth_ready")),
                "blocking_gates": row.get("blocking_gates", []) if isinstance(row.get("blocking_gates"), list) else [],
            }
            for row in rows
            if isinstance(row, dict)
        ],
    }


def _forum_route_receipts_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    routes = data.get("routes") if isinstance(data.get("routes"), list) else []
    return {
        "path": path_text,
        "schema": data.get("schema", ""),
        "kind": "forum_route_receipts",
        "summary": data.get("summary", {}) if isinstance(data.get("summary"), dict) else {},
        "route_metrics": [
            {
                "route_id": row.get("route_id", ""),
                "observation_status": row.get("observation_status", ""),
                "observed": bool(row.get("observed")),
                "observed_decided": row.get("observed_decided", ""),
                "observed_confidence": _safe_float(row.get("observed_confidence"))
                if row.get("observed_confidence") is not None else None,
                "observed_needs_escalation": row.get("observed_needs_escalation"),
                "observed_domain": row.get("observed_domain", ""),
                "observed_intent": row.get("observed_intent", ""),
                "observed_posture": row.get("observed_posture", ""),
                "observed_proof_lane": row.get("observed_proof_lane", ""),
                "observed_domain_lane": row.get("observed_domain_lane", ""),
                "provider_execution_observed": bool(row.get("provider_execution_observed")),
                "endpoint_probe_observed": bool(row.get("endpoint_probe_observed")),
            }
            for row in routes
            if isinstance(row, dict)
        ],
    }


def _mcp_tool_health_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    tools = data.get("tools") if isinstance(data.get("tools"), list) else []
    return {
        "path": path_text,
        "schema": data.get("schema", ""),
        "kind": "mcp_tool_health",
        "summary": data.get("summary", {}) if isinstance(data.get("summary"), dict) else {},
        "tool_health_metrics": [
            {
                "tool": row.get("tool", ""),
                "role": row.get("role", ""),
                "root_exists": bool(row.get("root_exists")),
                "observed": bool(row.get("observed")),
                "observed_status": row.get("observed_status", ""),
                "observed_error_code": row.get("observed_error_code", ""),
                "verdict": row.get("verdict", ""),
                "provider_execution_observed": bool(row.get("provider_execution_observed")),
                "endpoint_probe_observed": bool(row.get("endpoint_probe_observed")),
            }
            for row in tools
            if isinstance(row, dict)
        ],
    }


def _harness_comparison_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    comparisons = data.get("comparisons") if isinstance(data.get("comparisons"), list) else []
    return {
        "artifact_path": path_text,
        "schema": data.get("schema", ""),
        "kind": "harness_comparison_report",
        "conclusion": data.get("conclusion", {}),
        "summary": summary,
        "comparison_metrics": [
            {
                "benchmark_id": row.get("benchmark_id", ""),
                "comparison_key": row.get("comparison_key", ""),
                "available": bool(row.get("available")),
                "pass_rate_delta_flywheel_minus_codex": _safe_float(row.get("pass_rate_delta_flywheel_minus_codex")),
                "quality_delta_flywheel_minus_codex": _safe_float(row.get("quality_delta_flywheel_minus_codex")),
                "latency_delta_ms_flywheel_minus_codex": _safe_float(row.get("latency_delta_ms_flywheel_minus_codex")),
                "winner_by_quality": row.get("winner_by_quality", ""),
            }
            for row in comparisons
            if isinstance(row, dict)
        ],
    }


def _generic_child_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    schema = str(data.get("schema", ""))
    if schema == "harness.executable-manifest/v1":
        return _executable_manifest_summary(data, path_text)
    if schema == "harness.command-registry-html/v1":
        return _command_registry_summary(data, path_text)
    if schema == "harness.benchmark-profile-manifest/v1":
        return _benchmark_profile_summary(data, path_text)
    if schema == "harness.benchmark-execution-matrix/v1":
        return _benchmark_execution_matrix_summary(data, path_text)
    if schema == "harness.benchmark-profile-coverage/v1":
        return _benchmark_coverage_summary(data, path_text)
    if schema == "harness.agentic-task-manifest/v1":
        return _agentic_task_manifest_summary(data, path_text)
    if schema == "harness.cross-harness-manifest/v1":
        return _cross_harness_manifest_summary(data, path_text)
    if schema == "harness.schematic-drift-check/v1":
        return _schematic_drift_summary(data, path_text)
    if schema == "forum.deep-verify-benchmark/v1":
        return _forum_deep_verify_summary(data, path_text)
    if schema == "harness.embodied-realtime-multimodal/v1":
        return _embodied_realtime_summary(data, path_text)
    if schema == "harness.model-card-claim-table/v1":
        return _model_card_claim_table_summary(data, path_text)
    if schema == "harness.adapter-runtime-matrix/v1":
        return _adapter_runtime_matrix_summary(data, path_text)
    if schema == "harness.forum-route-receipts/v1":
        return _forum_route_receipts_summary(data, path_text)
    if schema == "harness.mcp-tool-health/v1":
        return _mcp_tool_health_summary(data, path_text)
    if schema == "harness.comparison-report/v1":
        return _harness_comparison_summary(data, path_text)
    if schema == "harness.context-inventory/v1":
        return _context_inventory_summary(data, path_text)
    if schema == "harness.tool-readiness/v1":
        return _tool_readiness_summary(data, path_text)
    if schema == "harness.tool-hardening-plan/v1":
        return _tool_hardening_summary(data, path_text)
    if schema == "harness.model-endpoint-profiles/v1":
        return _model_endpoint_summary(data, path_text)
    if schema == "harness.model-endpoint-gate/v1":
        return _model_endpoint_gate_summary(data, path_text)
    if schema == "harness.model-release-readiness/v1":
        return _model_release_summary(data, path_text)
    if schema == "harness.model-publish-plan/v1":
        return _model_publish_plan_summary(data, path_text)
    if schema == "harness.gather-readiness/v1":
        return _gather_readiness_summary(data, path_text)
    if schema == "m7-source-mined-scorecard/v1":
        return _source_mined_summary(data, path_text)
    if schema == "m7-governed-agent-scorecard/v1":
        return _governed_summary(data, path_text)
    if schema == "unisonai.stateful-provider-matrix/v1":
        return _unisonai_summary(data, path_text)
    if schema == "classifier-friction-benchmark/v1":
        return _classifier_friction_summary(data, path_text)
    return {
        "artifact_path": path_text,
        "schema": schema,
        "kind": "unclassified_json_artifact",
    }


def extract_child_artifact_summaries(report: dict[str, Any]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in _step_rows(report):
        artifacts = row.get("expected_artifacts", [])
        if not isinstance(artifacts, list):
            continue
        for path_text in artifacts:
            path_text = str(path_text)
            if path_text in seen:
                continue
            seen.add(path_text)
            data, error = _read_child_json(path_text)
            if data is None:
                summaries.append({
                    "artifact_path": path_text,
                    "schema": "",
                    "kind": "unloaded_artifact",
                    "load_error": error,
                })
                continue
            summaries.append(_generic_child_summary(data, path_text))
    return summaries


def benchmark_signal_summary(child_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    scorecards = [
        item
        for item in child_summaries
        if item.get("kind") in {
            "m7_source_mined",
            "m7_governed_agent",
            "unisonai_stateful_provider_matrix",
            "classifier_friction_accountability",
        }
    ]
    providers = sorted({
        str(metric.get("provider", ""))
        for item in scorecards
        for metric in item.get("provider_metrics", [])
        if metric.get("provider")
    })
    return {
        "scorecard_count": len(scorecards),
        "providers_observed": providers,
        "comparisons": [
            {
                "kind": item.get("kind", ""),
                "comparison": item.get("comparison", {}),
            }
            for item in scorecards
            if item.get("comparison")
        ],
        "classifier_modes_observed": sorted({
            str(metric.get("mode", ""))
            for item in scorecards
            if item.get("kind") == "classifier_friction_accountability"
            for metric in item.get("provider_metrics", [])
            if metric.get("mode")
        }),
        "classifier_delta_count": sum(
            len(item.get("comparison", {}).get("deltas", []))
            for item in scorecards
            if item.get("kind") == "classifier_friction_accountability"
            and isinstance(item.get("comparison"), dict)
        ),
    }


def comparison_report_signal_summary(child_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    reports = [
        item
        for item in child_summaries
        if item.get("kind") == "harness_comparison_report"
    ]
    comparisons = [
        metric
        for item in reports
        for metric in item.get("comparison_metrics", [])
    ]
    verdict_counts: dict[str, int] = {}
    for item in reports:
        conclusion_obj = item.get("conclusion") if isinstance(item.get("conclusion"), dict) else {}
        verdict = str(conclusion_obj.get("verdict", ""))
        if verdict:
            verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
    return {
        "comparison_artifacts": len(reports),
        "comparison_keys": len(comparisons),
        "available_comparisons": sum(1 for row in comparisons if row.get("available")),
        "flywheel_quality_wins": sum(1 for row in comparisons if row.get("winner_by_quality") == "flywheel"),
        "codex_quality_wins": sum(1 for row in comparisons if row.get("winner_by_quality") == "codex"),
        "quality_ties": sum(1 for row in comparisons if row.get("winner_by_quality") == "tie"),
        "verdict_counts": verdict_counts,
        "comparison_keys_observed": [str(row.get("comparison_key", "")) for row in comparisons if row.get("comparison_key")],
    }


def context_signal_summary(child_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    inventories = [
        item
        for item in child_summaries
        if item.get("kind") == "context_inventory"
    ]
    label_counts: dict[str, int] = {}
    for item in inventories:
        summary = item.get("summary") if isinstance(item.get("summary"), dict) else {}
        for label, count in (summary.get("label_counts") or {}).items():
            label_counts[str(label)] = label_counts.get(str(label), 0) + int(count or 0)
    return {
        "inventory_count": len(inventories),
        "entries": sum(int(item.get("summary", {}).get("entries", 0) or 0) for item in inventories),
        "existing_roots": sum(int(item.get("summary", {}).get("existing_roots", 0) or 0) for item in inventories),
        "sensitive_name_entries": sum(
            int(item.get("summary", {}).get("sensitive_name_entries", 0) or 0)
            for item in inventories
        ),
        "label_counts": label_counts,
    }


def tool_readiness_signal_summary(child_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    readiness = [
        item
        for item in child_summaries
        if item.get("kind") == "tool_readiness"
    ]
    verdict_counts: dict[str, int] = {}
    for item in readiness:
        for metric in item.get("tool_metrics", []):
            verdict = str(metric.get("verdict", ""))
            verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
    tools = [
        metric
        for item in readiness
        for metric in item.get("tool_metrics", [])
    ]
    return {
        "readiness_artifacts": len(readiness),
        "tools": len(tools),
        "enterprise_ready_tools": sum(1 for metric in tools if metric.get("enterprise_ready")),
        "existing_tools": sum(1 for metric in tools if metric.get("root_exists")),
        "mean_score": round(sum(_safe_float(metric.get("score")) for metric in tools) / len(tools), 4) if tools else 0.0,
        "verdict_counts": verdict_counts,
        "tools_observed": [str(metric.get("tool", "")) for metric in tools if metric.get("tool")],
    }


def tool_hardening_signal_summary(child_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    plans = [
        item
        for item in child_summaries
        if item.get("kind") == "tool_hardening_plan"
    ]
    actions = [
        action
        for item in plans
        for action in item.get("action_metrics", [])
    ]
    gates = [
        gate
        for item in plans
        for gate in item.get("release_gate_metrics", [])
    ]
    priority_counts: dict[str, int] = {}
    owner_counts: dict[str, int] = {}
    for action in actions:
        priority = str(action.get("priority", ""))
        owner = str(action.get("owner", ""))
        priority_counts[priority] = priority_counts.get(priority, 0) + 1
        owner_counts[owner] = owner_counts.get(owner, 0) + 1
    return {
        "plan_artifacts": len(plans),
        "actions": len(actions),
        "release_gates": len(gates),
        "passed_release_gates": sum(1 for gate in gates if gate.get("passed")),
        "priority_counts": priority_counts,
        "owner_counts": owner_counts,
        "tools_observed": sorted({str(action.get("tool", "")) for action in actions if action.get("tool")}),
    }


def model_release_signal_summary(child_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    releases = [
        item
        for item in child_summaries
        if item.get("kind") == "model_release_readiness"
    ]
    verdict_counts: dict[str, int] = {}
    models = [
        metric
        for item in releases
        for metric in item.get("model_metrics", [])
    ]
    for metric in models:
        verdict = str(metric.get("verdict", ""))
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
    return {
        "release_artifacts": len(releases),
        "models": len(models),
        "models_observed": [str(metric.get("model", "")) for metric in models if metric.get("model")],
        "existing_models": sum(1 for metric in models if metric.get("root_exists")),
        "models_with_weights": sum(1 for metric in models if int(metric.get("weight_file_count", 0) or 0) > 0),
        "release_ready_models": sum(1 for metric in models if metric.get("enterprise_release_ready")),
        "endpoint_profile_matches": sum(int(metric.get("endpoint_profile_count", 0) or 0) for metric in models),
        "endpoint_gate_rows": sum(int(metric.get("endpoint_gate_row_count", 0) or 0) for metric in models),
        "endpoint_gate_generation_ok": sum(int(metric.get("endpoint_gate_generation_ok_count", 0) or 0) for metric in models),
        "benchmark_artifact_matches": sum(int(metric.get("benchmark_artifact_count", 0) or 0) for metric in models),
        "mean_release_doc_score": round(sum(_safe_float(metric.get("release_doc_score")) for metric in models) / len(models), 4) if models else 0.0,
        "verdict_counts": verdict_counts,
    }


def model_publish_signal_summary(child_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    plans = [
        item
        for item in child_summaries
        if item.get("kind") == "model_publish_plan"
    ]
    models = [
        metric
        for item in plans
        for metric in item.get("model_publish_metrics", [])
    ]
    return {
        "publish_plan_artifacts": len(plans),
        "models": len(models),
        "candidate_names": [str(metric.get("candidate_name", "")) for metric in models if metric.get("candidate_name")],
        "ready_to_stage_models": sum(1 for metric in models if metric.get("publish_status") == "READY_TO_STAGE"),
        "do_not_publish_models": sum(1 for metric in models if metric.get("publish_status") == "DO_NOT_PUBLISH"),
        "actions": sum(int(metric.get("actions", 0) or 0) for metric in models),
        "blockers": sum(int(metric.get("blockers", 0) or 0) for metric in models),
    }


def model_endpoint_signal_summary(child_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    artifacts = [
        item
        for item in child_summaries
        if item.get("kind") == "model_endpoint_profiles"
    ]
    profiles = [
        metric
        for item in artifacts
        for metric in item.get("endpoint_metrics", [])
    ]
    backends = sorted({str(metric.get("backend", "")) for metric in profiles if metric.get("backend")})
    provider_roles = sorted({str(metric.get("provider_role", "")) for metric in profiles if metric.get("provider_role")})
    gates = [
        metric
        for item in child_summaries
        if item.get("kind") == "model_endpoint_gate"
        for metric in item.get("endpoint_gate_metrics", [])
    ]
    return {
        "endpoint_artifacts": len(artifacts),
        "profiles": len(profiles),
        "models_observed": sorted({str(metric.get("model", "")) for metric in profiles if metric.get("model")}),
        "backends_observed": backends,
        "provider_roles_observed": provider_roles,
        "existing_roots": sum(1 for metric in profiles if metric.get("root_exists")),
        "agentic_profiles": sum(1 for metric in profiles if metric.get("supports_agentic_workflow")),
        "live_probed_profiles": sum(1 for metric in profiles if metric.get("live_probed")),
        "gate_rows": len(gates),
        "gate_health_ok_rows": sum(1 for metric in gates if metric.get("health_ok")),
        "gate_generation_ok_rows": sum(1 for metric in gates if metric.get("generation_ok")),
        "gate_failed_rows": sum(1 for metric in gates if metric.get("failure_class")),
    }


def gather_readiness_signal_summary(child_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [
        item.get("gather_metrics", {})
        for item in child_summaries
        if item.get("kind") == "gather_readiness"
    ]
    verdict_counts: dict[str, int] = {}
    for row in rows:
        verdict = str(row.get("verdict", ""))
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
    return {
        "readiness_artifacts": len(rows),
        "root_exists_count": sum(1 for row in rows if row.get("root_exists")),
        "config_count": sum(int(row.get("config_count", 0) or 0) for row in rows),
        "credential_present_count": sum(1 for row in rows if row.get("credential_present")),
        "mean_core_score": round(sum(_safe_float(row.get("core_score")) for row in rows) / len(rows), 4) if rows else 0.0,
        "mean_discord_score": round(sum(_safe_float(row.get("discord_score")) for row in rows) / len(rows), 4) if rows else 0.0,
        "verdict_counts": verdict_counts,
    }


def executable_manifest_signal_summary(child_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    manifests = [
        item
        for item in child_summaries
        if item.get("kind") == "harness_executable_manifest"
    ]
    commands = [
        metric
        for item in manifests
        for metric in item.get("command_metrics", [])
    ]
    schemas = sorted({
        str(schema)
        for metric in commands
        for schema in metric.get("schemas", [])
        if schema
    })
    return {
        "manifest_artifacts": len(manifests),
        "commands": len(commands),
        "command_names": [str(metric.get("name", "")) for metric in commands if metric.get("name")],
        "schema_count": len(schemas),
        "schemas": schemas,
        "target_count": sum(int(metric.get("target_count", 0) or 0) for metric in commands),
    }


def command_registry_signal_summary(child_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    registries = [
        item
        for item in child_summaries
        if item.get("kind") == "harness_command_registry"
    ]
    command_names = sorted({
        str(name)
        for item in registries
        for name in item.get("command_names", [])
        if name
    })
    risk_counts: dict[str, int] = {}
    html_paths = []
    schemas = set()
    for item in registries:
        if item.get("html_path"):
            html_paths.append(str(item.get("html_path")))
        for risk, count in (item.get("risk_counts") or {}).items():
            risk_counts[str(risk)] = risk_counts.get(str(risk), 0) + int(count or 0)
        for schema in item.get("schemas", []):
            if schema:
                schemas.add(str(schema))
    return {
        "registry_artifacts": len(registries),
        "commands": sum(int(item.get("command_count", 0) or 0) for item in registries),
        "command_names": command_names,
        "risk_counts": risk_counts,
        "schema_count": len(schemas),
        "html_paths": html_paths,
    }


def benchmark_profile_signal_summary(child_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    profiles = [
        item
        for item in child_summaries
        if item.get("kind") == "benchmark_profile_manifest"
    ]
    providers = sorted({
        str(provider)
        for item in profiles
        for provider in item.get("providers", [])
        if provider
    })
    metrics = sorted({
        str(metric)
        for item in profiles
        for metric in item.get("metrics", [])
        if metric
    })
    benchmark_ids = sorted({
        str(metric.get("id", ""))
        for item in profiles
        for metric in item.get("benchmark_metrics", [])
        if metric.get("id")
    })
    dataset_lanes = sorted({
        str(lane)
        for item in profiles
        for lane in item.get("dataset_lanes", [])
        if lane
    })
    pressure_variables = sorted({
        str(variable)
        for item in profiles
        for variable in item.get("pressure_variables", [])
        if variable
    })
    return {
        "profile_artifacts": len(profiles),
        "providers": providers,
        "metrics": metrics,
        "benchmarks": sum(int(item.get("summary", {}).get("benchmarks", 0) or 0) for item in profiles),
        "runnable_benchmarks": sum(int(item.get("summary", {}).get("runnable_benchmarks", 0) or 0) for item in profiles),
        "planned_full_benchmarks": sum(int(item.get("summary", {}).get("planned_full_benchmarks", 0) or 0) for item in profiles),
        "coverage_units": sum(int(item.get("summary", {}).get("coverage_units", 0) or 0) for item in profiles),
        "existing_artifacts": sum(int(item.get("summary", {}).get("existing_artifacts", 0) or 0) for item in profiles),
        "benchmark_ids": benchmark_ids,
        "weight_sums": [item.get("metric_weight_sum", 0.0) for item in profiles],
        "dataset_lanes": dataset_lanes,
        "pressure_variables": pressure_variables,
        "dataset_lane_weight_sums": [item.get("dataset_lane_weight_sum", 0.0) for item in profiles],
    }


def benchmark_execution_matrix_signal_summary(child_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    matrices = [
        item
        for item in child_summaries
        if item.get("kind") == "benchmark_execution_matrix"
    ]
    providers = sorted({
        str(provider)
        for item in matrices
        for provider in item.get("providers", [])
        if provider
    })
    provider_roles = sorted({
        str(role)
        for item in matrices
        for role in item.get("expected_provider_roles", [])
        if role
    })
    step_ids = sorted({
        str(row.get("step_id", ""))
        for item in matrices
        for row in item.get("step_metrics", [])
        if row.get("step_id")
    })
    long_running_step_ids = sorted({
        str(row.get("step_id", ""))
        for item in matrices
        for row in item.get("step_metrics", [])
        if row.get("step_id") and row.get("long_running")
    })
    approval_step_ids = sorted({
        str(row.get("step_id", ""))
        for item in matrices
        for row in item.get("step_metrics", [])
        if row.get("step_id") and row.get("operator_approval_required")
    })
    expected_schemas = sorted({
        str(schema)
        for item in matrices
        for schema in item.get("summary", {}).get("expected_schemas", [])
        if schema
    } | {
        str(schema)
        for item in matrices
        for row in item.get("step_metrics", [])
        for schema in row.get("expected_schemas", [])
        if schema
    })
    evidence_gates = sorted({
        str(gate)
        for item in matrices
        for gate in item.get("summary", {}).get("evidence_gates", [])
        if gate
    } | {
        str(gate)
        for item in matrices
        for row in item.get("step_metrics", [])
        for gate in row.get("evidence_gates", [])
        if gate
    })
    tier_step_counts: dict[str, int] = {}
    tier_long_running_counts: dict[str, int] = {}
    for item in matrices:
        for row in item.get("tier_metrics", []):
            tier = str(row.get("tier", ""))
            if not tier:
                continue
            tier_step_counts[tier] = tier_step_counts.get(tier, 0) + int(row.get("step_count", 0) or 0)
            tier_long_running_counts[tier] = tier_long_running_counts.get(tier, 0) + int(row.get("long_running_steps", 0) or 0)
    return {
        "matrix_artifacts": len(matrices),
        "providers": providers,
        "expected_provider_roles": provider_roles,
        "steps": sum(int(item.get("summary", {}).get("steps", 0) or 0) for item in matrices),
        "dry_steps": sum(int(item.get("summary", {}).get("dry_steps", 0) or 0) for item in matrices),
        "focused_steps": sum(int(item.get("summary", {}).get("focused_steps", 0) or 0) for item in matrices),
        "full_steps": sum(int(item.get("summary", {}).get("full_steps", 0) or 0) for item in matrices),
        "long_running_steps": sum(int(item.get("summary", {}).get("long_running_steps", 0) or 0) for item in matrices),
        "operator_approval_required_steps": sum(int(item.get("summary", {}).get("operator_approval_required_steps", 0) or 0) for item in matrices),
        "step_ids": step_ids,
        "long_running_step_ids": long_running_step_ids,
        "operator_approval_required_step_ids": approval_step_ids,
        "expected_schemas": expected_schemas,
        "evidence_gates": evidence_gates,
        "tier_step_counts": dict(sorted(tier_step_counts.items())),
        "tier_long_running_counts": dict(sorted(tier_long_running_counts.items())),
    }


def benchmark_coverage_signal_summary(child_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [
        item
        for item in child_summaries
        if item.get("kind") == "benchmark_profile_coverage"
    ]
    verdict_counts: dict[str, int] = {}
    missing_benchmarks = set()
    missing_providers = set()
    missing_units: dict[str, set[str]] = {}
    observed_units: dict[str, set[str]] = {}
    incomplete_units: dict[str, dict[str, set[str]]] = {}
    invalid_units: dict[str, dict[str, set[str]]] = {}
    missing_provider_units: dict[str, dict[str, set[str]]] = {}
    invalid_provider_units: dict[str, dict[str, dict[str, set[str]]]] = {}
    observed_benchmarks = set()
    observed_providers = set()
    raw_expected_providers = set()
    declared_dataset_lanes = set()
    observed_dataset_lanes = set()
    missing_dataset_lanes = set()
    declared_pressure_variables = set()
    observed_pressure_variables = set()
    missing_pressure_variables = set()
    provider_aliases: dict[str, str] = {}
    for row in rows:
        verdict = str(row.get("verdict", ""))
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
        missing_benchmarks.update(str(item) for item in row.get("missing_runnable_benchmark_ids", []) if item)
        missing_providers.update(str(item) for item in row.get("missing_providers", []) if item)
        raw_expected_providers.update(str(item) for item in row.get("raw_expected_providers", []) if item)
        declared_dataset_lanes.update(str(item) for item in row.get("declared_dataset_lanes", []) if item)
        observed_dataset_lanes.update(str(item) for item in row.get("observed_dataset_lanes", []) if item)
        missing_dataset_lanes.update(str(item) for item in row.get("missing_dataset_lanes", []) if item)
        declared_pressure_variables.update(str(item) for item in row.get("declared_pressure_variables", []) if item)
        observed_pressure_variables.update(str(item) for item in row.get("observed_pressure_variables", []) if item)
        missing_pressure_variables.update(str(item) for item in row.get("missing_pressure_variables", []) if item)
        provider_aliases.update({str(key): str(value) for key, value in (row.get("provider_aliases") or {}).items()})
        observed_benchmarks.update(str(item) for item in row.get("observed_benchmark_ids", []) if item)
        observed_providers.update(str(item) for item in row.get("observed_providers", []) if item)
        for benchmark_id, units in (row.get("missing_units_by_benchmark") or {}).items():
            missing_units.setdefault(str(benchmark_id), set()).update(str(unit) for unit in units if unit)
        for benchmark_id, units in (row.get("observed_units_by_benchmark") or {}).items():
            observed_units.setdefault(str(benchmark_id), set()).update(str(unit) for unit in units if unit)
        for benchmark_id, units in (row.get("incomplete_units_by_benchmark") or {}).items():
            target = incomplete_units.setdefault(str(benchmark_id), {})
            for unit_id, missing in units.items():
                target.setdefault(str(unit_id), set()).update(str(item) for item in missing if item)
        for benchmark_id, units in (row.get("invalid_units_by_benchmark") or {}).items():
            target = invalid_units.setdefault(str(benchmark_id), {})
            for unit_id, invalid in units.items():
                target.setdefault(str(unit_id), set()).update(str(item) for item in invalid if item)
        for benchmark_id, providers in (row.get("missing_provider_units_by_benchmark") or {}).items():
            target = missing_provider_units.setdefault(str(benchmark_id), {})
            for provider, units in providers.items():
                target.setdefault(str(provider), set()).update(str(unit) for unit in units if unit)
        for benchmark_id, providers in (row.get("invalid_provider_units_by_benchmark") or {}).items():
            target = invalid_provider_units.setdefault(str(benchmark_id), {})
            for provider, units in providers.items():
                provider_target = target.setdefault(str(provider), {})
                for unit_id, invalid in units.items():
                    provider_target.setdefault(str(unit_id), set()).update(str(item) for item in invalid if item)
    return {
        "coverage_artifacts": len(rows),
        "mean_benchmark_coverage_rate": round(sum(_safe_float(row.get("benchmark_coverage_rate")) for row in rows) / len(rows), 4) if rows else 0.0,
        "mean_unit_coverage_rate": round(sum(_safe_float(row.get("unit_coverage_rate")) for row in rows) / len(rows), 4) if rows else 0.0,
        "mean_unit_metric_completeness_rate": round(sum(_safe_float(row.get("unit_metric_completeness_rate")) for row in rows) / len(rows), 4) if rows else 0.0,
        "mean_unit_metric_validity_rate": round(sum(_safe_float(row.get("unit_metric_validity_rate")) for row in rows) / len(rows), 4) if rows else 0.0,
        "mean_provider_coverage_rate": round(sum(_safe_float(row.get("provider_coverage_rate")) for row in rows) / len(rows), 4) if rows else 0.0,
        "mean_provider_unit_coverage_rate": round(sum(_safe_float(row.get("provider_unit_coverage_rate")) for row in rows) / len(rows), 4) if rows else 0.0,
        "mean_provider_unit_validity_rate": round(sum(_safe_float(row.get("provider_unit_validity_rate")) for row in rows) / len(rows), 4) if rows else 0.0,
        "mean_dataset_lane_coverage_rate": round(sum(_safe_float(row.get("dataset_lane_coverage_rate")) for row in rows) / len(rows), 4) if rows else 0.0,
        "mean_pressure_variable_coverage_rate": round(sum(_safe_float(row.get("pressure_variable_coverage_rate")) for row in rows) / len(rows), 4) if rows else 0.0,
        "missing_runnable_benchmark_ids": sorted(missing_benchmarks),
        "missing_providers": sorted(missing_providers),
        "raw_expected_providers": sorted(raw_expected_providers),
        "declared_dataset_lanes": sorted(declared_dataset_lanes),
        "observed_dataset_lanes": sorted(observed_dataset_lanes),
        "missing_dataset_lanes": sorted(missing_dataset_lanes),
        "declared_pressure_variables": sorted(declared_pressure_variables),
        "observed_pressure_variables": sorted(observed_pressure_variables),
        "missing_pressure_variables": sorted(missing_pressure_variables),
        "provider_aliases": dict(sorted(provider_aliases.items())),
        "missing_units_by_benchmark": {key: sorted(value) for key, value in sorted(missing_units.items())},
        "observed_units_by_benchmark": {key: sorted(value) for key, value in sorted(observed_units.items())},
        "incomplete_units_by_benchmark": {
            key: {unit_id: sorted(missing) for unit_id, missing in sorted(value.items())}
            for key, value in sorted(incomplete_units.items())
        },
        "invalid_units_by_benchmark": {
            key: {unit_id: sorted(invalid) for unit_id, invalid in sorted(value.items())}
            for key, value in sorted(invalid_units.items())
        },
        "missing_provider_units_by_benchmark": {
            key: {provider: sorted(units) for provider, units in sorted(value.items())}
            for key, value in sorted(missing_provider_units.items())
        },
        "invalid_provider_units_by_benchmark": {
            key: {
                provider: {unit_id: sorted(invalid) for unit_id, invalid in sorted(units.items())}
                for provider, units in sorted(value.items())
            }
            for key, value in sorted(invalid_provider_units.items())
        },
        "observed_benchmark_ids": sorted(observed_benchmarks),
        "observed_providers": sorted(observed_providers),
        "load_errors": sum(int(row.get("load_errors", 0) or 0) for row in rows),
        "verdict_counts": verdict_counts,
    }


def agentic_task_manifest_signal_summary(child_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    manifests = [
        item
        for item in child_summaries
        if item.get("kind") == "agentic_task_manifest"
    ]
    benchmark_ids = sorted({
        str(benchmark_id)
        for item in manifests
        for benchmark_id in item.get("benchmark_ids", [])
        if benchmark_id
    })
    dataset_lanes = sorted({
        str(lane)
        for item in manifests
        for lane in item.get("dataset_lanes", [])
        if lane
    })
    coverage_units = sorted({
        str(unit)
        for item in manifests
        for unit in item.get("coverage_units", [])
        if unit
    })
    provider_roles = sorted({
        str(role)
        for item in manifests
        for role in item.get("provider_roles", [])
        if role
    })
    prompt_hashes = sorted({
        str(prompt_hash)
        for item in manifests
        for prompt_hash in item.get("prompt_hashes", [])
        if prompt_hash
    })
    return {
        "manifest_artifacts": len(manifests),
        "task_count": sum(int(item.get("task_count", 0) or 0) for item in manifests),
        "planned_scorecard_rows": sum(int(item.get("planned_scorecard_rows", 0) or 0) for item in manifests),
        "benchmark_ids": benchmark_ids,
        "dataset_lanes": dataset_lanes,
        "coverage_units": coverage_units,
        "provider_roles": provider_roles,
        "prompt_hashes": prompt_hashes,
    }


def cross_harness_manifest_signal_summary(child_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    manifests = [
        item
        for item in child_summaries
        if item.get("kind") == "cross_harness_manifest"
    ]
    benchmark_ids = sorted({
        str(benchmark_id)
        for item in manifests
        for benchmark_id in item.get("benchmark_ids", [])
        if benchmark_id
    })
    provider_roles = sorted({
        str(role)
        for item in manifests
        for role in item.get("provider_roles", [])
        if role
    })
    prompt_hashes = sorted({
        str(prompt_hash)
        for item in manifests
        for prompt_hash in item.get("prompt_hashes", [])
        if prompt_hash
    })
    return {
        "manifest_artifacts": len(manifests),
        "task_count": sum(int(item.get("task_count", 0) or 0) for item in manifests),
        "planned_scorecard_rows": sum(int(item.get("planned_scorecard_rows", 0) or 0) for item in manifests),
        "benchmark_ids": benchmark_ids,
        "provider_roles": provider_roles,
        "prompt_hashes": prompt_hashes,
    }


def schematic_drift_signal_summary(child_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    reports = [
        item
        for item in child_summaries
        if item.get("kind") == "schematic_drift_check"
    ]
    return {
        "drift_artifacts": len(reports),
        "verdicts": sorted({str(item.get("verdict", "")) for item in reports if item.get("verdict")}),
        "missing_nodes": sum(int(item.get("missing_nodes", 0) or 0) for item in reports),
        "missing_edges": sum(int(item.get("missing_edges", 0) or 0) for item in reports),
        "missing_files": sum(int(item.get("missing_files", 0) or 0) for item in reports),
        "stale_phrases": sum(int(item.get("stale_phrases", 0) or 0) for item in reports),
    }


def forum_deep_verify_signal_summary(child_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    artifacts = [
        item
        for item in child_summaries
        if item.get("kind") == "forum_deep_verify_benchmark"
    ]
    cases = [
        metric
        for item in artifacts
        for metric in item.get("case_metrics", [])
    ]
    deep_samples = [_safe_float(row.get("verify_deep_mean_ms")) for row in cases]
    return {
        "benchmark_artifacts": len(artifacts),
        "case_count": len(cases),
        "max_entry_count": max([int(row.get("entry_count", 0) or 0) for row in cases], default=0),
        "max_payload_body_bytes": max([int(row.get("payload_body_bytes", 0) or 0) for row in cases], default=0),
        "storage_modes": sorted({str(row.get("storage_mode", "")) for row in cases if row.get("storage_mode")}),
        "redaction_ratios": sorted({_safe_float(row.get("redaction_ratio")) for row in cases}),
        "payloads_present": sum(int(row.get("payloads_present", 0) or 0) for row in cases),
        "payloads_redacted": sum(int(row.get("payloads_redacted", 0) or 0) for row in cases),
        "mean_verify_deep_ms": round(sum(deep_samples) / len(deep_samples), 4) if deep_samples else 0.0,
        "max_verify_deep_ms": max(deep_samples, default=0.0),
    }


def embodied_realtime_signal_summary(child_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    artifacts = [
        item
        for item in child_summaries
        if item.get("kind") == "embodied_realtime_multimodal_plan"
    ]
    probes = [
        metric
        for item in artifacts
        for metric in item.get("probe_metrics", [])
    ]
    return {
        "plan_artifacts": len(artifacts),
        "planned_probe_rows": sum(int(item.get("summary", {}).get("planned_probe_rows", 0) or 0) for item in artifacts),
        "planned_scorecard_rows": sum(int(item.get("summary", {}).get("planned_scorecard_rows", 0) or 0) for item in artifacts),
        "provider_roles": sorted({
            str(role)
            for item in artifacts
            for role in item.get("provider_roles", [])
            if role
        }),
        "latency_budgets_ms": sorted({
            int(value)
            for item in artifacts
            for value in item.get("latency_budgets_ms", [])
        }),
        "dataset_lanes": sorted({
            str(lane)
            for item in artifacts
            for lane in item.get("dataset_lanes", [])
            if lane
        }),
        "pressure_variables": sorted({
            str(variable)
            for item in artifacts
            for variable in item.get("pressure_variables", [])
            if variable
        }),
        "probe_ids": sorted({str(row.get("probe_id", "")) for row in probes if row.get("probe_id")}),
        "coverage_units": sorted({str(row.get("coverage_unit", "")) for row in probes if row.get("coverage_unit")}),
        "model_leads_unverified": sorted({
            str(item)
            for artifact in artifacts
            for item in artifact.get("model_leads_unverified", [])
            if item
        }),
    }


def model_card_claim_signal_summary(child_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    artifacts = [
        item
        for item in child_summaries
        if item.get("kind") == "model_card_claim_table"
    ]
    metrics = [
        metric
        for item in artifacts
        for metric in item.get("claim_metrics", [])
    ]
    status_counts: dict[str, int] = {}
    for metric in metrics:
        for status, count in (metric.get("status_counts") or {}).items():
            status_counts[str(status)] = status_counts.get(str(status), 0) + int(count or 0)
    unresolved = [
        field
        for item in artifacts
        for field in item.get("unresolved_fields", [])
        if isinstance(field, dict)
    ]
    return {
        "claim_table_artifacts": len(artifacts),
        "model_candidates": sum(int(item.get("summary", {}).get("model_candidates", 0) or 0) for item in artifacts),
        "claim_fields": sum(int(item.get("summary", {}).get("claim_fields", 0) or 0) for item in artifacts),
        "unresolved_fields": sum(int(item.get("summary", {}).get("unresolved_fields", 0) or 0) for item in artifacts),
        "verified_primary_source_fields": sum(
            int(item.get("summary", {}).get("verified_primary_source_fields", 0) or 0)
            for item in artifacts
        ),
        "verified_secondary_source_fields": sum(
            int(item.get("summary", {}).get("verified_secondary_source_fields", 0) or 0)
            for item in artifacts
        ),
        "not_checked_fields": sum(int(item.get("summary", {}).get("not_checked_fields", 0) or 0) for item in artifacts),
        "operator_relayed_unverified_fields": sum(
            int(item.get("summary", {}).get("operator_relayed_unverified_fields", 0) or 0)
            for item in artifacts
        ),
        "network_fetch_observed": any(bool(item.get("summary", {}).get("network_fetch")) for item in artifacts),
        "provider_execution_observed": any(bool(item.get("summary", {}).get("provider_execution")) for item in artifacts),
        "endpoint_probe_observed": any(bool(item.get("summary", {}).get("endpoint_probe")) for item in artifacts),
        "model_weight_read_observed": any(bool(item.get("summary", {}).get("model_weight_read")) for item in artifacts),
        "models_observed": sorted({str(metric.get("model_id", "")) for metric in metrics if metric.get("model_id")}),
        "status_counts": status_counts,
        "unresolved_models": sorted({str(field.get("model_id", "")) for field in unresolved if field.get("model_id")}),
        "unresolved_field_names": sorted({str(field.get("field", "")) for field in unresolved if field.get("field")}),
    }


def adapter_runtime_signal_summary(child_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    artifacts = [
        item
        for item in child_summaries
        if item.get("kind") == "adapter_runtime_matrix"
    ]
    rows = [
        metric
        for item in artifacts
        for metric in item.get("runtime_metrics", [])
    ]
    gate_counts: dict[str, int] = {}
    for row in rows:
        for gate in row.get("blocking_gates", []):
            gate_counts[str(gate)] = gate_counts.get(str(gate), 0) + 1
    return {
        "matrix_artifacts": len(artifacts),
        "runtime_rows": len(rows),
        "provider_roles": sorted({str(row.get("provider_role", "")) for row in rows if row.get("provider_role")}),
        "manifest_ready_roles": sorted({str(row.get("provider_role", "")) for row in rows if row.get("manifest_ready")}),
        "focused_run_ready_roles": sorted({str(row.get("provider_role", "")) for row in rows if row.get("focused_run_ready")}),
        "endpoint_profile_ready_roles": sorted({str(row.get("provider_role", "")) for row in rows if row.get("endpoint_profile_ready")}),
        "auth_ready_roles": sorted({str(row.get("provider_role", "")) for row in rows if row.get("auth_ready")}),
        "blocking_gate_counts": gate_counts,
        "roles_with_blocking_gates": sorted({
            str(row.get("provider_role", ""))
            for row in rows
            if row.get("blocking_gates")
        }),
        "provider_execution_observed": any(bool(item.get("summary", {}).get("provider_execution")) for item in artifacts),
        "endpoint_probe_observed": any(bool(item.get("summary", {}).get("endpoint_probe")) for item in artifacts),
        "model_weight_read_observed": any(bool(item.get("summary", {}).get("model_weight_read")) for item in artifacts),
        "token_store_read_observed": any(bool(item.get("summary", {}).get("token_store_read")) for item in artifacts),
    }


def forum_route_signal_summary(child_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    artifacts = [
        item
        for item in child_summaries
        if item.get("kind") == "forum_route_receipts"
    ]
    routes = [
        metric
        for item in artifacts
        for metric in item.get("route_metrics", [])
    ]
    confidences = [
        float(row["observed_confidence"])
        for row in routes
        if row.get("observed_confidence") is not None
    ]
    return {
        "route_artifacts": len(artifacts),
        "route_count": len(routes),
        "observed_route_frames": sum(1 for row in routes if row.get("observed")),
        "route_text_only": sum(1 for row in routes if not row.get("observed")),
        "escalation_count": sum(1 for row in routes if row.get("observed_needs_escalation") is True),
        "mean_observed_confidence": round(sum(confidences) / len(confidences), 4) if confidences else None,
        "decided_agents": sorted({str(row.get("observed_decided", "")) for row in routes if row.get("observed_decided")}),
        "domains": sorted({str(row.get("observed_domain", "")) for row in routes if row.get("observed_domain")}),
        "intents": sorted({str(row.get("observed_intent", "")) for row in routes if row.get("observed_intent")}),
        "proof_lanes": sorted({str(row.get("observed_proof_lane", "")) for row in routes if row.get("observed_proof_lane")}),
        "provider_execution_observed": any(bool(row.get("provider_execution_observed")) for row in routes),
        "endpoint_probe_observed": any(bool(row.get("endpoint_probe_observed")) for row in routes),
    }


def mcp_tool_health_signal_summary(child_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    artifacts = [
        item
        for item in child_summaries
        if item.get("kind") == "mcp_tool_health"
    ]
    rows = [
        metric
        for item in artifacts
        for metric in item.get("tool_health_metrics", [])
    ]
    verdict_counts: dict[str, int] = {}
    for row in rows:
        verdict = str(row.get("verdict", ""))
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
    return {
        "health_artifacts": len(artifacts),
        "tools": len(rows),
        "observed_tools": sum(1 for row in rows if row.get("observed")),
        "roots_existing": sum(1 for row in rows if row.get("root_exists")),
        "healthy_observed_tools": verdict_counts.get("OBSERVED_HEALTHY", 0),
        "degraded_observed_tools": verdict_counts.get("OBSERVED_DEGRADED", 0),
        "configured_unobserved_tools": verdict_counts.get("CONFIGURED_UNOBSERVED", 0),
        "missing_roots": verdict_counts.get("MISSING_ROOT", 0),
        "verdict_counts": verdict_counts,
        "healthy_tools": sorted({str(row.get("tool", "")) for row in rows if row.get("verdict") == "OBSERVED_HEALTHY"}),
        "degraded_tools": sorted({str(row.get("tool", "")) for row in rows if row.get("verdict") == "OBSERVED_DEGRADED"}),
        "unobserved_tools": sorted({str(row.get("tool", "")) for row in rows if not row.get("observed")}),
        "provider_execution_observed": any(bool(row.get("provider_execution_observed")) for row in rows),
        "endpoint_probe_observed": any(bool(row.get("endpoint_probe_observed")) for row in rows),
    }


def conclusion(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    dry_plan = bool(report.get("dry_plan"))
    if dry_plan:
        return {
            "verdict": "OUTCOME_PLAN_ONLY",
            "claim": "No benchmark execution evidence is present; this report is a runnable plan.",
        }
    failed = int(summary.get("failed_steps", 0) or 0)
    timeout = int(summary.get("timeout_steps", 0) or 0)
    if failed or timeout:
        return {
            "verdict": "OUTCOME_PARTIAL",
            "claim": "The run produced evidence, but at least one orchestration step failed or timed out.",
        }
    return {
        "verdict": "OUTCOME_RECORDED",
        "claim": "All orchestration steps completed at process level; child scorecards must still be inspected for model-quality conclusions.",
    }


def build_outcome(report: dict[str, Any], *, source_report_path: str) -> dict[str, Any]:
    rows = _step_rows(report)
    child_summaries = extract_child_artifact_summaries(report)
    observed_steps = [
        {
            "step_id": row.get("step_id", ""),
            "status": row.get("status", ""),
            "returncode": row.get("returncode"),
            "elapsed_ms": row.get("elapsed_ms", 0),
            "expected_artifacts": row.get("expected_artifacts", []),
        }
        for row in rows
    ]
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    return {
        "schema": "harness.closed-loop-outcome/v1",
        "timestamp_utc": _now(),
        "source_report_path": source_report_path,
        "source_schema": report.get("schema", ""),
        "run_id": report.get("run_id", ""),
        "store_root": report.get("store_root", ""),
        "artifact_dir": report.get("artifact_dir", ""),
        "conclusion": conclusion(report),
        "observations": {
            "dry_plan": bool(report.get("dry_plan")),
            "planned_steps": len(report.get("planned_steps", []) or []),
            "observed_steps": observed_steps,
            "child_artifacts": child_summaries,
            "executable_manifest_signals": executable_manifest_signal_summary(child_summaries),
            "command_registry_signals": command_registry_signal_summary(child_summaries),
            "benchmark_profile_signals": benchmark_profile_signal_summary(child_summaries),
            "benchmark_execution_matrix_signals": benchmark_execution_matrix_signal_summary(child_summaries),
            "benchmark_coverage_signals": benchmark_coverage_signal_summary(child_summaries),
            "schematic_drift_signals": schematic_drift_signal_summary(child_summaries),
            "agentic_task_manifest_signals": agentic_task_manifest_signal_summary(child_summaries),
            "cross_harness_manifest_signals": cross_harness_manifest_signal_summary(child_summaries),
            "adapter_runtime_signals": adapter_runtime_signal_summary(child_summaries),
            "forum_route_signals": forum_route_signal_summary(child_summaries),
            "mcp_tool_health_signals": mcp_tool_health_signal_summary(child_summaries),
            "forum_deep_verify_signals": forum_deep_verify_signal_summary(child_summaries),
            "embodied_realtime_signals": embodied_realtime_signal_summary(child_summaries),
            "model_card_claim_signals": model_card_claim_signal_summary(child_summaries),
            "comparison_report_signals": comparison_report_signal_summary(child_summaries),
            "benchmark_signals": benchmark_signal_summary(child_summaries),
            "context_signals": context_signal_summary(child_summaries),
            "tool_readiness_signals": tool_readiness_signal_summary(child_summaries),
            "tool_hardening_signals": tool_hardening_signal_summary(child_summaries),
            "model_endpoint_signals": model_endpoint_signal_summary(child_summaries),
            "model_release_signals": model_release_signal_summary(child_summaries),
            "model_publish_signals": model_publish_signal_summary(child_summaries),
            "gather_readiness_signals": gather_readiness_signal_summary(child_summaries),
            "summary": summary,
        },
        "inferences": [
            "Shared run-id orchestration is available when every child command includes --store-root and --run-id.",
            "Step-level process success is not equivalent to model-quality success; child scorecards remain the authority for benchmark claims.",
        ],
        "unknowns": [
            "No model-quality comparison can be concluded from a dry plan.",
            "Endpoint availability must be interpreted from endpoint-auth and child benchmark artifacts.",
            "Provider deltas extracted from child scorecards are only as strong as the executed benchmark scope.",
            "Full Codex/Flywheel/Claude/OpenCode/local-model conclusions require the full benchmark battery, not only the bounded seed slice.",
            "Static model release readiness does not prove live endpoint quality, checksum correctness, or publication readiness without executed benchmark and integrity artifacts.",
            "Static gather readiness does not prove source capture quality or authorization-specific corpus coverage without executed gather receipts.",
            "Static command registry artifacts document launch surfaces, but they do not prove delegated commands were executed.",
            "Static benchmark profiles define measurement intent, but they do not replace executed scorecards.",
            "Benchmark coverage reports identify missing evidence; they do not infer quality for absent scorecards.",
        ],
        "next_checks": [
            "Run the closed-loop seed dry plan if this outcome was built from stale or missing plan evidence.",
            "Execute the closed-loop seed command to create a shared-run receipt bundle.",
            "Inspect child scorecards for provider-level pass rates, latency, failure classes, and skipped endpoint posture.",
            "Extend orchestration to live gather receipts and live 14B/32B benchmark, checksum, and endpoint gates.",
        ],
    }


def render_markdown(outcome: dict[str, Any]) -> str:
    conclusion_obj = outcome["conclusion"]
    lines = [
        "# Closed-loop benchmark experimental outcome",
        "",
        f"- Schema: `{outcome['schema']}`",
        f"- Timestamp UTC: `{outcome['timestamp_utc']}`",
        f"- Run id: `{outcome['run_id']}`",
        f"- Source report: `{outcome['source_report_path']}`",
        f"- Verdict: `{conclusion_obj['verdict']}`",
        f"- Claim: {conclusion_obj['claim']}",
        "",
        "## Observations",
        "",
        f"- Dry plan: `{str(outcome['observations']['dry_plan']).lower()}`",
        f"- Planned steps: `{outcome['observations']['planned_steps']}`",
        f"- Executable manifest artifacts parsed: `{outcome['observations']['executable_manifest_signals']['manifest_artifacts']}`",
        f"- Executable commands observed: `{outcome['observations']['executable_manifest_signals']['commands']}`",
        f"- Command registry artifacts parsed: `{outcome['observations']['command_registry_signals']['registry_artifacts']}`",
        f"- Registry commands observed: `{outcome['observations']['command_registry_signals']['commands']}`",
        f"- Benchmark profile artifacts parsed: `{outcome['observations']['benchmark_profile_signals']['profile_artifacts']}`",
        f"- Profile benchmarks defined: `{outcome['observations']['benchmark_profile_signals']['benchmarks']}`",
        f"- Benchmark execution matrix artifacts parsed: `{outcome['observations']['benchmark_execution_matrix_signals']['matrix_artifacts']}`",
        f"- Execution matrix steps defined: `{outcome['observations']['benchmark_execution_matrix_signals']['steps']}`",
        f"- Benchmark coverage artifacts parsed: `{outcome['observations']['benchmark_coverage_signals']['coverage_artifacts']}`",
        f"- Agentic task manifest artifacts parsed: `{outcome['observations']['agentic_task_manifest_signals']['manifest_artifacts']}`",
        f"- Planned agentic tasks: `{outcome['observations']['agentic_task_manifest_signals']['task_count']}`",
        f"- Adapter runtime matrix artifacts parsed: `{outcome['observations']['adapter_runtime_signals']['matrix_artifacts']}`",
        f"- Adapter runtime rows: `{outcome['observations']['adapter_runtime_signals']['runtime_rows']}`",
        f"- Forum route receipt artifacts parsed: `{outcome['observations']['forum_route_signals']['route_artifacts']}`",
        f"- Forum route frames observed: `{outcome['observations']['forum_route_signals']['observed_route_frames']}`",
        f"- MCP tool health artifacts parsed: `{outcome['observations']['mcp_tool_health_signals']['health_artifacts']}`",
        f"- MCP degraded observed tools: `{outcome['observations']['mcp_tool_health_signals']['degraded_observed_tools']}`",
        f"- Forum deep-verify artifacts parsed: `{outcome['observations']['forum_deep_verify_signals']['benchmark_artifacts']}`",
        f"- Forum deep-verify cases: `{outcome['observations']['forum_deep_verify_signals']['case_count']}`",
        f"- Embodied realtime plan artifacts parsed: `{outcome['observations']['embodied_realtime_signals']['plan_artifacts']}`",
        f"- Embodied realtime planned rows: `{outcome['observations']['embodied_realtime_signals']['planned_probe_rows']}`",
        f"- Model-card claim table artifacts parsed: `{outcome['observations']['model_card_claim_signals']['claim_table_artifacts']}`",
        f"- Model-card unresolved claim fields: `{outcome['observations']['model_card_claim_signals']['unresolved_fields']}`",
        f"- Comparison report artifacts parsed: `{outcome['observations']['comparison_report_signals']['comparison_artifacts']}`",
        f"- Available Codex/Flywheel comparisons: `{outcome['observations']['comparison_report_signals']['available_comparisons']}`",
        f"- Missing runnable benchmarks: `{', '.join(outcome['observations']['benchmark_coverage_signals']['missing_runnable_benchmark_ids'])}`",
        f"- Benchmark scorecards parsed: `{outcome['observations']['benchmark_signals']['scorecard_count']}`",
        f"- Providers observed: `{', '.join(outcome['observations']['benchmark_signals']['providers_observed'])}`",
        f"- Context inventory artifacts parsed: `{outcome['observations']['context_signals']['inventory_count']}`",
        f"- Context entries observed: `{outcome['observations']['context_signals']['entries']}`",
        f"- Context sensitive-name entries: `{outcome['observations']['context_signals']['sensitive_name_entries']}`",
        f"- Tool readiness artifacts parsed: `{outcome['observations']['tool_readiness_signals']['readiness_artifacts']}`",
        f"- Tools observed: `{', '.join(outcome['observations']['tool_readiness_signals']['tools_observed'])}`",
        f"- Tool hardening plan artifacts parsed: `{outcome['observations']['tool_hardening_signals']['plan_artifacts']}`",
        f"- Tool hardening actions: `{outcome['observations']['tool_hardening_signals']['actions']}`",
        f"- Model endpoint artifacts parsed: `{outcome['observations']['model_endpoint_signals']['endpoint_artifacts']}`",
        f"- Model endpoint backends observed: `{', '.join(outcome['observations']['model_endpoint_signals']['backends_observed'])}`",
        f"- Model release artifacts parsed: `{outcome['observations']['model_release_signals']['release_artifacts']}`",
        f"- Models observed: `{', '.join(outcome['observations']['model_release_signals']['models_observed'])}`",
        f"- Model publish plan artifacts parsed: `{outcome['observations']['model_publish_signals']['publish_plan_artifacts']}`",
        f"- Model candidate names: `{', '.join(outcome['observations']['model_publish_signals']['candidate_names'])}`",
        f"- Gather readiness artifacts parsed: `{outcome['observations']['gather_readiness_signals']['readiness_artifacts']}`",
        "",
        "| Step | Status | Return code | Elapsed ms | Artifacts |",
        "|---|---|---:|---:|---:|",
    ]
    for row in outcome["observations"]["observed_steps"]:
        artifacts = row.get("expected_artifacts", [])
        lines.append(
            "| {step} | {status} | {returncode} | {elapsed} | {artifacts} |".format(
                step=row.get("step_id", ""),
                status=row.get("status", ""),
                returncode="" if row.get("returncode") is None else row.get("returncode"),
                elapsed=row.get("elapsed_ms", 0),
                artifacts=len(artifacts) if isinstance(artifacts, list) else 0,
            )
        )
    lines.extend(["", "## Benchmark signals", ""])
    manifest_signals = outcome["observations"].get("executable_manifest_signals", {})
    if manifest_signals.get("manifest_artifacts"):
        lines.extend([
            "## Executable manifest signals",
            "",
            f"- Manifest artifacts: `{manifest_signals.get('manifest_artifacts', 0)}`",
            f"- Commands observed: `{', '.join(manifest_signals.get('command_names', []))}`",
            f"- Schema count: `{manifest_signals.get('schema_count', 0)}`",
            f"- Target count: `{manifest_signals.get('target_count', 0)}`",
            "",
        ])
    registry_signals = outcome["observations"].get("command_registry_signals", {})
    if registry_signals.get("registry_artifacts"):
        lines.extend([
            "## Command registry signals",
            "",
            f"- Registry artifacts: `{registry_signals.get('registry_artifacts', 0)}`",
            f"- Commands observed: `{', '.join(registry_signals.get('command_names', []))}`",
            f"- Risk counts: `{json.dumps(registry_signals.get('risk_counts', {}), sort_keys=True)}`",
            f"- Schema count: `{registry_signals.get('schema_count', 0)}`",
            f"- HTML paths: `{', '.join(registry_signals.get('html_paths', []))}`",
            "",
        ])
    profile_signals = outcome["observations"].get("benchmark_profile_signals", {})
    if profile_signals.get("profile_artifacts"):
        lines.extend([
            "## Benchmark profile signals",
            "",
            f"- Profile artifacts: `{profile_signals.get('profile_artifacts', 0)}`",
            f"- Providers: `{', '.join(profile_signals.get('providers', []))}`",
            f"- Metrics: `{', '.join(profile_signals.get('metrics', []))}`",
            f"- Benchmarks defined: `{profile_signals.get('benchmarks', 0)}`",
            f"- Runnable benchmarks: `{profile_signals.get('runnable_benchmarks', 0)}`",
            f"- Planned full benchmarks: `{profile_signals.get('planned_full_benchmarks', 0)}`",
            f"- Coverage units declared: `{profile_signals.get('coverage_units', 0)}`",
            f"- Existing benchmark artifacts: `{profile_signals.get('existing_artifacts', 0)}`",
            f"- Dataset lanes: `{', '.join(profile_signals.get('dataset_lanes', []))}`",
            f"- Pressure variables: `{', '.join(profile_signals.get('pressure_variables', []))}`",
            f"- Benchmark ids: `{', '.join(profile_signals.get('benchmark_ids', []))}`",
            f"- Weight sums: `{json.dumps(profile_signals.get('weight_sums', []), sort_keys=True)}`",
            f"- Dataset lane weight sums: `{json.dumps(profile_signals.get('dataset_lane_weight_sums', []), sort_keys=True)}`",
            "",
        ])
    coverage_signals = outcome["observations"].get("benchmark_coverage_signals", {})
    matrix_signals = outcome["observations"].get("benchmark_execution_matrix_signals", {})
    if matrix_signals.get("matrix_artifacts"):
        lines.extend([
            "## Benchmark execution matrix signals",
            "",
            f"- Matrix artifacts: `{matrix_signals.get('matrix_artifacts', 0)}`",
            f"- Providers: `{', '.join(matrix_signals.get('providers', []))}`",
            f"- Expected provider roles: `{', '.join(matrix_signals.get('expected_provider_roles', []))}`",
            f"- Steps defined: `{matrix_signals.get('steps', 0)}`",
            f"- Dry/focused/full steps: `{matrix_signals.get('dry_steps', 0)}` / `{matrix_signals.get('focused_steps', 0)}` / `{matrix_signals.get('full_steps', 0)}`",
            f"- Long-running steps: `{matrix_signals.get('long_running_steps', 0)}`",
            f"- Operator-approval steps: `{matrix_signals.get('operator_approval_required_steps', 0)}`",
            f"- Tier step counts: `{json.dumps(matrix_signals.get('tier_step_counts', {}), sort_keys=True)}`",
            f"- Long-running step ids: `{', '.join(matrix_signals.get('long_running_step_ids', []))}`",
            f"- Operator-approval step ids: `{', '.join(matrix_signals.get('operator_approval_required_step_ids', []))}`",
            f"- Step ids: `{', '.join(matrix_signals.get('step_ids', []))}`",
            f"- Expected schemas: `{', '.join(matrix_signals.get('expected_schemas', []))}`",
            f"- Evidence gates: `{', '.join(matrix_signals.get('evidence_gates', []))}`",
            "",
        ])
    if coverage_signals.get("coverage_artifacts"):
        lines.extend([
            "## Benchmark coverage signals",
            "",
            f"- Coverage artifacts: `{coverage_signals.get('coverage_artifacts', 0)}`",
            f"- Mean benchmark coverage rate: `{coverage_signals.get('mean_benchmark_coverage_rate', 0.0)}`",
            f"- Mean unit coverage rate: `{coverage_signals.get('mean_unit_coverage_rate', 0.0)}`",
            f"- Mean unit metric completeness rate: `{coverage_signals.get('mean_unit_metric_completeness_rate', 0.0)}`",
            f"- Mean unit metric validity rate: `{coverage_signals.get('mean_unit_metric_validity_rate', 0.0)}`",
            f"- Mean provider coverage rate: `{coverage_signals.get('mean_provider_coverage_rate', 0.0)}`",
            f"- Mean provider-unit coverage rate: `{coverage_signals.get('mean_provider_unit_coverage_rate', 0.0)}`",
            f"- Mean provider-unit validity rate: `{coverage_signals.get('mean_provider_unit_validity_rate', 0.0)}`",
            f"- Mean dataset lane coverage rate: `{coverage_signals.get('mean_dataset_lane_coverage_rate', 0.0)}`",
            f"- Mean pressure variable coverage rate: `{coverage_signals.get('mean_pressure_variable_coverage_rate', 0.0)}`",
            f"- Observed benchmarks: `{', '.join(coverage_signals.get('observed_benchmark_ids', []))}`",
            f"- Missing runnable benchmarks: `{', '.join(coverage_signals.get('missing_runnable_benchmark_ids', []))}`",
            f"- Observed dataset lanes: `{', '.join(coverage_signals.get('observed_dataset_lanes', []))}`",
            f"- Missing dataset lanes: `{', '.join(coverage_signals.get('missing_dataset_lanes', []))}`",
            f"- Observed pressure variables: `{', '.join(coverage_signals.get('observed_pressure_variables', []))}`",
            f"- Missing pressure variables: `{', '.join(coverage_signals.get('missing_pressure_variables', []))}`",
            f"- Observed units: `{json.dumps(coverage_signals.get('observed_units_by_benchmark', {}), sort_keys=True)}`",
            f"- Missing units: `{json.dumps(coverage_signals.get('missing_units_by_benchmark', {}), sort_keys=True)}`",
            f"- Incomplete units: `{json.dumps(coverage_signals.get('incomplete_units_by_benchmark', {}), sort_keys=True)}`",
            f"- Invalid units: `{json.dumps(coverage_signals.get('invalid_units_by_benchmark', {}), sort_keys=True)}`",
            f"- Missing provider units: `{json.dumps(coverage_signals.get('missing_provider_units_by_benchmark', {}), sort_keys=True)}`",
            f"- Invalid provider units: `{json.dumps(coverage_signals.get('invalid_provider_units_by_benchmark', {}), sort_keys=True)}`",
            f"- Observed providers: `{', '.join(coverage_signals.get('observed_providers', []))}`",
            f"- Missing providers: `{', '.join(coverage_signals.get('missing_providers', []))}`",
            f"- Raw expected providers: `{', '.join(coverage_signals.get('raw_expected_providers', []))}`",
            f"- Provider aliases: `{json.dumps(coverage_signals.get('provider_aliases', {}), sort_keys=True)}`",
            f"- Load errors: `{coverage_signals.get('load_errors', 0)}`",
            f"- Verdict counts: `{json.dumps(coverage_signals.get('verdict_counts', {}), sort_keys=True)}`",
            "",
        ])
    drift_signals = outcome["observations"].get("schematic_drift_signals", {})
    if drift_signals.get("drift_artifacts"):
        lines.extend([
            "## Schematic drift signals",
            "",
            f"- Drift artifacts: `{drift_signals.get('drift_artifacts', 0)}`",
            f"- Verdicts: `{', '.join(drift_signals.get('verdicts', []))}`",
            f"- Missing nodes: `{drift_signals.get('missing_nodes', 0)}`",
            f"- Missing edges: `{drift_signals.get('missing_edges', 0)}`",
            f"- Missing files: `{drift_signals.get('missing_files', 0)}`",
            f"- Stale phrases: `{drift_signals.get('stale_phrases', 0)}`",
            "",
        ])
    task_manifest_signals = outcome["observations"].get("agentic_task_manifest_signals", {})
    if task_manifest_signals.get("manifest_artifacts"):
        lines.extend([
            "## Agentic task manifest signals",
            "",
            f"- Manifest artifacts: `{task_manifest_signals.get('manifest_artifacts', 0)}`",
            f"- Planned tasks: `{task_manifest_signals.get('task_count', 0)}`",
            f"- Planned scorecard rows: `{task_manifest_signals.get('planned_scorecard_rows', 0)}`",
            f"- Benchmark ids: `{', '.join(task_manifest_signals.get('benchmark_ids', []))}`",
            f"- Dataset lanes: `{', '.join(task_manifest_signals.get('dataset_lanes', []))}`",
            f"- Coverage units: `{', '.join(task_manifest_signals.get('coverage_units', []))}`",
            f"- Provider roles: `{', '.join(task_manifest_signals.get('provider_roles', []))}`",
            f"- Prompt hashes: `{', '.join(task_manifest_signals.get('prompt_hashes', []))}`",
            "",
        ])
    cross_harness_signals = outcome["observations"].get("cross_harness_manifest_signals", {})
    if cross_harness_signals.get("manifest_artifacts"):
        lines.extend([
            "## Cross-harness manifest signals",
            "",
            f"- Manifest artifacts: `{cross_harness_signals.get('manifest_artifacts', 0)}`",
            f"- Planned tasks: `{cross_harness_signals.get('task_count', 0)}`",
            f"- Planned scorecard rows: `{cross_harness_signals.get('planned_scorecard_rows', 0)}`",
            f"- Benchmark ids: `{', '.join(cross_harness_signals.get('benchmark_ids', []))}`",
            f"- Provider roles: `{', '.join(cross_harness_signals.get('provider_roles', []))}`",
            f"- Prompt hashes: `{', '.join(cross_harness_signals.get('prompt_hashes', []))}`",
            "",
        ])
    adapter_runtime_signals = outcome["observations"].get("adapter_runtime_signals", {})
    if adapter_runtime_signals.get("matrix_artifacts"):
        lines.extend([
            "## Adapter runtime signals",
            "",
            f"- Matrix artifacts: `{adapter_runtime_signals.get('matrix_artifacts', 0)}`",
            f"- Runtime rows: `{adapter_runtime_signals.get('runtime_rows', 0)}`",
            f"- Provider roles: `{', '.join(adapter_runtime_signals.get('provider_roles', []))}`",
            f"- Manifest-ready roles: `{', '.join(adapter_runtime_signals.get('manifest_ready_roles', []))}`",
            f"- Focused-run-ready roles: `{', '.join(adapter_runtime_signals.get('focused_run_ready_roles', []))}`",
            f"- Endpoint-profile-ready roles: `{', '.join(adapter_runtime_signals.get('endpoint_profile_ready_roles', []))}`",
            f"- Auth-ready roles: `{', '.join(adapter_runtime_signals.get('auth_ready_roles', []))}`",
            f"- Roles with blocking gates: `{', '.join(adapter_runtime_signals.get('roles_with_blocking_gates', []))}`",
            f"- Blocking gate counts: `{json.dumps(adapter_runtime_signals.get('blocking_gate_counts', {}), sort_keys=True)}`",
            f"- Provider execution observed: `{str(adapter_runtime_signals.get('provider_execution_observed', False)).lower()}`",
            f"- Endpoint probe observed: `{str(adapter_runtime_signals.get('endpoint_probe_observed', False)).lower()}`",
            f"- Model weight read observed: `{str(adapter_runtime_signals.get('model_weight_read_observed', False)).lower()}`",
            f"- Token store read observed: `{str(adapter_runtime_signals.get('token_store_read_observed', False)).lower()}`",
            "",
        ])
    forum_route_signals = outcome["observations"].get("forum_route_signals", {})
    if forum_route_signals.get("route_artifacts"):
        lines.extend([
            "## Forum route signals",
            "",
            f"- Route artifacts: `{forum_route_signals.get('route_artifacts', 0)}`",
            f"- Routes: `{forum_route_signals.get('route_count', 0)}`",
            f"- Observed route frames: `{forum_route_signals.get('observed_route_frames', 0)}`",
            f"- Route-text-only rows: `{forum_route_signals.get('route_text_only', 0)}`",
            f"- Escalations: `{forum_route_signals.get('escalation_count', 0)}`",
            f"- Mean observed confidence: `{forum_route_signals.get('mean_observed_confidence')}`",
            f"- Decided agents: `{', '.join(forum_route_signals.get('decided_agents', []))}`",
            f"- Domains: `{', '.join(forum_route_signals.get('domains', []))}`",
            f"- Intents: `{', '.join(forum_route_signals.get('intents', []))}`",
            f"- Proof lanes: `{', '.join(forum_route_signals.get('proof_lanes', []))}`",
            f"- Provider execution observed: `{str(forum_route_signals.get('provider_execution_observed', False)).lower()}`",
            f"- Endpoint probe observed: `{str(forum_route_signals.get('endpoint_probe_observed', False)).lower()}`",
            "",
        ])
    mcp_health_signals = outcome["observations"].get("mcp_tool_health_signals", {})
    if mcp_health_signals.get("health_artifacts"):
        lines.extend([
            "## MCP tool health signals",
            "",
            f"- Health artifacts: `{mcp_health_signals.get('health_artifacts', 0)}`",
            f"- Tools: `{mcp_health_signals.get('tools', 0)}`",
            f"- Observed tools: `{mcp_health_signals.get('observed_tools', 0)}`",
            f"- Existing roots: `{mcp_health_signals.get('roots_existing', 0)}`",
            f"- Healthy observed tools: `{mcp_health_signals.get('healthy_observed_tools', 0)}`",
            f"- Degraded observed tools: `{mcp_health_signals.get('degraded_observed_tools', 0)}`",
            f"- Configured unobserved tools: `{mcp_health_signals.get('configured_unobserved_tools', 0)}`",
            f"- Missing roots: `{mcp_health_signals.get('missing_roots', 0)}`",
            f"- Healthy tools: `{', '.join(mcp_health_signals.get('healthy_tools', []))}`",
            f"- Degraded tools: `{', '.join(mcp_health_signals.get('degraded_tools', []))}`",
            f"- Unobserved tools: `{', '.join(mcp_health_signals.get('unobserved_tools', []))}`",
            f"- Verdict counts: `{json.dumps(mcp_health_signals.get('verdict_counts', {}), sort_keys=True)}`",
            f"- Provider execution observed: `{str(mcp_health_signals.get('provider_execution_observed', False)).lower()}`",
            f"- Endpoint probe observed: `{str(mcp_health_signals.get('endpoint_probe_observed', False)).lower()}`",
            "",
        ])
    forum_deep_signals = outcome["observations"].get("forum_deep_verify_signals", {})
    if forum_deep_signals.get("benchmark_artifacts"):
        lines.extend([
            "## Forum deep-verify signals",
            "",
            f"- Benchmark artifacts: `{forum_deep_signals.get('benchmark_artifacts', 0)}`",
            f"- Cases: `{forum_deep_signals.get('case_count', 0)}`",
            f"- Max entry count: `{forum_deep_signals.get('max_entry_count', 0)}`",
            f"- Max payload body bytes: `{forum_deep_signals.get('max_payload_body_bytes', 0)}`",
            f"- Storage modes: `{', '.join(forum_deep_signals.get('storage_modes', []))}`",
            f"- Redaction ratios: `{json.dumps(forum_deep_signals.get('redaction_ratios', []), sort_keys=True)}`",
            f"- Payloads present/redacted: `{forum_deep_signals.get('payloads_present', 0)}` / `{forum_deep_signals.get('payloads_redacted', 0)}`",
            f"- Mean verify(deep=True) ms: `{forum_deep_signals.get('mean_verify_deep_ms', 0.0)}`",
            f"- Max verify(deep=True) ms: `{forum_deep_signals.get('max_verify_deep_ms', 0.0)}`",
            "",
        ])
    embodied_signals = outcome["observations"].get("embodied_realtime_signals", {})
    if embodied_signals.get("plan_artifacts"):
        lines.extend([
            "## Embodied realtime multimodal signals",
            "",
            f"- Plan artifacts: `{embodied_signals.get('plan_artifacts', 0)}`",
            f"- Planned probe rows: `{embodied_signals.get('planned_probe_rows', 0)}`",
            f"- Planned scorecard rows: `{embodied_signals.get('planned_scorecard_rows', 0)}`",
            f"- Provider roles: `{', '.join(embodied_signals.get('provider_roles', []))}`",
            f"- Latency budgets ms: `{', '.join(str(item) for item in embodied_signals.get('latency_budgets_ms', []))}`",
            f"- Dataset lanes: `{', '.join(embodied_signals.get('dataset_lanes', []))}`",
            f"- Pressure variables: `{', '.join(embodied_signals.get('pressure_variables', []))}`",
            f"- Probe ids: `{', '.join(embodied_signals.get('probe_ids', []))}`",
            f"- Coverage units: `{', '.join(embodied_signals.get('coverage_units', []))}`",
            f"- Model leads unverified: `{', '.join(embodied_signals.get('model_leads_unverified', []))}`",
            "",
        ])
    claim_signals = outcome["observations"].get("model_card_claim_signals", {})
    if claim_signals.get("claim_table_artifacts"):
        lines.extend([
            "## Model-card claim signals",
            "",
            f"- Claim table artifacts: `{claim_signals.get('claim_table_artifacts', 0)}`",
            f"- Model candidates: `{claim_signals.get('model_candidates', 0)}`",
            f"- Claim fields: `{claim_signals.get('claim_fields', 0)}`",
            f"- Unresolved fields: `{claim_signals.get('unresolved_fields', 0)}`",
            f"- Verified primary-source fields: `{claim_signals.get('verified_primary_source_fields', 0)}`",
            f"- Verified secondary-source fields: `{claim_signals.get('verified_secondary_source_fields', 0)}`",
            f"- Not checked fields: `{claim_signals.get('not_checked_fields', 0)}`",
            f"- Operator-relayed unverified fields: `{claim_signals.get('operator_relayed_unverified_fields', 0)}`",
            f"- Network fetch observed: `{str(claim_signals.get('network_fetch_observed', False)).lower()}`",
            f"- Provider execution observed: `{str(claim_signals.get('provider_execution_observed', False)).lower()}`",
            f"- Endpoint probe observed: `{str(claim_signals.get('endpoint_probe_observed', False)).lower()}`",
            f"- Model weight read observed: `{str(claim_signals.get('model_weight_read_observed', False)).lower()}`",
            f"- Models observed: `{', '.join(claim_signals.get('models_observed', []))}`",
            f"- Unresolved models: `{', '.join(claim_signals.get('unresolved_models', []))}`",
            f"- Unresolved field names: `{', '.join(claim_signals.get('unresolved_field_names', []))}`",
            f"- Status counts: `{json.dumps(claim_signals.get('status_counts', {}), sort_keys=True)}`",
            "",
        ])
    comparison_report_signals = outcome["observations"].get("comparison_report_signals", {})
    if comparison_report_signals.get("comparison_artifacts"):
        lines.extend([
            "## Harness comparison signals",
            "",
            f"- Comparison artifacts: `{comparison_report_signals.get('comparison_artifacts', 0)}`",
            f"- Comparison keys: `{comparison_report_signals.get('comparison_keys', 0)}`",
            f"- Available Codex/Flywheel comparisons: `{comparison_report_signals.get('available_comparisons', 0)}`",
            f"- Flywheel quality wins: `{comparison_report_signals.get('flywheel_quality_wins', 0)}`",
            f"- Codex quality wins: `{comparison_report_signals.get('codex_quality_wins', 0)}`",
            f"- Quality ties: `{comparison_report_signals.get('quality_ties', 0)}`",
            f"- Verdict counts: `{json.dumps(comparison_report_signals.get('verdict_counts', {}), sort_keys=True)}`",
            f"- Comparison keys observed: `{', '.join(comparison_report_signals.get('comparison_keys_observed', []))}`",
            "",
        ])
    context_signals = outcome["observations"].get("context_signals", {})
    if context_signals.get("inventory_count"):
        lines.extend([
            "## Context signals",
            "",
            f"- Inventories parsed: `{context_signals.get('inventory_count', 0)}`",
            f"- Existing roots observed: `{context_signals.get('existing_roots', 0)}`",
            f"- Entries observed: `{context_signals.get('entries', 0)}`",
            f"- Label counts: `{json.dumps(context_signals.get('label_counts', {}), sort_keys=True)}`",
            "",
        ])
    tool_signals = outcome["observations"].get("tool_readiness_signals", {})
    if tool_signals.get("readiness_artifacts"):
        lines.extend([
            "## Tool readiness signals",
            "",
            f"- Tools observed: `{', '.join(tool_signals.get('tools_observed', []))}`",
            f"- Existing tools: `{tool_signals.get('existing_tools', 0)}` / `{tool_signals.get('tools', 0)}`",
            f"- Enterprise-ready tools: `{tool_signals.get('enterprise_ready_tools', 0)}`",
            f"- Mean static score: `{tool_signals.get('mean_score', 0.0)}`",
            f"- Verdict counts: `{json.dumps(tool_signals.get('verdict_counts', {}), sort_keys=True)}`",
            "",
        ])
    hardening_signals = outcome["observations"].get("tool_hardening_signals", {})
    if hardening_signals.get("plan_artifacts"):
        lines.extend([
            "## Tool hardening signals",
            "",
            f"- Plan artifacts: `{hardening_signals.get('plan_artifacts', 0)}`",
            f"- Actions: `{hardening_signals.get('actions', 0)}`",
            f"- Release gates passed: `{hardening_signals.get('passed_release_gates', 0)}` / `{hardening_signals.get('release_gates', 0)}`",
            f"- Priority counts: `{json.dumps(hardening_signals.get('priority_counts', {}), sort_keys=True)}`",
            f"- Owner counts: `{json.dumps(hardening_signals.get('owner_counts', {}), sort_keys=True)}`",
            f"- Tools observed: `{', '.join(hardening_signals.get('tools_observed', []))}`",
            "",
        ])
    model_signals = outcome["observations"].get("model_release_signals", {})
    endpoint_signals = outcome["observations"].get("model_endpoint_signals", {})
    if endpoint_signals.get("endpoint_artifacts"):
        lines.extend([
            "## Model endpoint signals",
            "",
            f"- Models observed: `{', '.join(endpoint_signals.get('models_observed', []))}`",
            f"- Backends observed: `{', '.join(endpoint_signals.get('backends_observed', []))}`",
            f"- Provider roles observed: `{', '.join(endpoint_signals.get('provider_roles_observed', []))}`",
            f"- Endpoint profiles: `{endpoint_signals.get('profiles', 0)}`",
            f"- Existing roots: `{endpoint_signals.get('existing_roots', 0)}`",
            f"- Agentic profiles: `{endpoint_signals.get('agentic_profiles', 0)}`",
            f"- Live-probed profiles: `{endpoint_signals.get('live_probed_profiles', 0)}`",
            f"- Gate rows: `{endpoint_signals.get('gate_rows', 0)}`",
            f"- Gate health OK rows: `{endpoint_signals.get('gate_health_ok_rows', 0)}`",
            f"- Gate generation OK rows: `{endpoint_signals.get('gate_generation_ok_rows', 0)}`",
            f"- Gate failed rows: `{endpoint_signals.get('gate_failed_rows', 0)}`",
            "",
        ])
    if model_signals.get("release_artifacts"):
        lines.extend([
            "## Model release signals",
            "",
            f"- Models observed: `{', '.join(model_signals.get('models_observed', []))}`",
            f"- Existing models: `{model_signals.get('existing_models', 0)}` / `{model_signals.get('models', 0)}`",
            f"- Models with weights: `{model_signals.get('models_with_weights', 0)}`",
            f"- Release-ready static models: `{model_signals.get('release_ready_models', 0)}`",
            f"- Endpoint profile matches: `{model_signals.get('endpoint_profile_matches', 0)}`",
            f"- Endpoint gate rows: `{model_signals.get('endpoint_gate_rows', 0)}`",
            f"- Endpoint gate generation OK: `{model_signals.get('endpoint_gate_generation_ok', 0)}`",
            f"- Benchmark artifact matches: `{model_signals.get('benchmark_artifact_matches', 0)}`",
            f"- Mean release doc score: `{model_signals.get('mean_release_doc_score', 0.0)}`",
            f"- Verdict counts: `{json.dumps(model_signals.get('verdict_counts', {}), sort_keys=True)}`",
            "",
        ])
    publish_signals = outcome["observations"].get("model_publish_signals", {})
    if publish_signals.get("publish_plan_artifacts"):
        lines.extend([
            "## Model publish signals",
            "",
            f"- Publish plan artifacts: `{publish_signals.get('publish_plan_artifacts', 0)}`",
            f"- Candidate names: `{', '.join(publish_signals.get('candidate_names', []))}`",
            f"- Ready to stage models: `{publish_signals.get('ready_to_stage_models', 0)}`",
            f"- Do-not-publish models: `{publish_signals.get('do_not_publish_models', 0)}`",
            f"- Actions: `{publish_signals.get('actions', 0)}`",
            f"- Blockers: `{publish_signals.get('blockers', 0)}`",
            "",
        ])
    gather_signals = outcome["observations"].get("gather_readiness_signals", {})
    if gather_signals.get("readiness_artifacts"):
        lines.extend([
            "## Gather readiness signals",
            "",
            f"- Readiness artifacts: `{gather_signals.get('readiness_artifacts', 0)}`",
            f"- Root exists count: `{gather_signals.get('root_exists_count', 0)}`",
            f"- Config count: `{gather_signals.get('config_count', 0)}`",
            f"- Credential present count: `{gather_signals.get('credential_present_count', 0)}`",
            f"- Mean core score: `{gather_signals.get('mean_core_score', 0.0)}`",
            f"- Mean Discord score: `{gather_signals.get('mean_discord_score', 0.0)}`",
            f"- Verdict counts: `{json.dumps(gather_signals.get('verdict_counts', {}), sort_keys=True)}`",
            "",
        ])
    for item in outcome["observations"]["child_artifacts"]:
        if item.get("kind") not in {
            "m7_source_mined",
            "m7_governed_agent",
            "unisonai_stateful_provider_matrix",
            "classifier_friction_accountability",
        }:
            continue
        lines.append(f"### {item.get('kind', '')}")
        lines.append("")
        comparison = item.get("comparison")
        if comparison:
            lines.append(f"- Comparison: `{json.dumps(comparison, sort_keys=True)}`")
        lines.append("")
        lines.append("| Provider | Live | Skipped | Operational | Pass rate | Quality | Latency ms | Failure |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
        for metric in item.get("provider_metrics", []):
            lines.append(
                "| {provider} | {live} | {skipped} | {operational} | {pass_rate} | {quality} | {latency} | {failure} |".format(
                    provider=metric.get("provider", ""),
                    live=str(metric.get("live", False)).lower(),
                    skipped=str(metric.get("skipped", False)).lower(),
                    operational=str(metric.get("operational", False)).lower(),
                    pass_rate=metric.get("pass_rate", 0.0),
                    quality=metric.get("quality", ""),
                    latency=metric.get("latency_ms", ""),
                    failure=metric.get("failure_class", ""),
                )
            )
        lines.append("")
    lines.extend(["", "## Inferences", ""])
    for item in outcome["inferences"]:
        lines.append(f"- {item}")
    lines.extend(["", "## Unknowns", ""])
    for item in outcome["unknowns"]:
        lines.append(f"- {item}")
    lines.extend(["", "## Next checks", ""])
    for item in outcome["next_checks"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _write_text(path_text: str, text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def _store_outcome(
    outcome: dict[str, Any],
    *,
    store_root: str,
    run_id: str,
    artifact_paths: list[tuple[str, str]],
) -> list[dict[str, Any]]:
    if not store_root:
        return []
    store = FileBackedHarnessStore(Path(store_root))
    outputs = [
        store.put_receipt(
            kind="closed_loop_outcome",
            body=outcome,
            run_id=run_id,
            verdict=outcome["conclusion"]["verdict"],
        )
    ]
    for path_text, label in artifact_paths:
        if path_text and Path(path_text).exists():
            outputs.append(store.copy_artifact(Path(path_text), run_id=run_id, label=label))
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="", help="closed-loop benchmark seed JSON report")
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    input_path = args.input or find_seed_report_in_store(
        store_root=args.store_root,
        run_id=args.run_id,
    )
    if not input_path:
        raise SystemExit("--input is required unless --store-root and --run-id locate a closed-loop seed report artifact")
    source_path = Path(input_path)
    report = _load_json(source_path)
    outcome = build_outcome(report, source_report_path=str(source_path))
    run_id = args.run_id or str(outcome.get("run_id", ""))
    json_text = json.dumps(outcome, indent=2, sort_keys=True)
    md_text = render_markdown(outcome)
    json_path = _write_text(args.out, json_text)
    md_path = _write_text(args.markdown_out, md_text)
    store_outputs = _store_outcome(
        outcome,
        store_root=args.store_root,
        run_id=run_id,
        artifact_paths=[
            (json_path, "closed-loop-outcome-json"),
            (md_path, "closed-loop-outcome-markdown"),
        ],
    )
    if store_outputs:
        outcome = {**outcome, "store_outputs": store_outputs}
        json_text = json.dumps(outcome, indent=2, sort_keys=True)
    print(json_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
