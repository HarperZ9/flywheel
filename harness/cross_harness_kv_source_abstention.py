"""Abstention KV source branches."""
from __future__ import annotations

from typing import Any

from harness.cross_harness_oracle_support import _Malformed, _strings
from harness.cross_harness_kv_source_common import _field, _fields, _records_with_type, _row_by_id, _unverifiable


def _kv_abst_001(task_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    rows = _row_by_id(records)
    required = _field(_fields(rows, "rule:treatment-compliance"), "required_evidence")
    captured = _field(_fields(rows, "pilot:comparison"), "f16_runner_arguments_captured")
    if captured is True:
        raise _Malformed("f16_missing_fixture_has_required_evidence")
    return _unverifiable(
        task_id,
        [required],
        ["treatment_compliance_proven", "latency_superiority", "quality_noninferiority"],
        [
            "pilot:comparison",
            "pilot:q8-runtime-settings",
            "pilot:f16-empty-logs",
            "rule:treatment-compliance",
        ],
    )


def _kv_abst_002(task_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    rows = _row_by_id(records)
    required = _field(_fields(rows, "spec:frontier-comparison"), "required")
    required_strings = _strings(required, "fixture_required_evidence")
    missing = [
        row["fields"].get("item")
        for row in _records_with_type(records, "missing_evidence")
        if row["fields"].get("present") is False
    ]
    if not set(missing) <= set(required_strings):
        raise _Malformed("frontier_missing_evidence_not_in_requirement")
    blocked = _strings(
        _field(_fields(rows, "rule:no-equivalence-from-diagnostic"), "forbidden_claims"),
        "fixture_forbidden_claims",
    )
    return _unverifiable(
        task_id,
        required_strings,
        blocked,
        [
            "spec:frontier-comparison",
            "evidence:named-endpoints-absent",
            "evidence:permissions-absent",
            "rule:no-equivalence-from-diagnostic",
        ],
    )


DERIVERS = {
    "kv-abst-001-f16-settings-missing": _kv_abst_001,
    "kv-abst-002-frontier-comparison-missing": _kv_abst_002,
}
