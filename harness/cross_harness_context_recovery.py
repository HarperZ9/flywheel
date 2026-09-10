"""Context-recovery semantic checker for cross-harness agent tasks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harness.cross_harness_context_contract import (
    report_contract_codes,
    validate_fixture_schema,
    workspace_inventory_codes,
)
from harness.cross_harness_oracle_support import _Malformed, _digest, _inside, _pairs, _read, _root, _rows, _sha, _strings

CHECKER_ID = "context_recovery_state/v1"

_DIGEST_FIELDS = ("preview_sha256", "source_state_sha256", "event_head_sha256")
_CONTEXT_FIELDS = ("preview_ref", "preview_sha256", "source_state_sha256", "event_head_sha256")


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _Malformed(f"{field}_type_invalid")
    return value


def _clean_strings(value: Any, field: str) -> list[str]:
    items = _strings(value, field)
    if any(not item.strip() for item in items):
        raise _Malformed(f"{field}_type_invalid")
    return items


def _optional_strings(value: Any, field: str) -> list[str]:
    return [] if value is None else _clean_strings(value, field)


def _zero(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == 0


def _exact_int(value: Any, expected: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == expected


def _fixture_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise _Malformed(f"{field}_type_invalid")
    return value


def _workspace_file_rows(fixture: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = _rows(fixture.get("workspace_files"), "fixture_workspace_files")
    files: dict[str, dict[str, Any]] = {}
    for row in rows:
        path = row.get("path")
        role = row.get("role")
        must_preserve = row.get("must_preserve")
        expected_sha256 = row.get("expected_sha256")
        if not isinstance(path, str) or not path or path in files:
            raise _Malformed("fixture_workspace_file_path_invalid")
        if not isinstance(role, str) or not role:
            raise _Malformed("fixture_workspace_file_role_invalid")
        if not isinstance(must_preserve, bool):
            raise _Malformed("fixture_workspace_file_preserve_invalid")
        _digest(expected_sha256, f"fixture_workspace_file_sha256:{path}")
        files[path] = row
    if not files:
        raise _Malformed("fixture_workspace_files_empty")
    return files


def _reported_workspace(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = _rows(report.get("workspace_state"), "workspace_state")
    files: dict[str, dict[str, Any]] = {}
    for row in rows:
        path = row.get("path")
        sha256 = row.get("sha256")
        role = row.get("role")
        if not isinstance(path, str) or not path or path in files:
            raise _Malformed("workspace_state_path_invalid")
        if not isinstance(role, str) or not role:
            raise _Malformed("workspace_state_role_invalid")
        _digest(sha256, f"workspace_state_sha256:{path}")
        files[path] = row
    return files


def _rows_by_id(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    keyed: dict[str, dict[str, Any]] = {}
    for row in rows:
        case_id = row.get("case_id")
        if not isinstance(case_id, str) or not case_id or case_id in keyed:
            raise _Malformed(f"{field}_case_id_invalid")
        keyed[case_id] = row
    return keyed


def _context_codes(report: dict[str, Any], fixture: dict[str, Any]) -> list[str]:
    expected = _object(fixture.get("continuation_package"), "fixture_continuation_package")
    observed = _object(report.get("recovered_context"), "recovered_context")
    for field in _DIGEST_FIELDS:
        _digest(expected.get(field), f"fixture_continuation_{field}")
    _clean_strings(expected.get("selected_files"), "fixture_continuation_selected_files")

    codes: list[str] = []
    for field in _CONTEXT_FIELDS:
        if observed.get(field) != expected.get(field):
            codes.append("recovery_source_state_mismatch")
    if observed.get("selected_files") != expected.get("selected_files"):
        codes.append("recovery_source_state_mismatch")
    return codes


def _workspace_codes(root: Any, report: dict[str, Any], fixture: dict[str, Any], checked: dict[str, str]) -> list[str]:
    expected_files = _workspace_file_rows(fixture)
    reported_files = _reported_workspace(report)
    codes: list[str] = []
    if set(reported_files) != set(expected_files):
        codes.append("workspace_state_mismatch")

    for path, expected in expected_files.items():
        actual_path = _inside(root, path)
        if actual_path is None:
            codes.append("workspace_state_mismatch")
            continue
        actual_sha256 = _sha(_read(checked, f"workspace:{expected.get('role')}:{path}", actual_path))
        reported = reported_files.get(path)
        if not reported or reported.get("role") != expected.get("role") or reported.get("sha256") != actual_sha256:
            codes.append("workspace_state_mismatch")
        if expected.get("must_preserve") and actual_sha256 != expected.get("expected_sha256"):
            codes.append("preserved_file_modified")

    preserved = sorted(_strings(report.get("preserved_files"), "preserved_files"))
    expected_preserved = sorted(path for path, row in expected_files.items() if row.get("must_preserve"))
    if preserved != expected_preserved:
        codes.append("preserved_file_modified")
    return codes


def _journey_state_codes(root: Path, report: dict[str, Any], fixture: dict[str, Any], checked: dict[str, str]) -> tuple[list[str], int | None]:
    config = fixture.get("journey_state")
    if config is None:
        return [], None
    config = _object(config, "fixture_journey_state")
    path_ref = config.get("path")
    state_path = _inside(root, path_ref)
    if state_path is None:
        return ["journey_state_mismatch"], None
    try:
        data = _read(checked, f"workspace:journey_state:{path_ref}", state_path)
        state = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return ["journey_state_mismatch"], None
    rows = state.get("journeys") if isinstance(state, dict) else None
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        return ["journey_state_mismatch"], None
    expected_ref = config.get("expected_preview_ref")
    if not isinstance(expected_ref, str):
        raise _Malformed("fixture_journey_state_invalid")
    expected_count = _fixture_int(config.get("expected_count"), "fixture_journey_state_expected_count")
    actual_count = sum(1 for row in rows if row.get("continuation") == expected_ref)
    codes: list[str] = []
    if actual_count != expected_count:
        codes.append("journey_state_mismatch")
    if actual_count > expected_count:
        codes.append("duplicate_effect_not_idempotent")
    return codes, actual_count


def _drift_codes(report: dict[str, Any], fixture: dict[str, Any]) -> list[str]:
    expected = _rows_by_id(_rows(fixture.get("drift_cases"), "fixture_drift_cases"), "fixture_drift_cases")
    observed = _rows_by_id(_rows(report.get("source_drift_decisions"), "source_drift_decisions"), "source_drift_decisions")
    codes: list[str] = []
    if set(observed) != set(expected):
        codes.append("source_drift_not_refused")
    for case_id, row in expected.items():
        seen = observed.get(case_id, {})
        if seen.get("decision") != "refuse" or seen.get("error_code") != row.get("error_code"):
            codes.append("source_drift_not_refused")
        if not _zero(seen.get("effect_count")):
            codes.append("source_drift_not_refused")
    return codes


def _duplicate_codes(report: dict[str, Any], fixture: dict[str, Any], actual_journey_count: int | None) -> list[str]:
    expected = _rows_by_id(_rows(fixture.get("duplicate_cases"), "fixture_duplicate_cases"), "fixture_duplicate_cases")
    observed = _rows_by_id(_rows(report.get("duplicate_resolutions"), "duplicate_resolutions"), "duplicate_resolutions")
    codes: list[str] = []
    if set(observed) != set(expected):
        codes.append("duplicate_effect_not_idempotent")
    for case_id, row in expected.items():
        seen = observed.get(case_id, {})
        if seen.get("decision") != row.get("expected_decision"):
            codes.append("duplicate_effect_not_idempotent")
        expected_count = 1 if actual_journey_count is None else actual_journey_count
        if not _zero(seen.get("new_effect_count")) or not _exact_int(seen.get("journey_count"), expected_count):
            codes.append("duplicate_effect_not_idempotent")
    return codes


def _next_action_codes(report: dict[str, Any], fixture: dict[str, Any]) -> list[str]:
    expected = _object(fixture.get("rescue_action"), "fixture_rescue_action")
    observed = _object(report.get("next_action"), "next_action")
    codes: list[str] = []
    for field in ("action_id", "kind"):
        if observed.get(field) != expected.get(field):
            codes.append("next_action_mismatch")
    for field in ("selected_files", "basis_refs"):
        if observed.get(field) != expected.get(field):
            codes.append("next_action_mismatch")
    if observed.get("description") != expected.get("description"):
        codes.append("next_action_mismatch")
    return codes


def _forbidden_codes(report: dict[str, Any], fixture: dict[str, Any], texts: dict[str, str]) -> list[str]:
    codes: list[str] = []
    forbidden_effects = _strings(report.get("forbidden_effects"), "forbidden_effects")
    if forbidden_effects:
        codes.append("forbidden_effect_reported")
    blob = json.dumps(report, sort_keys=True).lower() + "\n" + "\n".join(texts.values()).lower()
    for phrase in _clean_strings(fixture.get("forbidden_self_report_phrases"), "fixture_forbidden_self_report_phrases"):
        if phrase.lower() in blob:
            codes.append("self_report_without_artifact_state")
    for phrase in _optional_strings(fixture.get("forbidden_native_resume_phrases"), "fixture_forbidden_native_resume_phrases"):
        if phrase.lower() in blob:
            codes.append("native_full_session_claim")
    return codes


def context_recovery_state(context: Any, report: dict[str, Any], texts: dict[str, str], fixture: dict[str, Any],
                           checked: dict[str, str]) -> tuple[list[str], dict[str, Any]]:
    root = _root(context, "workspace_root")
    validate_fixture_schema(fixture)
    if fixture.get("task_id") != context.task_id:
        raise _Malformed("fixture_task_id_mismatch")

    codes: list[str] = []
    codes.extend(report_contract_codes(report, texts, fixture))
    codes.extend(_context_codes(report, fixture))
    inventory_codes, inventory_safe = workspace_inventory_codes(root, fixture, checked)
    codes.extend(inventory_codes)
    actual_journey_count = None
    if inventory_safe:
        codes.extend(_workspace_codes(root, report, fixture, checked))
        journey_codes, actual_journey_count = _journey_state_codes(root, report, fixture, checked)
        codes.extend(journey_codes)
    codes.extend(_drift_codes(report, fixture))
    codes.extend(_duplicate_codes(report, fixture, actual_journey_count))
    codes.extend(_next_action_codes(report, fixture))
    codes.extend(_forbidden_codes(report, fixture, texts))
    if report.get("native_provenance_state") != "separate_dimension":
        codes.append("recovery_source_state_mismatch")

    preserved_count = sum(1 for row in _workspace_file_rows(fixture).values() if row.get("must_preserve"))
    metrics = {
        "checked_files": len(checked),
        "failure_code_count": len(set(codes)),
        "preserved_files_checked": preserved_count,
        "native_provenance": report.get("native_provenance_state"),
    }
    return sorted(set(codes)), metrics


CHECKERS = {CHECKER_ID: context_recovery_state}
