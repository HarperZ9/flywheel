"""Shared helpers for the source-only KV oracle checker."""
from __future__ import annotations

import json
from pathlib import Path, PureWindowsPath
from typing import Any

from harness.cross_harness_oracle_support import _Malformed, _rows, _strings


CHECKER_ID = "kv_source_derived_strict_json/v1"
FIXTURE_SCHEMA = "flywheel.kv-source-only-fixture/v1"
TOKEN_ADMITTED_FIXTURE_SCHEMA = "flywheel.kv-source-only-fixture/v2-token-admitted"
SUPPORTED_FIXTURE_SCHEMAS = {FIXTURE_SCHEMA, TOKEN_ADMITTED_FIXTURE_SCHEMA}
TOKEN_ADMITTED_FIXTURE_KEYS = {
    "schema",
    "task_id",
    "family",
    "question",
    "citation_order",
    "source_input_ref",
    "source_input_sha256",
    "source_records",
}


def _answered(task_id: str, answer: dict[str, Any], citations: list[str]) -> dict[str, Any]:
    return {"task_id": task_id, "verdict": "ANSWERED", "answer": answer, "citations": citations}


def _unverifiable(
    task_id: str,
    missing: list[str],
    blocked_claims: list[str],
    citations: list[str],
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "verdict": "UNVERIFIABLE",
        "answer": None,
        "missing_evidence": missing,
        "claims_not_made": blocked_claims,
        "citations": citations,
    }


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _validate_fixture_schema(fixture: dict[str, Any]) -> str:
    schema = fixture.get("schema")
    if schema not in SUPPORTED_FIXTURE_SCHEMAS:
        raise _Malformed("fixture_schema_invalid")
    if schema == TOKEN_ADMITTED_FIXTURE_SCHEMA:
        if set(fixture) != TOKEN_ADMITTED_FIXTURE_KEYS:
            raise _Malformed("fixture_token_admitted_shape_invalid")
        for key in ("family", "question", "citation_order"):
            value = fixture.get(key)
            if not isinstance(value, str) or not value:
                raise _Malformed("fixture_token_admitted_shape_invalid")
    return schema


def _records(value: Any) -> list[dict[str, Any]]:
    records = _rows(value, "fixture_source_records")
    seen: set[str] = set()
    for row in records:
        record_id = row.get("record_id")
        if not isinstance(record_id, str) or not record_id:
            raise _Malformed("fixture_record_id_type_invalid")
        if record_id in seen:
            raise _Malformed("fixture_record_id_duplicate")
        seen.add(record_id)
        if not isinstance(row.get("fields"), dict):
            raise _Malformed("fixture_record_fields_invalid")
    return records


def _row_by_id(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row["record_id"]): row for row in records}


def _fields(rows: dict[str, dict[str, Any]], record_id: str) -> dict[str, Any]:
    row = rows.get(record_id)
    if row is None:
        raise _Malformed("fixture_required_record_missing")
    fields = row.get("fields")
    if not isinstance(fields, dict):
        raise _Malformed("fixture_record_fields_invalid")
    return fields


def _field(fields: dict[str, Any], key: str) -> Any:
    if key not in fields:
        raise _Malformed("fixture_required_field_missing")
    return fields[key]


def _str_field(fields: dict[str, Any], key: str) -> str:
    value = _field(fields, key)
    if not isinstance(value, str) or not value:
        raise _Malformed("fixture_string_field_invalid")
    return value


def _records_with_type(records: list[dict[str, Any]], record_type: str) -> list[dict[str, Any]]:
    return [row for row in records if row.get("record_type") == record_type]


def _source_ids(records: list[dict[str, Any]]) -> set[str]:
    return {str(row["record_id"]) for row in records}


def _relative_path(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value:
        raise _Malformed(code)
    native = Path(value)
    windows = PureWindowsPath(value)
    if native.is_absolute() or windows.is_absolute() or ".." in native.parts or ".." in windows.parts:
        raise _Malformed(code)
    return value


def _join(root: Any, relative: Any) -> str:
    if not isinstance(root, str) or not root:
        raise _Malformed("fixture_path_root_invalid")
    part = _relative_path(relative, "fixture_path_part_invalid")
    if not part:
        raise _Malformed("fixture_path_part_invalid")
    return f"{root.rstrip('/')}/{part.lstrip('/')}"


def _cwd(paths: dict[str, Any]) -> str:
    value = paths.get("cwd")
    if not isinstance(value, str) or not value:
        raise _Malformed("fixture_cwd_missing")
    return value


def _ensure_flags(allowed: Any, required: list[str], code: str) -> None:
    allowed_args = set(_strings(allowed, "fixture_allowed_args"))
    if not set(required) <= allowed_args:
        raise _Malformed(code)


def _latest(items: list[dict[str, Any]], field: str) -> dict[str, Any]:
    if not items:
        raise _Malformed("fixture_required_record_missing")
    try:
        return max(items, key=lambda row: row["fields"][field])
    except (KeyError, TypeError) as exc:
        raise _Malformed("fixture_required_field_missing") from exc


def _lowest(items: list[dict[str, Any]], field: str) -> dict[str, Any]:
    if not items:
        raise _Malformed("fixture_required_record_missing")
    try:
        return min(items, key=lambda row: row["fields"][field])
    except (KeyError, TypeError) as exc:
        raise _Malformed("fixture_required_field_missing") from exc


def _sorted_by(items: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    if not items:
        raise _Malformed("fixture_required_record_missing")
    try:
        return sorted(items, key=lambda row: row["fields"][field])
    except (KeyError, TypeError) as exc:
        raise _Malformed("fixture_required_field_missing") from exc


def _validate_derived_result(task_id: str, records: list[dict[str, Any]], expected: dict[str, Any]) -> None:
    source_ids = _source_ids(records)
    citations = _strings(expected.get("citations"), "expected_citations")
    if len(set(citations)) != len(citations) or any(citation not in source_ids for citation in citations):
        raise _Malformed("derived_citation_invalid")
    if expected.get("task_id") != task_id:
        raise _Malformed("derived_task_id_invalid")

    full_reference = _canonical(expected)
    answer = expected.get("answer")
    full_answer = _canonical(answer) if answer is not None else ""
    forbidden_field_keys = {"reference_output", "reference", "answer", "citations"}
    for row in records:
        fields = row.get("fields") or {}
        if forbidden_field_keys & set(fields):
            raise _Malformed("fixture_reference_like_field")
        text = _canonical(row)
        if full_reference in text or (full_answer and full_answer in text):
            raise _Malformed("fixture_embedded_reference_output")
