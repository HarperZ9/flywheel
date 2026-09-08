"""Source-only KV diagnostic oracle.

This checker is packet-specific. It derives expected answers from
`flywheel.kv-source-only-fixture/v1` or
`flywheel.kv-source-only-fixture/v2-token-admitted` source records for the first
KV-cache source-only diagnostic task set. It does not load private oracle
fixtures, wrong-answer controls, or runtime profiles.
"""
from __future__ import annotations

from typing import Any, Callable

from harness.cross_harness_oracle_support import _Malformed, _digest
from harness.cross_harness_kv_source_abstention import DERIVERS as _ABSTENTION_DERIVERS
from harness.cross_harness_kv_source_authority import DERIVERS as _AUTHORITY_DERIVERS
from harness.cross_harness_kv_source_common import (
    CHECKER_ID,
    _field,
    _records,
    _relative_path,
    _source_ids,
    _validate_derived_result,
    _validate_fixture_schema,
)
from harness.cross_harness_kv_source_scoring import _score_result
from harness.cross_harness_kv_source_state import DERIVERS as _STATE_DERIVERS
from harness.cross_harness_kv_source_structured import DERIVERS as _STRUCTURED_DERIVERS


DERIVERS: dict[str, Callable[[str, list[dict[str, Any]]], dict[str, Any]]] = {
    **_STATE_DERIVERS,
    **_AUTHORITY_DERIVERS,
    **_STRUCTURED_DERIVERS,
    **_ABSTENTION_DERIVERS,
}


def derive_kv_source_result(task_id: str, fixture: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str], int]:
    _validate_fixture_schema(fixture)
    if fixture.get("task_id") != task_id:
        return None, ["fixture_task_id_mismatch"], 0

    _relative_path(_field(fixture, "source_input_ref"), "fixture_source_input_ref_invalid")
    _digest(_field(fixture, "source_input_sha256"), "fixture_source_input_sha256")

    records = _records(fixture.get("source_records"))
    deriver = DERIVERS.get(task_id)
    if deriver is None:
        return None, ["unknown_kv_task"], len(records)
    expected = deriver(task_id, records)
    _validate_derived_result(task_id, records, expected)
    return expected, [], len(records)


def kv_source_derived_strict_json(context, report, texts, fixture, checked):
    del texts, checked
    result = report.get("result")
    if not isinstance(result, dict):
        raise _Malformed("result_type_invalid")

    expected, fixture_codes, source_record_count = derive_kv_source_result(context.task_id, fixture)
    if fixture_codes:
        return fixture_codes, {
            "source_record_count": source_record_count,
            "citation_count": 0,
            "kv_source_derivation": "unavailable",
        }
    assert expected is not None
    records = _records(fixture.get("source_records"))
    citation_order = context.oracle_spec.get("citation_order") or fixture.get("citation_order") or "unordered_set"
    if not isinstance(citation_order, str):
        raise _Malformed("citation_order_invalid")
    codes = _score_result(result, expected, _source_ids(records), citation_order)
    metrics = {
        "source_record_count": source_record_count,
        "citation_count": len(expected["citations"]),
        "kv_source_derivation": "source_records",
    }
    return codes, metrics


CHECKERS = {CHECKER_ID: kv_source_derived_strict_json}
