"""Post-run validator for the original agt-003 cross-harness comparison."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from harness.cross_harness_executor import comparison_key
from harness.cross_harness_postrun_checks import (
    RUN_SCHEMA,
    SCORECARD_SCHEMA,
    artifact_content_checks,
    cell_key,
    declared_intent,
    indexed,
    json_token,
    load_bound_intent,
    load_index,
    state,
    top_json,
)
from harness.cross_harness_postrun_paths import safe_run_root

SCHEMA = "harness.cross-harness-postrun-comparison/v1"


def _empty_report(reasons: set[str], extra_rows: int = 0) -> dict[str, Any]:
    return {"schema": SCHEMA, "decision": "evidence_gap", "reasons": sorted(reasons),
            "counts": {"intended_attempts": 0, "eligible_scored": 0, "gaps": 0, "extra_rows": extra_rows},
            "cells": [], "quality_ranking": None, "comparison_scope": "not_available",
            "denominator_state": "unknown_invalid_declared_dimensions",
            "enforcement": {"equivalence": "unknown"}}


def validate_postrun_comparison(run_root: str | Path) -> dict[str, Any]:
    reasons: set[str] = set()
    root, root_error = safe_run_root(run_root)
    if root_error:
        return _empty_report({root_error})
    run, run_path = top_json(root, "run.json", "run_receipt_missing", "run_receipt_malformed", reasons)
    scorecard, score_path = top_json(root, "comparison-input.json", "scorecard_missing", "scorecard_malformed", reasons)
    if scorecard is None:
        return _empty_report(reasons)
    if run and run.get("schema") != RUN_SCHEMA:
        reasons.add("run_schema_mismatch")
    if scorecard.get("schema") != SCORECARD_SCHEMA:
        reasons.add("scorecard_schema_mismatch")
    rows = scorecard.get("rows")
    if not isinstance(rows, list):
        reasons.add("scorecard_rows_malformed")
        rows = []
    if run and isinstance(run.get("rows"), list) and run.get("rows") != rows:
        reasons.add("run_scorecard_rows_mismatch")
    index = load_index(root, reasons)
    indexed(root, run_path, index, reasons)
    indexed(root, score_path, index, reasons)
    intent, intent_sha = load_bound_intent(root, run, scorecard, index, reasons)
    if scorecard.get("source_tree_state") != "clean" or not run or run.get("source_tree_state") != "clean":
        reasons.add("source_tree_not_clean")
    before, after = (run or {}).get("source_snapshot_before"), (run or {}).get("source_snapshot_after")
    if before != after or not isinstance(before, dict) or not before.get("sha256"):
        reasons.add("source_tree_not_clean")
    if intent is None:
        return _empty_report(reasons, len(rows))
    seen_intended, intended, declared_count = declared_intent(intent, reasons)
    by_key: dict[tuple[str, str, int, str], list[dict[str, Any]]] = {}
    extra_rows = 0
    for row in rows:
        if not isinstance(row, dict):
            reasons.add("row_malformed")
            continue
        key = cell_key(row, reasons, "row_cell_malformed")
        if key is None:
            continue
        if key not in seen_intended:
            extra_rows += 1
            reasons.add("extra_observed_row")
            continue
        by_key.setdefault(key, []).append(row)
    out_cells, eligible = [], 0
    enforcement_hashes: set[str] = set()
    parity_groups: dict[tuple[str, int], dict[str, set[str]]] = {}
    parity_fields = ("task_set_id", "task_id", "raw_prompt_sha256", "input_sha256s", "runtime_context_sha256", "tool_policy_sha256", "schema")
    for key, cell in intended:
        matches = by_key.get(key, [])
        if not matches:
            reasons.add("missing_row")
            out_cells.append({"provider_role": key[3], "task_id": key[1], "repetition": key[2], "state": "missing_row"})
            continue
        if len(matches) > 1:
            reasons.add("duplicate_observed_cell")
            out_cells.append({"provider_role": key[3], "task_id": key[1], "repetition": key[2], "state": "duplicate_row"})
            continue
        row, row_reasons = matches[0], set()
        expected = {"schema": SCORECARD_SCHEMA, **{f: cell.get(f) for f in ("task_set_id", "task_id", "repetition", "provider_role", "harness_id", "adapter_id", "model_id", "requested_model_reference")}}
        for field, value in expected.items():
            if row.get(field) != value:
                row_reasons.add("row_identity_mismatch")
        for field in ("run_id", "phase", "execution_mode", "cache_state", "source_commit", "source_snapshot_sha256"):
            if row.get(field) != intent.get(field):
                row_reasons.add("row_intent_mismatch")
        if row.get("intended_matrix_sha256") != intent_sha:
            row_reasons.add("row_intent_mismatch")
        try:
            if row.get("comparison_key") != comparison_key(row):
                row_reasons.add("comparison_key_mismatch")
        except Exception:
            row_reasons.add("comparison_key_mismatch")
        if isinstance(before, dict) and row.get("source_snapshot_sha256") != before.get("sha256"):
            row_reasons.add("source_tree_not_clean")
        artifact_content_checks(root, row, index, row_reasons)
        is_scored, cell_state = state(row, row_reasons)
        reasons.update(row_reasons)
        if is_scored and not row_reasons:
            eligible += 1
        group = parity_groups.setdefault((key[1], key[2]), {field: set() for field in parity_fields})
        for field in parity_fields:
            group[field].add(json_token(row.get(field)))
        if row.get("enforcement_sha256"):
            enforcement_hashes.add(str(row.get("enforcement_sha256")))
        out_cells.append({"provider_role": key[3], "task_id": key[1], "repetition": key[2], "state": cell_state,
                          "execution_state": row.get("execution_state"), "oracle_state": row.get("oracle_state"),
                          "primary_outcome": row.get("primary_outcome"), "status": row.get("status"),
                          "reasons": sorted(row_reasons)})
    for group in parity_groups.values():
        for field, values in group.items():
            if len(values) > 1:
                reasons.add(f"parity_mismatch:{field}")
    intended_attempts = declared_count if declared_count is not None else 0
    gaps = max((declared_count if declared_count is not None else len(intended)) - eligible, 0)
    planned = bool(rows) and all(str(row.get("execution_mode", "")) == "manifest_only" or str(row.get("status", "")) == "planned" for row in rows if isinstance(row, dict))
    decision = "completed_comparison" if not reasons and gaps == 0 else ("planned_only" if planned and "legacy_intent_unverified" not in reasons else "evidence_gap")
    equivalence = "non_equivalent" if len(enforcement_hashes) > 1 else ("not_verified" if enforcement_hashes else "unknown")
    return {"schema": SCHEMA, "decision": decision, "reasons": sorted(reasons),
            "counts": {"intended_attempts": intended_attempts, "eligible_scored": eligible, "gaps": gaps, "extra_rows": extra_rows},
            "cells": out_cells, "quality_ranking": None,
            "denominator_state": "declared_product" if declared_count is not None else "unknown_invalid_declared_dimensions",
            "comparison_scope": "orchestration_stack_observation" if decision == "completed_comparison" else "not_available",
            "enforcement": {"equivalence": equivalence, "hashes": sorted(enforcement_hashes)},
            "does_not_prove": ["SHA-256 values identify local bytes; they are not authenticity proof by themselves.",
                               "This validator does not run providers or prove the original comparison executed outside the supplied run root."]}
