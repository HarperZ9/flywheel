"""Compare a benchmark profile contract against observed scorecard artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import re

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.file_backed_store import FileBackedHarnessStore  # noqa: E402
from harness.provider_roles import (  # noqa: E402
    provider_alias_map as default_provider_alias_map,
    provider_role as canonical_provider_role,
)


SCHEMA_TO_BENCHMARK_ID = {
    "m7-source-mined-scorecard/v1": "m7_source_mined",
    "m7-governed-agent-scorecard/v1": "m7_governed_agent",
    "unisonai.stateful-provider-matrix/v1": "unisonai_stateful_provider_matrix",
    "classifier-friction-benchmark/v1": "classifier_friction_accountability",
    "harness.model-endpoint-profiles/v1": "local_model_release_gate_14b_32b",
    "harness.model-endpoint-gate/v1": "local_model_release_gate_14b_32b",
    "harness.model-release-readiness/v1": "local_model_release_gate_14b_32b",
    "harness.gather-readiness/v1": "gather_live_source_intake",
    "harness.comparison-report/v1": "cross_harness_reproducibility_matrix",
    "harness.tool-hardening-plan/v1": "toolchain_failure_recovery_matrix",
    "harness.closed-loop-seed/v1": "closed_loop_agentic_gauntlet",
    "harness.closed-loop-benchmark-seed/v1": "closed_loop_agentic_gauntlet",
    "harness.agentic-task-manifest/v1": "closed_loop_agentic_gauntlet",
    "harness.cross-harness-manifest/v1": "cross_harness_reproducibility_matrix",
    "harness.cross-harness-task-scorecard/v1": "cross_harness_reproducibility_matrix",
    "harness.adapter-runtime-matrix/v1": "cross_harness_reproducibility_matrix",
    "forum.deep-verify-benchmark/v1": "forum_ledger_deep_verify_scaling",
    "harness.embodied-realtime-multimodal/v1": "embodied_realtime_multimodal_pressure",
    "harness.model-card-claim-table/v1": "embodied_realtime_multimodal_pressure",
}

BENCHMARK_TO_DATASET_LANES = {
    "m7_source_mined": ["source_mined_codebase_tasks"],
    "m7_governed_agent": ["agentic_tool_workflows"],
    "unisonai_stateful_provider_matrix": ["agentic_tool_workflows", "cross_harness_reproducibility"],
    "classifier_friction_accountability": ["guardrail_accountability_friction"],
    "adversarial_pressure_full_matrix": ["adversarial_receipt_integrity"],
    "local_model_release_gate_14b_32b": ["endpoint_release_gates"],
    "gather_live_source_intake": ["source_mined_codebase_tasks"],
    "closed_loop_agentic_gauntlet": ["agentic_tool_workflows", "cross_harness_reproducibility"],
    "cross_harness_reproducibility_matrix": ["cross_harness_reproducibility"],
    "toolchain_failure_recovery_matrix": ["agentic_tool_workflows"],
    "forum_ledger_deep_verify_scaling": ["replayable_causal_ledger_scaling", "adversarial_receipt_integrity"],
    "embodied_realtime_multimodal_pressure": ["embodied_realtime_multimodal", "local_resource_pressure"],
}

LOCAL_RESOURCE_PRESSURE_UNITS = {
    "14B_low_memory",
    "14B_long_context",
    "32B_low_memory",
    "32B_long_context",
    "endpoint_restart",
}

DATASET_LANE_KEYS = {
    "dataset_lane",
    "dataset_lanes",
    "lane",
}

PRESSURE_VARIABLE_KEYS = {
    "pressure_variable",
    "pressure_variables",
    "pressure_mode",
    "pressure_modes",
    "failure_injection",
    "failure_injections",
    "adversarial_lane",
    "adversarial_lanes",
}

UNIT_ID_KEYS = {
    "case_id",
    "scenario_id",
    "unit_id",
    "coverage_unit",
    "coverage_unit_id",
    "benchmark_case_id",
    "case_category",
    "category",
    "model",
}

UNIT_CONTAINER_KEYS = {
    "cases",
    "case_results",
    "scenario_results",
    "scenarios",
    "evaluations",
    "results",
    "rows",
    "backend_rows",
    "models",
    "configs",
    "profiles",
}

REQUIRED_UNIT_METRIC_GROUPS = {
    "quality": {"quality", "quality_score", "mean_quality_score", "weighted_quality_score", "adversarial_pressure_score"},
    "latency": {"latency_ms", "mean_latency_ms", "elapsed_ms", "duration_ms"},
    "failure_class": {"failure_class", "failure_code", "error_class", "verdict"},
    "receipt": {"receipt_hash", "packet_hash", "witness_hash", "byte_witness_id", "attached_witnesses", "receipt"},
}

VALID_FAILURE_VALUES = {
    "",
    "none",
    "ok",
    "match",
    "passed",
    "pass",
    "failed",
    "fail",
    "timeout",
    "provider_unavailable",
    "provider_skipped",
    "endpoint_error",
    "endpoint_unavailable",
    "provider_error",
    "empty_response",
    "unnecessary_refusal",
    "low_task_focus",
    "incomplete_receipt_witness",
    "malformed_action_json",
    "empty_repair_actions",
    "missing_source_grounding",
    "low_quality",
    "schematic_drift",
    "unauthorized_mutation",
    "missing_credential",
    "capture_skipped",
    "source_unavailable",
    "receipt_missing",
    "unverifiable",
    "drift",
    "false_match",
    "untyped_escalation",
}


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _split_paths(value: str) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(";") if part.strip()]


def _text_items(value: Any) -> list[str]:
    if isinstance(value, (str, int, float)) and str(value):
        return [str(value)]
    if isinstance(value, list):
        items: list[str] = []
        for item in value:
            items.extend(_text_items(item))
        return items
    if isinstance(value, dict):
        for key in ("lane", "name", "id", "value"):
            item = value.get(key)
            if isinstance(item, (str, int, float)) and str(item):
                return [str(item)]
    return []


def _collect_values_for_keys(value: Any, keys: set[str]) -> set[str]:
    collected: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in keys:
                collected.update(_text_items(item))
            if isinstance(item, (dict, list)):
                collected.update(_collect_values_for_keys(item, keys))
    elif isinstance(value, list):
        for item in value:
            collected.update(_collect_values_for_keys(item, keys))
    return {item for item in collected if item}


def _declared_dataset_lanes(profile: dict[str, Any]) -> list[str]:
    rows = profile.get("dataset_lanes") if isinstance(profile.get("dataset_lanes"), list) else []
    return sorted({
        str(row.get("lane", ""))
        for row in rows
        if isinstance(row, dict) and row.get("lane")
    })


def _declared_pressure_variables(profile: dict[str, Any]) -> list[str]:
    raw_variables = profile.get("pressure_variables")
    variables = set(str(item) for item in raw_variables if item) if isinstance(raw_variables, list) else set()
    rows = profile.get("dataset_lanes") if isinstance(profile.get("dataset_lanes"), list) else []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("pressure_variables"), list):
            continue
        variables.update(str(item) for item in row["pressure_variables"] if item)
    return sorted(variables)


def _artifact_benchmark_ids_from_schema(schema: str, unit_ids: list[str]) -> list[str]:
    ids: list[str] = []
    mapped = SCHEMA_TO_BENCHMARK_ID.get(schema)
    if mapped:
        ids.append(mapped)
    if schema == "harness.model-endpoint-gate/v1" and LOCAL_RESOURCE_PRESSURE_UNITS & set(unit_ids):
        ids.append("local_resource_pressure_14b_32b")
    return sorted(dict.fromkeys(ids))


def _artifact_benchmark_ids(row: dict[str, Any]) -> list[str]:
    ids = row.get("benchmark_ids") if isinstance(row.get("benchmark_ids"), list) else []
    if ids:
        return [str(item) for item in ids if item]
    benchmark_id = row.get("benchmark_id")
    return [str(benchmark_id)] if benchmark_id else []


def _dataset_lanes_for_benchmarks(benchmark_ids: list[str]) -> list[str]:
    lanes: set[str] = set()
    for benchmark_id in benchmark_ids:
        lanes.update(BENCHMARK_TO_DATASET_LANES.get(benchmark_id, []))
    return sorted(lanes)


def _write(path_text: str, text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def _load_json(path_text: str) -> tuple[dict[str, Any] | None, str]:
    if not path_text:
        return None, "empty_path"
    path = Path(path_text)
    try:
        return json.loads(path.read_text(encoding="utf-8")), ""
    except FileNotFoundError:
        return None, "missing_artifact"
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"unreadable_artifact:{type(exc).__name__}"


def _providers_from_rows(rows: Any) -> list[str]:
    if not isinstance(rows, list):
        return []
    providers = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("skipped"):
            continue
        provider = row.get("provider_role") or row.get("provider")
        if provider:
            providers.append(str(provider))
    return sorted(set(providers))


def _provider_alias_map(profile: dict[str, Any]) -> dict[str, str]:
    aliases = default_provider_alias_map()
    profile_aliases = profile.get("provider_aliases") if isinstance(profile.get("provider_aliases"), dict) else {}
    aliases.update({str(key).strip().lower(): str(value) for key, value in profile_aliases.items() if key and value})
    return aliases


def _provider_role(provider: str, aliases: dict[str, str]) -> str:
    provider = str(provider).strip()
    return aliases.get(provider.lower(), canonical_provider_role(provider))


def _provider_roles_for(providers: list[str], aliases: dict[str, str]) -> list[str]:
    roles = []
    for provider in providers:
        role = _provider_role(provider, aliases)
        if role and role not in roles:
            roles.append(role)
    return roles


def _collect_unit_ids(value: Any) -> set[str]:
    unit_ids: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in UNIT_ID_KEYS and isinstance(item, (str, int, float)) and str(item):
                unit_ids.add(str(item))
            if key in UNIT_CONTAINER_KEYS:
                unit_ids.update(_collect_unit_ids(item))
            elif isinstance(item, dict):
                unit_ids.update(_collect_unit_ids(item))
    elif isinstance(value, list):
        for item in value:
            unit_ids.update(_collect_unit_ids(item))
    return unit_ids


def _metric_groups_present(row: dict[str, Any]) -> dict[str, bool]:
    present: dict[str, bool] = {}
    for group, keys in REQUIRED_UNIT_METRIC_GROUPS.items():
        if group == "failure_class":
            present[group] = any(key in row and row.get(key) is not None for key in keys)
        else:
            present[group] = any(key in row and row.get(key) not in (None, "") for key in keys)
    return present


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _hashish(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    return bool(re.fullmatch(r"[A-Fa-f0-9]{8,128}", text))


def _receipt_value_valid(key: str, value: Any) -> bool:
    if key in {"receipt_hash", "packet_hash", "witness_hash"}:
        return _hashish(value)
    if key == "byte_witness_id":
        return isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9_.:-]{8,128}", value.strip()))
    if key == "attached_witnesses":
        return isinstance(value, list) and len(value) > 0
    if key == "receipt":
        return isinstance(value, dict) and bool(value)
    return value not in (None, "")


def _metric_groups_valid(row: dict[str, Any], present: dict[str, bool]) -> dict[str, bool]:
    quality_values = [
        _as_float(row.get(key))
        for key in REQUIRED_UNIT_METRIC_GROUPS["quality"]
        if key in row
    ]
    latency_values = [
        _as_float(row.get(key))
        for key in REQUIRED_UNIT_METRIC_GROUPS["latency"]
        if key in row
    ]
    failure_values = [
        str(row.get(key, "")).strip().lower()
        for key in REQUIRED_UNIT_METRIC_GROUPS["failure_class"]
        if key in row and row.get(key) is not None
    ]
    receipt_values = [
        _receipt_value_valid(key, row.get(key))
        for key in REQUIRED_UNIT_METRIC_GROUPS["receipt"]
        if key in row
    ]
    return {
        "quality": present.get("quality", False) and any(value is not None and 0.0 <= value <= 1.0 for value in quality_values),
        "latency": present.get("latency", False) and any(value is not None and value >= 0.0 for value in latency_values),
        "failure_class": present.get("failure_class", False) and any(value in VALID_FAILURE_VALUES for value in failure_values),
        "receipt": present.get("receipt", False) and any(receipt_values),
    }


def _unit_id_from_row(row: dict[str, Any]) -> str:
    for key in UNIT_ID_KEYS:
        item = row.get(key)
        if isinstance(item, (str, int, float)) and str(item):
            return str(item)
    return ""


def _metric_row_for_unit(unit_id: str, row: dict[str, Any]) -> dict[str, Any]:
    present = _metric_groups_present(row)
    missing = [group for group, ok in present.items() if not ok]
    valid_groups = _metric_groups_valid(row, present)
    invalid = sorted(group for group in REQUIRED_UNIT_METRIC_GROUPS
                     if present.get(group) and not valid_groups[group])
    return {
        "unit_id": unit_id,
        "present": present,
        "missing": missing,
        "valid_groups": valid_groups,
        "invalid": invalid,
        "complete": not missing,
        "valid": not missing and not invalid,
    }


def _merge_metric_rows(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    present = {
        group: bool(existing.get("present", {}).get(group)) or bool(incoming.get("present", {}).get(group))
        for group in REQUIRED_UNIT_METRIC_GROUPS
    }
    valid_groups = {
        group: bool(existing.get("valid_groups", {}).get(group)) or bool(incoming.get("valid_groups", {}).get(group))
        for group in REQUIRED_UNIT_METRIC_GROUPS
    }
    missing = [group for group, ok in present.items() if not ok]
    invalid = sorted(group for group in REQUIRED_UNIT_METRIC_GROUPS
                     if present.get(group) and not valid_groups[group])
    return {
        "unit_id": existing.get("unit_id") or incoming.get("unit_id", ""),
        "present": present,
        "missing": missing,
        "valid_groups": valid_groups,
        "invalid": invalid,
        "complete": not missing,
        "valid": not missing and not invalid,
    }


def _merge_provider_unit_maps(
    target: dict[str, dict[str, dict[str, Any]]],
    incoming: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, dict[str, dict[str, Any]]]:
    for provider, units in incoming.items():
        provider_rows = target.setdefault(provider, {})
        for unit_id, row in units.items():
            if unit_id in provider_rows:
                provider_rows[unit_id] = _merge_metric_rows(provider_rows[unit_id], row)
            else:
                provider_rows[unit_id] = row
    return target


def _collect_provider_unit_metric_completeness(value: Any, inherited_provider: str = "") -> dict[str, dict[str, dict[str, Any]]]:
    collected: dict[str, dict[str, dict[str, Any]]] = {}
    if isinstance(value, dict):
        if value.get("skipped"):
            return collected
        provider = str(value.get("provider_role") or value.get("provider") or inherited_provider)
        unit_id = _unit_id_from_row(value)
        if provider and unit_id:
            collected.setdefault(provider, {})[unit_id] = _metric_row_for_unit(unit_id, value)
        for key, item in value.items():
            if key in UNIT_CONTAINER_KEYS or isinstance(item, (dict, list)):
                _merge_provider_unit_maps(collected, _collect_provider_unit_metric_completeness(item, provider))
    elif isinstance(value, list):
        for item in value:
            _merge_provider_unit_maps(collected, _collect_provider_unit_metric_completeness(item, inherited_provider))
    return collected


def _normalize_provider_unit_map(
    provider_units: dict[str, dict[str, dict[str, Any]]],
    aliases: dict[str, str],
) -> dict[str, dict[str, dict[str, Any]]]:
    normalized: dict[str, dict[str, dict[str, Any]]] = {}
    for provider, units in provider_units.items():
        role = _provider_role(provider, aliases)
        _merge_provider_unit_maps(normalized, {role: units})
    return normalized


def _collect_unit_metric_completeness(value: Any) -> dict[str, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(value, dict):
        unit_id = ""
        for key in UNIT_ID_KEYS:
            item = value.get(key)
            if isinstance(item, (str, int, float)) and str(item):
                unit_id = str(item)
                break
        if unit_id:
            present = _metric_groups_present(value)
            missing = [group for group, ok in present.items() if not ok]
            valid_groups = _metric_groups_valid(value, present)
            invalid = sorted(group for group in REQUIRED_UNIT_METRIC_GROUPS
                             if present.get(group) and not valid_groups[group])
            rows.append({
                "unit_id": unit_id,
                "present": present,
                "missing": missing,
                "valid_groups": valid_groups,
                "invalid": invalid,
                "complete": not missing,
                "valid": not missing and not invalid,
            })
        for key, item in value.items():
            if key in UNIT_CONTAINER_KEYS or isinstance(item, (dict, list)):
                rows.extend(_collect_unit_metric_completeness(item).values())
    elif isinstance(value, list):
        for item in value:
            rows.extend(_collect_unit_metric_completeness(item).values())

    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        unit_id = str(row["unit_id"])
        if unit_id not in merged:
            merged[unit_id] = row
            continue
        present = {
            group: bool(merged[unit_id]["present"].get(group)) or bool(row["present"].get(group))
            for group in REQUIRED_UNIT_METRIC_GROUPS
        }
        valid_groups = {
            group: bool(merged[unit_id].get("valid_groups", {}).get(group)) or bool(row.get("valid_groups", {}).get(group))
            for group in REQUIRED_UNIT_METRIC_GROUPS
        }
        missing = [group for group, ok in present.items() if not ok]
        invalid = sorted(group for group in REQUIRED_UNIT_METRIC_GROUPS
                         if present.get(group) and not valid_groups[group])
        merged[unit_id] = {
            "unit_id": unit_id,
            "present": present,
            "missing": missing,
            "valid_groups": valid_groups,
            "invalid": invalid,
            "complete": not missing,
            "valid": not missing and not invalid,
        }
    return merged


def observed_artifact_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    schema = str(data.get("schema", ""))
    if schema == "harness.agentic-task-manifest/v1":
        return _agentic_task_manifest_summary(data, path_text)
    if schema == "harness.cross-harness-manifest/v1":
        return _cross_harness_manifest_summary(data, path_text)
    if schema == "harness.cross-harness-task-scorecard/v1":
        return _cross_harness_scorecard_summary(data, path_text)
    if schema == "harness.adapter-runtime-matrix/v1":
        return _adapter_runtime_matrix_summary(data, path_text)
    if schema == "harness.embodied-realtime-multimodal/v1":
        return _embodied_realtime_plan_summary(data, path_text)
    if schema == "harness.model-card-claim-table/v1":
        return _model_card_claim_table_summary(data, path_text)
    if schema == "forum.deep-verify-benchmark/v1":
        return _forum_deep_verify_summary(data, path_text)
    providers: list[str] = []
    row_count = 0
    if schema in {"m7-source-mined-scorecard/v1", "m7-governed-agent-scorecard/v1"}:
        rows = data.get("backend_rows")
        if not isinstance(rows, list) and schema == "m7-source-mined-scorecard/v1":
            rows = data.get("rows")
        providers = _providers_from_rows(rows)
        row_count = len(rows) if isinstance(rows, list) else 0
    elif schema == "unisonai.stateful-provider-matrix/v1":
        rows = data.get("rows")
        providers = _providers_from_rows(rows)
        row_count = len(rows) if isinstance(rows, list) else 0
    elif schema == "classifier-friction-benchmark/v1":
        rows = data.get("results")
        providers = _providers_from_rows(rows)
        row_count = len(rows) if isinstance(rows, list) else 0
    elif schema == "harness.model-release-readiness/v1":
        rows = data.get("models")
        row_count = len(rows) if isinstance(rows, list) else 0
    elif schema == "harness.model-endpoint-profiles/v1":
        rows = data.get("profiles")
        providers = _providers_from_rows(rows)
        row_count = len(rows) if isinstance(rows, list) else 0
    elif schema == "harness.model-endpoint-gate/v1":
        rows = data.get("rows")
        providers = _providers_from_rows(rows)
        row_count = len(rows) if isinstance(rows, list) else 0
    elif schema == "harness.gather-readiness/v1":
        row_count = int(data.get("summary", {}).get("config_count", 0) or 0) if isinstance(data.get("summary"), dict) else 0
    unit_ids = sorted(_collect_unit_ids(data))
    benchmark_ids = _artifact_benchmark_ids_from_schema(schema, unit_ids)
    benchmark_id = benchmark_ids[0] if benchmark_ids else ""
    dataset_lanes = set(_dataset_lanes_for_benchmarks(benchmark_ids))
    dataset_lanes.update(_collect_values_for_keys(data, DATASET_LANE_KEYS))
    pressure_variables = _collect_values_for_keys(data, PRESSURE_VARIABLE_KEYS)
    return {
        "artifact_path": path_text,
        "schema": schema,
        "benchmark_id": benchmark_id,
        "benchmark_ids": benchmark_ids,
        "providers": providers,
        "unit_ids": unit_ids,
        "dataset_lanes": sorted(dataset_lanes),
        "pressure_variables": sorted(pressure_variables),
        "unit_metric_completeness": _collect_unit_metric_completeness(data),
        "provider_unit_metric_completeness": _collect_provider_unit_metric_completeness(data),
        "row_count": row_count,
        "recognized": bool(benchmark_id),
    }


def _agentic_task_manifest_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    task_rows = data.get("task_rows") if isinstance(data.get("task_rows"), list) else []
    dry_rows = data.get("dry_scorecard_rows") if isinstance(data.get("dry_scorecard_rows"), list) else []
    benchmark_ids = sorted({
        str(row.get("benchmark_id", ""))
        for row in task_rows
        if isinstance(row, dict) and row.get("benchmark_id")
    })
    planned_units_by_benchmark: dict[str, list[str]] = {}
    for row in task_rows:
        if not isinstance(row, dict):
            continue
        benchmark_id = str(row.get("benchmark_id", ""))
        unit = str(row.get("coverage_unit") or row.get("task_id") or "")
        if benchmark_id and unit:
            planned_units_by_benchmark.setdefault(benchmark_id, []).append(unit)
    planned_units_by_benchmark = {
        key: sorted(set(value))
        for key, value in sorted(planned_units_by_benchmark.items())
    }
    unit_ids = sorted({
        str(row.get("coverage_unit") or row.get("task_id") or "")
        for row in task_rows
        if isinstance(row, dict) and (row.get("coverage_unit") or row.get("task_id"))
    })
    providers = sorted({
        str(row.get("provider_role", ""))
        for row in dry_rows
        if isinstance(row, dict) and row.get("provider_role")
    } | {
        str(role)
        for role in (data.get("provider_roles") if isinstance(data.get("provider_roles"), list) else [])
        if role
    })
    dataset_lanes = sorted({
        str(row.get("dataset_lane", ""))
        for row in task_rows
        if isinstance(row, dict) and row.get("dataset_lane")
    })
    return {
        "artifact_path": path_text,
        "schema": "harness.agentic-task-manifest/v1",
        "benchmark_id": benchmark_ids[0] if benchmark_ids else "",
        "benchmark_ids": benchmark_ids,
        "providers": providers,
        "unit_ids": unit_ids,
        "dataset_lanes": dataset_lanes,
        "pressure_variables": [],
        "unit_metric_completeness": {},
        "provider_unit_metric_completeness": {},
        "row_count": len(dry_rows),
        "recognized": bool(benchmark_ids),
        "planned_only": True,
        "planned_units_by_benchmark": planned_units_by_benchmark,
        "planned_provider_roles": providers,
        "manifest_task_count": int(data.get("task_count", len(task_rows)) or 0),
        "planned_scorecard_rows": len(dry_rows),
    }


def _cross_harness_manifest_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    task_rows = data.get("task_rows") if isinstance(data.get("task_rows"), list) else []
    dry_rows = data.get("dry_scorecard_rows") if isinstance(data.get("dry_scorecard_rows"), list) else []
    benchmark_ids = sorted({
        str(row.get("benchmark_id", ""))
        for row in task_rows
        if isinstance(row, dict) and row.get("benchmark_id")
    } | {
        str(row.get("benchmark_id", ""))
        for row in dry_rows
        if isinstance(row, dict) and row.get("benchmark_id")
    })
    planned_units_by_benchmark: dict[str, list[str]] = {}
    for row in task_rows:
        if not isinstance(row, dict):
            continue
        benchmark_id = str(row.get("benchmark_id", ""))
        unit = str(row.get("coverage_unit") or row.get("task_id") or "")
        if benchmark_id and unit:
            planned_units_by_benchmark.setdefault(benchmark_id, []).append(unit)
    planned_units_by_benchmark = {
        key: sorted(set(value))
        for key, value in sorted(planned_units_by_benchmark.items())
    }
    unit_ids = sorted({
        str(row.get("coverage_unit") or row.get("task_id") or "")
        for row in task_rows
        if isinstance(row, dict) and (row.get("coverage_unit") or row.get("task_id"))
    })
    providers = sorted({
        str(row.get("provider_role", ""))
        for row in dry_rows
        if isinstance(row, dict) and row.get("provider_role")
    } | {
        str(role)
        for role in (data.get("provider_roles") if isinstance(data.get("provider_roles"), list) else [])
        if role
    })
    dataset_lanes = sorted({
        str(lane)
        for lane in (data.get("dataset_lanes") if isinstance(data.get("dataset_lanes"), list) else [])
        if lane
    } | {
        str(row.get("dataset_lane", ""))
        for row in task_rows
        if isinstance(row, dict) and row.get("dataset_lane")
    })
    return {
        "artifact_path": path_text,
        "schema": "harness.cross-harness-manifest/v1",
        "benchmark_id": benchmark_ids[0] if benchmark_ids else "",
        "benchmark_ids": benchmark_ids,
        "providers": providers,
        "unit_ids": unit_ids,
        "dataset_lanes": dataset_lanes,
        "pressure_variables": [],
        "unit_metric_completeness": {},
        "provider_unit_metric_completeness": {},
        "row_count": len(dry_rows),
        "recognized": bool(benchmark_ids),
        "planned_only": True,
        "planned_units_by_benchmark": planned_units_by_benchmark,
        "planned_provider_roles": providers,
        "manifest_task_count": int(data.get("task_count", len(task_rows)) or 0),
        "planned_scorecard_rows": len(dry_rows),
    }


def _cross_harness_scorecard_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    rows = data.get("rows") if isinstance(data.get("rows"), list) else [data]
    row_dicts = [row for row in rows if isinstance(row, dict)]
    benchmark_ids = sorted({
        str(row.get("benchmark_id", ""))
        for row in row_dicts
        if row.get("benchmark_id")
    })
    unit_ids = sorted({
        str(row.get("coverage_unit") or row.get("task_id") or "")
        for row in row_dicts
        if row.get("coverage_unit") or row.get("task_id")
    })
    providers = sorted({
        str(row.get("provider_role", ""))
        for row in row_dicts
        if row.get("provider_role")
    })
    planned_only = all(
        str(row.get("execution_mode", "")) == "manifest_only" or str(row.get("status", "")) == "planned"
        for row in row_dicts
    )
    benchmark_id = benchmark_ids[0] if benchmark_ids else ""
    return {
        "artifact_path": path_text,
        "schema": "harness.cross-harness-task-scorecard/v1",
        "benchmark_id": benchmark_id,
        "benchmark_ids": benchmark_ids,
        "providers": providers,
        "unit_ids": unit_ids,
        "dataset_lanes": _dataset_lanes_for_benchmarks(benchmark_ids),
        "pressure_variables": [],
        "unit_metric_completeness": {},
        "provider_unit_metric_completeness": {},
        "row_count": len(row_dicts),
        "recognized": bool(benchmark_ids),
        "planned_only": planned_only,
        "planned_units_by_benchmark": {benchmark_id: unit_ids} if planned_only and benchmark_id else {},
        "planned_provider_roles": providers if planned_only else [],
        "manifest_task_count": len(unit_ids) if planned_only else 0,
        "planned_scorecard_rows": len(row_dicts) if planned_only else 0,
    }


def _forum_deep_verify_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    cases = data.get("cases") if isinstance(data.get("cases"), list) else []
    benchmark_ids = ["forum_ledger_deep_verify_scaling"]
    unit_ids = []
    pressure_variables = set()
    for row in cases:
        if not isinstance(row, dict):
            continue
        entry_count = row.get("entry_count", "")
        payload_bytes = row.get("payload_body_bytes", "")
        storage = row.get("storage_mode", "")
        redaction = row.get("redaction_ratio", "")
        if entry_count != "":
            pressure_variables.add("entry-count-scale")
        if payload_bytes != "":
            pressure_variables.add("payload-byte-scale")
        if redaction != "":
            pressure_variables.add("redaction-ratio")
        if storage:
            unit_ids.append(f"{storage}:{entry_count}:{payload_bytes}:redact={redaction}")
    return {
        "artifact_path": path_text,
        "schema": "forum.deep-verify-benchmark/v1",
        "benchmark_id": "forum_ledger_deep_verify_scaling",
        "benchmark_ids": benchmark_ids,
        "providers": [],
        "unit_ids": sorted(set(unit_ids)),
        "dataset_lanes": _dataset_lanes_for_benchmarks(benchmark_ids),
        "pressure_variables": sorted(pressure_variables),
        "unit_metric_completeness": {},
        "provider_unit_metric_completeness": {},
        "row_count": len(cases),
        "recognized": True,
    }


def _embodied_realtime_plan_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    rows = data.get("dry_scorecard_rows") if isinstance(data.get("dry_scorecard_rows"), list) else []
    benchmark_id = str(data.get("benchmark_id", "embodied_realtime_multimodal_pressure"))
    units = sorted({
        str(row.get("coverage_unit", ""))
        for row in rows
        if isinstance(row, dict) and row.get("coverage_unit")
    })
    providers = sorted({
        str(row.get("provider_role", ""))
        for row in rows
        if isinstance(row, dict) and row.get("provider_role")
    })
    dataset_lanes = sorted({
        str(lane)
        for lane in (data.get("dataset_lanes") if isinstance(data.get("dataset_lanes"), list) else [])
        if lane
    })
    pressure_variables = sorted({
        str(variable)
        for variable in (data.get("pressure_variables") if isinstance(data.get("pressure_variables"), list) else [])
        if variable
    })
    return {
        "artifact_path": path_text,
        "schema": "harness.embodied-realtime-multimodal/v1",
        "benchmark_id": benchmark_id,
        "benchmark_ids": [benchmark_id] if benchmark_id else [],
        "providers": providers,
        "unit_ids": units,
        "dataset_lanes": dataset_lanes,
        "pressure_variables": pressure_variables,
        "unit_metric_completeness": {},
        "provider_unit_metric_completeness": {},
        "row_count": len(rows),
        "recognized": bool(benchmark_id),
        "planned_only": True,
        "planned_units_by_benchmark": {benchmark_id: units} if benchmark_id else {},
        "planned_provider_roles": providers,
        "manifest_task_count": int(data.get("summary", {}).get("planned_probe_rows", len(rows)) or 0)
        if isinstance(data.get("summary"), dict)
        else len(rows),
        "planned_scorecard_rows": len(rows),
    }


def _adapter_runtime_matrix_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    rows = data.get("runtime_rows") if isinstance(data.get("runtime_rows"), list) else []
    benchmark_id = "cross_harness_reproducibility_matrix"
    units = sorted({
        str(row.get("provider_role", ""))
        for row in rows
        if isinstance(row, dict) and row.get("provider_role")
    })
    return {
        "artifact_path": path_text,
        "schema": "harness.adapter-runtime-matrix/v1",
        "benchmark_id": benchmark_id,
        "benchmark_ids": [benchmark_id],
        "providers": units,
        "unit_ids": units,
        "dataset_lanes": ["cross_harness_reproducibility", "endpoint_release_gates"],
        "pressure_variables": ["adapter-discovery", "account-auth", "endpoint-profile", "endpoint-gate"],
        "unit_metric_completeness": {},
        "provider_unit_metric_completeness": {},
        "row_count": len(rows),
        "recognized": True,
        "planned_only": True,
        "planned_units_by_benchmark": {benchmark_id: units},
        "planned_provider_roles": units,
        "manifest_task_count": len(rows),
        "planned_scorecard_rows": 0,
    }


def _model_card_claim_table_summary(data: dict[str, Any], path_text: str) -> dict[str, Any]:
    rows = data.get("model_rows") if isinstance(data.get("model_rows"), list) else []
    benchmark_id = "embodied_realtime_multimodal_pressure"
    unit_ids = sorted({
        str(row.get("model_id", ""))
        for row in rows
        if isinstance(row, dict) and row.get("model_id")
    })
    claim_fields = [
        field
        for row in rows
        if isinstance(row, dict)
        for field in (row.get("claim_fields") if isinstance(row.get("claim_fields"), list) else [])
        if isinstance(field, dict)
    ]
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    return {
        "artifact_path": path_text,
        "schema": "harness.model-card-claim-table/v1",
        "benchmark_id": benchmark_id,
        "benchmark_ids": [benchmark_id],
        "providers": [],
        "unit_ids": unit_ids,
        "dataset_lanes": ["embodied_realtime_multimodal", "local_resource_pressure"],
        "pressure_variables": ["model-card-unverified"],
        "unit_metric_completeness": {},
        "provider_unit_metric_completeness": {},
        "row_count": len(claim_fields),
        "recognized": True,
        "planned_only": True,
        "planned_units_by_benchmark": {benchmark_id: unit_ids},
        "planned_provider_roles": [],
        "manifest_task_count": int(summary.get("model_candidates", len(rows)) or 0),
        "planned_scorecard_rows": 0,
        "claim_fields": int(summary.get("claim_fields", len(claim_fields)) or 0),
        "unresolved_fields": int(summary.get("unresolved_fields", 0) or 0),
        "all_primary_sourced": bool(summary.get("all_primary_sourced")),
    }


def _declared_benchmarks(profile: dict[str, Any]) -> list[dict[str, Any]]:
    rows = profile.get("benchmarks") if isinstance(profile.get("benchmarks"), list) else []
    return [row for row in rows if isinstance(row, dict)]


def build_coverage_report(
    profile: dict[str, Any],
    *,
    profile_path: str,
    artifact_paths: list[str],
) -> dict[str, Any]:
    declared = _declared_benchmarks(profile)
    runnable = [row for row in declared if row.get("status") == "runnable"]
    declared_ids = [str(row.get("id", "")) for row in declared if row.get("id")]
    runnable_ids = [str(row.get("id", "")) for row in runnable if row.get("id")]
    declared_units_by_benchmark = {
        str(row.get("id", "")): [str(unit) for unit in row.get("coverage_units", []) if unit]
        for row in declared
        if row.get("id") and isinstance(row.get("coverage_units"), list)
    }
    aliases = _provider_alias_map(profile)
    raw_expected_providers = [str(item) for item in profile.get("providers", []) if item] if isinstance(profile.get("providers"), list) else []
    expected_providers = [str(item) for item in profile.get("expected_provider_roles", []) if item] if isinstance(profile.get("expected_provider_roles"), list) else _provider_roles_for(raw_expected_providers, aliases)

    observed: list[dict[str, Any]] = []
    load_errors: list[dict[str, str]] = []
    for path_text in artifact_paths:
        data, error = _load_json(path_text)
        if data is None:
            load_errors.append({"artifact_path": path_text, "error": error})
            continue
        observed.append(observed_artifact_summary(data, path_text))
    executed_observed = [row for row in observed if not row.get("planned_only")]
    planned_observed = [row for row in observed if row.get("planned_only")]

    observed_benchmark_ids = sorted({
        benchmark_id
        for row in executed_observed
        for benchmark_id in _artifact_benchmark_ids(row)
        if benchmark_id
    })
    planned_benchmark_ids = sorted({
        benchmark_id
        for row in planned_observed
        for benchmark_id in _artifact_benchmark_ids(row)
        if benchmark_id
    })
    planned_units_by_benchmark: dict[str, list[str]] = {}
    for row in planned_observed:
        for benchmark_id, units in (row.get("planned_units_by_benchmark") or {}).items():
            existing = set(planned_units_by_benchmark.get(str(benchmark_id), []))
            existing.update(str(unit) for unit in units if unit)
            planned_units_by_benchmark[str(benchmark_id)] = sorted(existing)
    planned_provider_roles = sorted({
        str(provider)
        for row in planned_observed
        for provider in row.get("planned_provider_roles", [])
        if provider
    })
    observed_units_by_benchmark: dict[str, list[str]] = {}
    unit_metric_completeness_by_benchmark: dict[str, dict[str, dict[str, Any]]] = {}
    provider_unit_metric_by_benchmark: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    for row in executed_observed:
        for benchmark_id in _artifact_benchmark_ids(row):
            if not benchmark_id:
                continue
            existing = set(observed_units_by_benchmark.get(benchmark_id, []))
            existing.update(str(unit) for unit in row.get("unit_ids", []) if unit)
            observed_units_by_benchmark[benchmark_id] = sorted(existing)
            metric_rows = unit_metric_completeness_by_benchmark.setdefault(benchmark_id, {})
            for unit_id, metric_row in (row.get("unit_metric_completeness") or {}).items():
                if unit_id not in metric_rows:
                    metric_rows[unit_id] = metric_row
                    continue
                metric_rows[unit_id] = _merge_metric_rows(metric_rows[unit_id], metric_row)
            provider_rows = provider_unit_metric_by_benchmark.setdefault(benchmark_id, {})
            _merge_provider_unit_maps(provider_rows, _normalize_provider_unit_map(row.get("provider_unit_metric_completeness") or {}, aliases))
    declared_dataset_lanes = _declared_dataset_lanes(profile)
    declared_pressure_variables = _declared_pressure_variables(profile)
    observed_dataset_lanes = sorted({
        str(lane)
        for row in executed_observed
        for lane in row.get("dataset_lanes", [])
        if lane
    })
    planned_dataset_lanes = sorted({
        str(lane)
        for row in planned_observed
        for lane in row.get("dataset_lanes", [])
        if lane
    })
    observed_pressure_variables = sorted({
        str(variable)
        for row in executed_observed
        for variable in row.get("pressure_variables", [])
        if variable
    })
    missing_dataset_lanes = [lane for lane in declared_dataset_lanes if lane not in observed_dataset_lanes]
    missing_pressure_variables = [variable for variable in declared_pressure_variables if variable not in observed_pressure_variables]
    missing_units_by_benchmark = {
        benchmark_id: [
            unit
            for unit in units
            if unit not in observed_units_by_benchmark.get(benchmark_id, [])
        ]
        for benchmark_id, units in declared_units_by_benchmark.items()
        if benchmark_id in runnable_ids
    }
    missing_units_by_benchmark = {
        benchmark_id: units
        for benchmark_id, units in missing_units_by_benchmark.items()
        if units
    }
    incomplete_units_by_benchmark: dict[str, dict[str, list[str]]] = {}
    invalid_units_by_benchmark: dict[str, dict[str, list[str]]] = {}
    observed_provider_units_by_benchmark: dict[str, dict[str, list[str]]] = {}
    missing_provider_units_by_benchmark: dict[str, dict[str, list[str]]] = {}
    invalid_provider_units_by_benchmark: dict[str, dict[str, dict[str, list[str]]]] = {}
    complete_unit_count = 0
    valid_unit_count = 0
    observed_declared_unit_count = 0
    expected_provider_unit_count = 0
    observed_provider_unit_count = 0
    valid_provider_unit_count = 0
    for benchmark_id in runnable_ids:
        declared_units = set(declared_units_by_benchmark.get(benchmark_id, []))
        expected_provider_unit_count += len(expected_providers) * len(declared_units)
        for unit_id in sorted(declared_units & set(observed_units_by_benchmark.get(benchmark_id, []))):
            observed_declared_unit_count += 1
            metric_row = unit_metric_completeness_by_benchmark.get(benchmark_id, {}).get(unit_id)
            if metric_row and metric_row.get("complete"):
                complete_unit_count += 1
                if metric_row.get("valid"):
                    valid_unit_count += 1
                else:
                    invalid_units_by_benchmark.setdefault(benchmark_id, {})[unit_id] = list(metric_row.get("invalid", []))
            else:
                missing = metric_row.get("missing", sorted(REQUIRED_UNIT_METRIC_GROUPS)) if metric_row else sorted(REQUIRED_UNIT_METRIC_GROUPS)
                incomplete_units_by_benchmark.setdefault(benchmark_id, {})[unit_id] = list(missing)
        for provider in expected_providers:
            provider_rows = provider_unit_metric_by_benchmark.get(benchmark_id, {}).get(provider, {})
            observed_units = sorted(declared_units & set(provider_rows.keys()))
            if observed_units:
                observed_provider_units_by_benchmark.setdefault(benchmark_id, {})[provider] = observed_units
            missing_units = sorted(declared_units - set(observed_units))
            if missing_units:
                missing_provider_units_by_benchmark.setdefault(benchmark_id, {})[provider] = missing_units
            for unit_id in observed_units:
                observed_provider_unit_count += 1
                metric_row = provider_rows.get(unit_id, {})
                if metric_row.get("valid"):
                    valid_provider_unit_count += 1
                else:
                    reasons = sorted(set((metric_row.get("missing") or []) + (metric_row.get("invalid") or [])))
                    invalid_provider_units_by_benchmark.setdefault(benchmark_id, {}).setdefault(provider, {})[unit_id] = reasons
    observed_providers = sorted({
        role
        for row in executed_observed
        for role in _provider_roles_for(row.get("providers", []), aliases)
        if role
    })
    missing_runnable = [benchmark_id for benchmark_id in runnable_ids if benchmark_id not in observed_benchmark_ids]
    missing_providers = [provider for provider in expected_providers if provider not in observed_providers]
    benchmark_denominator = len(runnable_ids)
    provider_denominator = len(expected_providers)
    unit_denominator = sum(len(declared_units_by_benchmark.get(benchmark_id, [])) for benchmark_id in runnable_ids)
    observed_unit_count = sum(
        len(set(declared_units_by_benchmark.get(benchmark_id, [])) & set(observed_units_by_benchmark.get(benchmark_id, [])))
        for benchmark_id in runnable_ids
    )
    benchmark_rate = round((benchmark_denominator - len(missing_runnable)) / benchmark_denominator, 4) if benchmark_denominator else 1.0
    provider_rate = round((provider_denominator - len(missing_providers)) / provider_denominator, 4) if provider_denominator else 1.0
    unit_rate = round(observed_unit_count / unit_denominator, 4) if unit_denominator else 1.0
    unit_metric_rate = round(complete_unit_count / observed_declared_unit_count, 4) if observed_declared_unit_count else 0.0
    unit_validity_rate = round(valid_unit_count / observed_declared_unit_count, 4) if observed_declared_unit_count else 0.0
    provider_unit_coverage_rate = round(observed_provider_unit_count / expected_provider_unit_count, 4) if expected_provider_unit_count else 1.0
    provider_unit_validity_rate = round(valid_provider_unit_count / expected_provider_unit_count, 4) if expected_provider_unit_count else 1.0
    dataset_lane_coverage_rate = round((len(declared_dataset_lanes) - len(missing_dataset_lanes)) / len(declared_dataset_lanes), 4) if declared_dataset_lanes else 1.0
    pressure_variable_coverage_rate = round((len(declared_pressure_variables) - len(missing_pressure_variables)) / len(declared_pressure_variables), 4) if declared_pressure_variables else 1.0
    verdict = "COVERAGE_COMPLETE" if not missing_runnable and not missing_providers and not missing_units_by_benchmark and not incomplete_units_by_benchmark and not invalid_units_by_benchmark and not missing_provider_units_by_benchmark and not invalid_provider_units_by_benchmark and not missing_dataset_lanes and not missing_pressure_variables and not load_errors else "COVERAGE_PARTIAL"
    return {
        "schema": "harness.benchmark-profile-coverage/v1",
        "timestamp_utc": _now(),
        "profile_path": profile_path,
        "profile_schema": profile.get("schema", ""),
        "profile_id": profile.get("profile_id", ""),
        "declared_benchmark_ids": declared_ids,
        "declared_runnable_benchmark_ids": runnable_ids,
        "observed_artifacts": observed,
        "load_errors": load_errors,
        "summary": {
            "verdict": verdict,
            "artifact_paths": len(artifact_paths),
            "loaded_artifacts": len(observed),
            "planned_only_artifacts": len(planned_observed),
            "load_errors": len(load_errors),
            "declared_benchmarks": len(declared_ids),
            "declared_runnable_benchmarks": len(runnable_ids),
            "observed_benchmarks": len(observed_benchmark_ids),
            "observed_benchmark_ids": observed_benchmark_ids,
            "planned_benchmark_ids": planned_benchmark_ids,
            "missing_runnable_benchmark_ids": missing_runnable,
            "benchmark_coverage_rate": benchmark_rate,
            "declared_units_by_benchmark": declared_units_by_benchmark,
            "observed_units_by_benchmark": observed_units_by_benchmark,
            "planned_units_by_benchmark": planned_units_by_benchmark,
            "missing_units_by_benchmark": missing_units_by_benchmark,
            "unit_coverage_rate": unit_rate,
            "unit_metric_completeness_by_benchmark": unit_metric_completeness_by_benchmark,
            "incomplete_units_by_benchmark": incomplete_units_by_benchmark,
            "unit_metric_completeness_rate": unit_metric_rate,
            "invalid_units_by_benchmark": invalid_units_by_benchmark,
            "unit_metric_validity_rate": unit_validity_rate,
            "observed_provider_units_by_benchmark": observed_provider_units_by_benchmark,
            "missing_provider_units_by_benchmark": missing_provider_units_by_benchmark,
            "invalid_provider_units_by_benchmark": invalid_provider_units_by_benchmark,
            "provider_unit_coverage_rate": provider_unit_coverage_rate,
            "provider_unit_validity_rate": provider_unit_validity_rate,
            "expected_providers": expected_providers,
            "raw_expected_providers": raw_expected_providers,
            "observed_providers": observed_providers,
            "planned_provider_roles": planned_provider_roles,
            "missing_providers": missing_providers,
            "provider_coverage_rate": provider_rate,
            "provider_aliases": aliases,
            "metric_weight_sum": _safe_float(profile.get("metric_weight_sum")),
            "dataset_lane_weight_sum": _safe_float(profile.get("dataset_lane_weight_sum")),
            "declared_dataset_lanes": declared_dataset_lanes,
            "observed_dataset_lanes": observed_dataset_lanes,
            "planned_dataset_lanes": planned_dataset_lanes,
            "missing_dataset_lanes": missing_dataset_lanes,
            "dataset_lane_coverage_rate": dataset_lane_coverage_rate,
            "declared_pressure_variables": declared_pressure_variables,
            "observed_pressure_variables": observed_pressure_variables,
            "missing_pressure_variables": missing_pressure_variables,
            "pressure_variable_coverage_rate": pressure_variable_coverage_rate,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Benchmark profile coverage",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Timestamp UTC: `{report['timestamp_utc']}`",
        f"- Profile: `{report['profile_path']}`",
        f"- Verdict: `{summary['verdict']}`",
        f"- Benchmark coverage rate: `{summary['benchmark_coverage_rate']}`",
        f"- Unit coverage rate: `{summary['unit_coverage_rate']}`",
        f"- Unit metric completeness rate: `{summary['unit_metric_completeness_rate']}`",
        f"- Unit metric validity rate: `{summary['unit_metric_validity_rate']}`",
        f"- Provider coverage rate: `{summary['provider_coverage_rate']}`",
        f"- Provider-unit coverage rate: `{summary['provider_unit_coverage_rate']}`",
        f"- Provider-unit validity rate: `{summary['provider_unit_validity_rate']}`",
        f"- Dataset lane coverage rate: `{summary['dataset_lane_coverage_rate']}`",
        f"- Pressure variable coverage rate: `{summary['pressure_variable_coverage_rate']}`",
        f"- Missing runnable benchmarks: `{', '.join(summary['missing_runnable_benchmark_ids'])}`",
        f"- Missing units: `{json.dumps(summary['missing_units_by_benchmark'], sort_keys=True)}`",
        f"- Missing dataset lanes: `{', '.join(summary['missing_dataset_lanes'])}`",
        f"- Missing pressure variables: `{', '.join(summary['missing_pressure_variables'])}`",
        f"- Incomplete units: `{json.dumps(summary['incomplete_units_by_benchmark'], sort_keys=True)}`",
        f"- Invalid units: `{json.dumps(summary['invalid_units_by_benchmark'], sort_keys=True)}`",
        f"- Missing provider units: `{json.dumps(summary['missing_provider_units_by_benchmark'], sort_keys=True)}`",
        f"- Invalid provider units: `{json.dumps(summary['invalid_provider_units_by_benchmark'], sort_keys=True)}`",
        f"- Missing providers: `{', '.join(summary['missing_providers'])}`",
        f"- Planned-only artifacts: `{summary['planned_only_artifacts']}`",
        f"- Planned benchmarks: `{', '.join(summary['planned_benchmark_ids'])}`",
        f"- Planned units: `{json.dumps(summary['planned_units_by_benchmark'], sort_keys=True)}`",
        f"- Planned provider roles: `{', '.join(summary['planned_provider_roles'])}`",
        f"- Planned dataset lanes: `{', '.join(summary['planned_dataset_lanes'])}`",
        "",
        "## Observed artifacts",
        "",
        "| Benchmark | Mode | Schema | Providers | Dataset lanes | Pressure variables | Units | Rows | Artifact |",
        "|---|---|---|---|---|---|---:|---:|---|",
    ]
    for row in report["observed_artifacts"]:
        lines.append(
                "| {benchmark} | {mode} | {schema} | {providers} | {lanes} | {pressure} | {units} | {rows} | {artifact} |".format(
                benchmark=row.get("benchmark_id", ""),
                mode="planned_only" if row.get("planned_only") else "executed",
                schema=row.get("schema", ""),
                providers=", ".join(row.get("providers", [])),
                lanes=", ".join(row.get("dataset_lanes", [])),
                pressure=", ".join(row.get("pressure_variables", [])),
                units=len(row.get("unit_ids", [])),
                rows=row.get("row_count", 0),
                artifact=row.get("artifact_path", ""),
            )
        )
    if report["load_errors"]:
        lines.extend(["", "## Load errors", "", "| Artifact | Error |", "|---|---|"])
        for row in report["load_errors"]:
            lines.append(f"| {row.get('artifact_path', '')} | {row.get('error', '')} |")
    return "\n".join(lines) + "\n"


def store_report(
    report: dict[str, Any],
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
            kind="benchmark_profile_coverage",
            body=report,
            run_id=run_id,
            verdict=report["summary"]["verdict"],
        )
    ]
    for path_text, label in artifacts:
        if path_text and Path(path_text).exists():
            outputs.append(store.copy_artifact(Path(path_text), run_id=run_id, label=label))
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--artifacts", default="")
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    profile, error = _load_json(args.profile)
    if profile is None:
        profile = {
            "schema": "",
            "profile_id": "",
            "providers": [],
            "benchmarks": [],
            "metric_weight_sum": 0.0,
        }
        artifact_paths: list[str] = []
        report = build_coverage_report(profile, profile_path=args.profile, artifact_paths=artifact_paths)
        report["load_errors"].append({"artifact_path": args.profile, "error": error})
        report["summary"]["load_errors"] = len(report["load_errors"])
        report["summary"]["verdict"] = "COVERAGE_UNVERIFIABLE"
    else:
        report = build_coverage_report(
            profile,
            profile_path=args.profile,
            artifact_paths=_split_paths(args.artifacts),
        )
    json_text = json.dumps(report, indent=2, sort_keys=True)
    md_text = render_markdown(report)
    json_path = _write(args.out, json_text)
    md_path = _write(args.markdown_out, md_text)
    store_outputs = store_report(
        report,
        store_root=args.store_root,
        run_id=args.run_id,
        artifacts=[
            (json_path, "benchmark-profile-coverage-json"),
            (md_path, "benchmark-profile-coverage-markdown"),
        ],
    )
    if store_outputs:
        report = {**report, "store_outputs": store_outputs}
        json_text = json.dumps(report, indent=2, sort_keys=True)
    print(json_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
