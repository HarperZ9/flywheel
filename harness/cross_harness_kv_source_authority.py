"""Authority and repository-reference KV source branches."""
from __future__ import annotations

from typing import Any

from harness.cross_harness_oracle_support import _Malformed
from harness.cross_harness_kv_source_common import _answered, _field, _fields, _lowest, _records_with_type, _row_by_id, _sorted_by, _str_field


def _kv_cdr_001(task_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    ranked = _sorted_by(_records_with_type(records, "retention_rule"), "authority_rank")
    winner = ranked[0]
    fields = winner["fields"]
    return _answered(
        task_id,
        {
            "retention_days": _field(fields, "retention_days"),
            "public_copy_allowed": _field(fields, "public_copy_allowed"),
            "promotion_requires": _field(fields, "promotion_requires"),
            "winning_authority": winner["record_id"],
            "losing_conflicts": [row["record_id"] for row in ranked[1:]],
        },
        [
            "operator-handoff:kv-retention",
            "project-agent:temp-retention",
            "roadmap:artifact-retention",
            "stale-transcript:retention",
        ],
    )


def _kv_cdr_002(task_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    winner = _lowest(_records_with_type(records, "endpoint_evidence"), "authority_rank")
    fields = winner["fields"]
    return _answered(
        task_id,
        {
            "endpoint_url": _field(fields, "endpoint_url"),
            "context_tokens": _field(fields, "context_tokens"),
            "cache_type_k": _field(fields, "cache_type_k"),
            "cache_type_v": _field(fields, "cache_type_v"),
            "flash_attention": _field(fields, "flash_attention"),
            "winning_authority": winner["record_id"],
        },
        [
            "live-process:ollama-q8",
            "profile-json:ollama-8192",
            "docs:serving-defaults",
            "memory-note:old-port",
        ],
    )


def _kv_rsm_001(task_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    registry = next(
        (
            row
            for row in _records_with_type(records, "repo_excerpt")
            if row["fields"].get("role") == "authoritative_registry"
        ),
        None,
    )
    if registry is None:
        raise _Malformed("fixture_required_record_missing")
    supporting = [
        row
        for row in _records_with_type(records, "repo_excerpt")
        if row["fields"].get("role") == "supporting_doc"
    ]
    if len(supporting) != 1:
        raise _Malformed("fixture_supporting_doc_record_missing")
    path = _str_field(registry["fields"], "path")
    symbol_rows = {
        row["fields"].get("symbol"): row
        for row in _records_with_type(records, "symbol")
        if row["fields"].get("path") == path
    }
    if {"LANE_REGISTRY", "lane_for_task"} - set(symbol_rows):
        raise _Malformed("lane_symbols_missing")
    supporting_doc = _str_field(supporting[0]["fields"], "path")
    return _answered(
        task_id,
        {
            "registry_file": path,
            "registry_symbol": "LANE_REGISTRY",
            "resolver_symbol": "lane_for_task",
            "supporting_doc": supporting_doc,
        },
        [
            str(registry["record_id"]),
            str(symbol_rows["LANE_REGISTRY"]["record_id"]),
            str(symbol_rows["lane_for_task"]["record_id"]),
            str(supporting[0]["record_id"]),
        ],
    )


def _kv_rsm_002(task_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    rows = _row_by_id(records)
    registry = _fields(rows, "repo-file:harness/cross_harness_oracles.py")
    checker = _fields(rows, "checker:evidence_bound_reporting/v1")
    symbol = _fields(rows, "symbol:_CHECKERS")
    if _field(symbol, "path") != _field(registry, "path"):
        raise _Malformed("checker_registry_symbol_path_mismatch")
    return _answered(
        task_id,
        {
            "registration_file": _field(registry, "path"),
            "graded_checker_file": _field(checker, "file"),
            "registry_symbol": _field(symbol, "symbol"),
            "checker_id": _field(checker, "checker_id"),
        },
        [
            "repo-file:harness/cross_harness_oracles.py",
            "repo-file:harness/cross_harness_checkers.py",
            "symbol:_CHECKERS",
            "checker:evidence_bound_reporting/v1",
        ],
    )


DERIVERS = {
    "kv-cdr-001-retention-authority": _kv_cdr_001,
    "kv-cdr-002-endpoint-authority": _kv_cdr_002,
    "kv-rsm-001-lane-symbol-match": _kv_rsm_001,
    "kv-rsm-002-checker-reference-match": _kv_rsm_002,
}
