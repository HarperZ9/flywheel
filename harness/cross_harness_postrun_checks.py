"""Validation checks used by the cross-harness post-run CLI."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from harness.cross_harness_artifacts import recheck_attempt_receipt
from harness.cross_harness_executor import comparison_key, derive_primary_outcome
from harness.cross_harness_postrun_intent import SCHEMA as INTENT_SCHEMA
from harness.cross_harness_postrun_paths import canonical, read_json_file, safe_existing_path, safe_read_json, sha_file

SCORECARD_SCHEMA = "harness.cross-harness-task-scorecard/v1"
RUN_SCHEMA = "harness.cross-harness-run-receipt/v1"
INDEX_SCHEMA = "harness.cross-harness-artifact-index/v1"
TASK_ID = "agt-003-codex-flywheel-shared-task"
ORIGINAL_ROLES = ("codex_harness", "flywheel_harness")
ORIGINAL_IDENTITIES = {
    "codex_harness": {"harness_id": "codex", "adapter_id": "codex_cli_json/v1",
                       "model_id": "gpt-5.3-codex-spark", "requested_model_reference": "gpt-5.3-codex-spark"},
    "flywheel_harness": {"harness_id": "flywheel", "adapter_id": "flywheel_router/v1",
                          "model_id": "gpt-5.3-codex-spark", "requested_model_reference": "gpt-5.3-codex-spark"},
}


def json_token(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def relative(root: Path, path: Path) -> str:
    return path.resolve(strict=True).relative_to(root.resolve(strict=True)).as_posix()


def top_json(root: Path, name: str, missing: str, malformed: str,
             reasons: set[str]) -> tuple[dict[str, Any] | None, Path | None]:
    data, error, path = safe_read_json(root, name)
    if not error:
        return data, path
    reasons.add(missing if error == "path_missing" else malformed if error == "malformed" else error)
    return None, path


def load_index(root: Path, reasons: set[str]) -> dict[str, str]:
    data, error, _path = safe_read_json(root, "artifact-index.json")
    if error:
        reasons.add("artifact_index_missing" if error == "path_missing" else
                    "artifact_index_malformed" if error == "malformed" else error)
        return {}
    if data is None or data.get("schema") != INDEX_SCHEMA:
        reasons.add("artifact_index_schema_mismatch")
        return {}
    out: dict[str, str] = {}
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, list):
        reasons.add("artifact_index_malformed")
        return out
    for item in artifacts:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("sha256"), str):
            reasons.add("artifact_index_malformed")
            continue
        path, code = safe_existing_path(root, item["path"], kind="file")
        if code:
            reasons.add(code)
            continue
        rel = relative(root, path)
        if rel in out:
            reasons.add("artifact_index_duplicate_path")
        out[rel] = item["sha256"]
        if item["sha256"] != sha_file(path):
            reasons.add("artifact_index_mismatch")
    return out


def indexed(root: Path, path: Path | None, index: dict[str, str], reasons: set[str], code="artifact_index_mismatch") -> None:
    if path is None:
        return
    try:
        rel = relative(root, path)
    except (OSError, ValueError):
        reasons.add(code)
        return
    if index.get(rel) != sha_file(path):
        reasons.add(code)


def load_bound_intent(root: Path, run: dict[str, Any] | None, scorecard: dict[str, Any] | None,
                      index: dict[str, str], reasons: set[str]) -> tuple[dict[str, Any] | None, str]:
    run_sha = (run or {}).get("intended_matrix_sha256")
    score_sha = (scorecard or {}).get("intended_matrix_sha256")
    run_path = (run or {}).get("intended_matrix_path")
    score_path = (scorecard or {}).get("intended_matrix_path")
    if not isinstance(run_sha, str) or not isinstance(score_sha, str) or not run_sha or not score_sha:
        reasons.add("legacy_intent_unverified")
        return None, ""
    if not isinstance(run_path, str) or not isinstance(score_path, str) or not run_path or not score_path:
        reasons.add("legacy_intent_unverified")
        return None, run_sha
    if run_sha != score_sha:
        reasons.add("intended_matrix_hash_mismatch")
    if run_path != score_path:
        reasons.add("intended_matrix_path_mismatch")
    path, error = safe_existing_path(root, run_path, kind="file")
    if error:
        reasons.add("intended_matrix_missing" if error == "path_missing" else error)
        return None, run_sha
    actual = sha_file(path)
    if actual != run_sha or index.get(relative(root, path)) != actual:
        reasons.add("intended_matrix_hash_mismatch")
    data, read_error = read_json_file(path)
    if read_error or data is None or data.get("schema") != INTENT_SCHEMA:
        reasons.add("intended_matrix_malformed")
        return None, run_sha
    return data, run_sha


def cell_key(cell: dict[str, Any], reasons: set[str], code: str) -> tuple[str, str, int, str] | None:
    task_set = cell.get("task_set_id")
    task_id = cell.get("task_id")
    role = cell.get("provider_role")
    rep = cell.get("repetition")
    if (not isinstance(task_set, str) or not task_set or not isinstance(task_id, str) or not task_id
            or not isinstance(role, str) or not role or not isinstance(rep, int) or isinstance(rep, bool) or rep < 1):
        reasons.add(code)
        return None
    return task_set, task_id, rep, role


def _string_list(value: Any, code: str, reasons: set[str]) -> list[str]:
    if not isinstance(value, list) or not value or any(not isinstance(v, str) or not v for v in value):
        reasons.add(code)
        return []
    if len(value) != len(set(value)):
        reasons.add(code)
    return list(value)


def _repetition_list(value: Any, reasons: set[str]) -> list[int]:
    if (not isinstance(value, list) or not value or
            any(not isinstance(v, int) or isinstance(v, bool) or v < 1 for v in value)):
        reasons.add("intended_repetition_malformed")
        return []
    if len(value) != len(set(value)):
        reasons.add("intended_repetition_malformed")
    return list(value)


def declared_intent(intent: dict[str, Any], reasons: set[str]) -> tuple[set[tuple[str, str, int, str]], list[tuple[tuple[str, str, int, str], dict[str, Any]]], int | None]:
    if intent.get("row_schema") != SCORECARD_SCHEMA:
        reasons.add("intended_row_schema_mismatch")
    task_set = intent.get("task_set_id")
    if not isinstance(task_set, str) or not task_set:
        reasons.add("intended_task_set_malformed")
        task_set = ""
    task_ids = _string_list(intent.get("task_ids"), "intended_task_ids_mismatch", reasons)
    roles = _string_list(intent.get("roles"), "intended_role_set_mismatch", reasons)
    repetitions = _repetition_list(intent.get("repetitions"), reasons)
    if task_ids != [TASK_ID]:
        reasons.add("intended_task_ids_mismatch")
    if set(roles) != set(ORIGINAL_ROLES) or len(roles) != len(ORIGINAL_ROLES):
        reasons.add("intended_role_set_mismatch")
    if any(role not in ORIGINAL_IDENTITIES for role in roles):
        reasons.add("intended_unknown_role")
    denominator_known = bool(task_set and task_ids == [TASK_ID] and set(roles) == set(ORIGINAL_ROLES)
                             and len(roles) == len(ORIGINAL_ROLES) and repetitions)
    declared_count = len(task_ids) * len(roles) * len(repetitions) if denominator_known else None
    if declared_count is None:
        reasons.add("intended_denominator_unknown")
    cells = intent.get("cells")
    if not isinstance(cells, list):
        reasons.add("intended_matrix_malformed")
        return set(), [], declared_count
    seen: set[tuple[str, str, int, str]] = set()
    intended: list[tuple[tuple[str, str, int, str], dict[str, Any]]] = []
    for cell in cells:
        if not isinstance(cell, dict):
            reasons.add("intended_cell_malformed")
            continue
        key = cell_key(cell, reasons, "intended_cell_malformed")
        if key is None:
            continue
        if key in seen:
            reasons.add("duplicate_intended_cell")
        seen.add(key)
        intended.append((key, cell))
        expected = ORIGINAL_IDENTITIES.get(key[3])
        if key[1] == TASK_ID and expected:
            for field, value in expected.items():
                if cell.get(field) != value:
                    reasons.add("intended_identity_mismatch")
        elif key[3] not in ORIGINAL_IDENTITIES:
            reasons.add("intended_unknown_role")
    expected = {(task_set, task_id, rep, role) for task_id in task_ids for rep in repetitions for role in roles}
    if seen != expected:
        reasons.add("intended_product_mismatch")
    for task_id in task_ids:
        for rep in repetitions:
            if {role for ts, tid, r, role in seen if ts == task_set and tid == task_id and r == rep} != set(roles):
                reasons.add("intended_repetition_pair_incomplete")
                break
    return seen, intended, declared_count


def state(row: dict[str, Any], reasons: set[str]) -> tuple[bool, str]:
    try:
        outcome, status = derive_primary_outcome(str(row.get("execution_state", "")), str(row.get("oracle_state", "")), str(row.get("receipt_state", "")))
    except ValueError:
        reasons.add("state_matrix_violation")
        return False, "state_matrix_violation"
    if row.get("primary_outcome") != outcome or row.get("status") != status:
        reasons.add("state_matrix_violation")
        return False, "state_matrix_violation"
    if row.get("execution_state") == "returned" and row.get("receipt_state") == "verified" and row.get("oracle_state") in {"pass", "fail"}:
        return True, "eligible_scored_row"
    if row.get("oracle_state") == "unverifiable": reasons.add("unverifiable_row")
    elif row.get("receipt_state") == "drift": reasons.add("receipt_drift")
    elif row.get("execution_state") == "unavailable": reasons.add("blocked_or_unavailable")
    elif row.get("execution_state") in {"timeout", "malformed", "internal_error"}: reasons.add(str(row.get("execution_state")))
    else: reasons.add("not_scored")
    return False, "gap_row"


def artifact_content_checks(root: Path, row: dict[str, Any], index: dict[str, str], reasons: set[str]) -> None:
    attempt_dir, code = safe_existing_path(root, str(row.get("attempt_dir", "")), kind="dir")
    if code:
        reasons.add("attempt_dir_missing" if code == "path_missing" else code)
        return
    files: dict[str, Path] = {}
    for field in ("raw_prompt_path", "raw_output_path", "tool_trace_path", "receipt_path"):
        value = row.get(field)
        if not value:
            continue
        path, path_code = safe_existing_path(root, str(value), kind="file")
        if path_code: reasons.add(path_code)
        else: indexed(root, path, index, reasons)
    for name in ("oracle.json", "metrics.json", "resource.json", "enforcement.json", "limitations.md", "receipt.json"):
        path, path_code = safe_existing_path(root, str(attempt_dir / name), kind="file")
        if path_code: reasons.add(path_code)
        else:
            files[name] = path
            indexed(root, path, index, reasons)
    for name, expected, mismatch in (("oracle.json", row.get("oracle_evidence"), "oracle_artifact_row_mismatch"),
                                     ("metrics.json", row.get("metrics"), "metrics_artifact_row_mismatch"),
                                     ("resource.json", row.get("metrics"), "metrics_artifact_row_mismatch"),
                                     ("enforcement.json", row.get("enforcement_description"), "enforcement_artifact_row_mismatch")):
        data, error = read_json_file(files.get(name, Path("__missing__")))
        if error or data != expected:
            reasons.add(mismatch)
    if row.get("enforcement_sha256") and row.get("enforcement_description") is not None:
        if sha(row["enforcement_description"]) != row.get("enforcement_sha256"):
            reasons.add("enforcement_hash_mismatch")
    receipt_path, code = safe_existing_path(root, str(row.get("receipt_path", "")), kind="file")
    if code:
        reasons.add("receipt_missing" if code == "path_missing" else code)
        return
    if recheck_attempt_receipt(receipt_path, row) != "verified":
        reasons.add("receipt_unverified")
    if row.get("receipt_sha256") and row.get("receipt_sha256") != sha_file(receipt_path):
        reasons.add("receipt_hash_mismatch")
    receipt, error = read_json_file(receipt_path)
    if error:
        reasons.add("receipt_malformed")
        return
    if row.get("receipt_subject_sha256") and row.get("receipt_subject_sha256") != receipt.get("receipt_subject_sha256"):
        reasons.add("receipt_subject_hash_mismatch")
    for item in ((receipt.get("receipt_subject") or {}).get("artifacts") or []):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            reasons.add("receipt_artifact_malformed")
            continue
        path, item_code = safe_existing_path(receipt_path.parent, item["path"], kind="file")
        if item_code: reasons.add(item_code)
        else: indexed(root, path, index, reasons)
