# SPDX-License-Identifier: MIT
"""Fail-closed Flywheel oracle for the 76-row Competitive Surpass Matrix.

Verifies exact 1-to-1 partition between COMMONS_COMPETITIVE_SIGNALS.tsv and
the surpass matrix JSON, CS-001..CS-076 completeness, raw TSV SHA-256 match,
live catalogue provenance, and deterministic surpass_attestation_sha256.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .matrix_parser import (
    MatrixSignalRecord,
    SignalTsvRecord,
    parse_matrix_signals,
    parse_signals_tsv,
    validate_summary_block,
)
from .numeric_guards import (
    canonical_sha256_hex,
    is_strict_int,
    sha256_bytes_hex,
)

HONEST_SCOPE_LIMIT = (
    "Verifies 1-to-1 TSV-to-JSON signal partition, CS-001..CS-076 ID "
    "completeness, TSV byte digest, summary arithmetic, and caller-supplied "
    "catalogue provenance. Does not independently re-execute third-party "
    "competitor benchmarks."
)


@dataclass(frozen=True)
class SurpassGateReport:
    """Fail-closed attestation verdict for the Competitive Surpass Matrix."""

    passed: bool
    total_signals: int
    surpassed_count: int
    parity_count: int
    open_count: int
    unique_catalogue_ids: int
    tsv_sha256: str
    surpass_attestation_sha256: str
    violations: tuple[str, ...]
    honest_scope_limit: str = HONEST_SCOPE_LIMIT


def _expected_signal_ids(expected_count: int, prefix: str) -> list[str]:
    width = max(3, len(str(expected_count)))
    return [f"{prefix}{idx:0{width}d}" for idx in range(1, expected_count + 1)]


def _check_partition_and_completeness(
    tsv_rows: list[SignalTsvRecord],
    json_rows: list[MatrixSignalRecord],
    expected_count: int,
    id_prefix: str,
) -> list[str]:
    errors: list[str] = []
    tsv_map = {r.signal_id: r for r in tsv_rows}
    json_map = {r.signal_id: r for r in json_rows}
    missing_in_json = sorted(set(tsv_map) - set(json_map))
    extra_in_json = sorted(set(json_map) - set(tsv_map))
    if missing_in_json:
        errors.append(f"partition: missing in JSON {missing_in_json[:5]}")
    if extra_in_json:
        errors.append(f"partition: extra in JSON {extra_in_json[:5]}")
    expected = set(_expected_signal_ids(expected_count, id_prefix))
    missing_exp = sorted(expected - set(tsv_map))
    extra_exp = sorted(set(tsv_map) - expected)
    if missing_exp:
        errors.append(f"completeness: missing expected IDs {missing_exp[:5]}")
    if extra_exp:
        errors.append(f"completeness: unexpected IDs {extra_exp[:5]}")
    for sid, t_rec in tsv_map.items():
        j_rec = json_map.get(sid)
        if j_rec is not None and j_rec.lane != t_rec.lane:
            errors.append(
                f"partition({sid}): lane mismatch {j_rec.lane!r} != {t_rec.lane!r}"
            )
    return errors


def _check_provenance(
    records: list[MatrixSignalRecord],
    known_catalogue_ids: set[int] | None,
) -> tuple[list[int], list[str]]:
    errors: list[str] = []
    all_cids: set[int] = set()
    for rec in records:
        if rec.tier == "surpassed_with_receipt" and not rec.evidence_catalogue_ids:
            errors.append(
                f"provenance({rec.signal_id}): surpassed_with_receipt lacks catalogue ID"
            )
        for cid in rec.evidence_catalogue_ids:
            all_cids.add(cid)
            if known_catalogue_ids is not None and cid not in known_catalogue_ids:
                errors.append(
                    f"provenance({rec.signal_id}): forged or absent catalogue_id {cid}"
                )
    return sorted(all_cids), errors


def _check_source_registry_digest(
    matrix_obj: dict[str, Any],
    tsv_sha256: str,
    tsv_row_count: int,
) -> list[str]:
    src = matrix_obj.get("source_registry")
    if not isinstance(src, dict):
        return ["source_registry: missing object in matrix JSON"]
    errors: list[str] = []
    claimed_sha = src.get("sha256")
    if isinstance(claimed_sha, str) and claimed_sha.strip():
        if claimed_sha.strip().lower() != tsv_sha256.lower():
            errors.append(
                f"source_registry.sha256 mismatch: {claimed_sha} != {tsv_sha256}"
            )
    else:
        errors.append("source_registry.sha256: missing or invalid string")
    claimed_rows = src.get("row_count")
    if not is_strict_int(claimed_rows) or claimed_rows != tsv_row_count:
        errors.append(
            f"source_registry.row_count: {claimed_rows!r} != {tsv_row_count}"
        )
    return errors


def verify_surpass_matrix(
    tsv_bytes: bytes,
    matrix_obj: Any,
    *,
    known_catalogue_ids: set[int] | None = None,
    expected_count: int = 76,
    id_prefix: str = "CS-",
) -> SurpassGateReport:
    """Run fail-closed verification on raw TSV bytes and parsed matrix JSON."""
    if not isinstance(tsv_bytes, (bytes, bytearray)):
        return _fail_report("tsv_bytes: expected bytes", "")
    if not is_strict_int(expected_count) or expected_count <= 0:
        return _fail_report(f"expected_count: invalid {expected_count!r}", "")
    raw_bytes = bytes(tsv_bytes)
    tsv_sha = sha256_bytes_hex(raw_bytes)
    try:
        tsv_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return _fail_report("tsv_bytes: invalid UTF-8 encoding", tsv_sha)
    tsv_rows, tsv_errs = parse_signals_tsv(tsv_text)
    json_rows, json_errs = parse_matrix_signals(matrix_obj)
    violations = list(tsv_errs) + list(json_errs)
    if isinstance(matrix_obj, dict) and not json_errs:
        violations.extend(validate_summary_block(matrix_obj, json_rows))
        violations.extend(
            _check_source_registry_digest(matrix_obj, tsv_sha, len(tsv_rows))
        )
    if not tsv_errs and not json_errs:
        violations.extend(
            _check_partition_and_completeness(
                tsv_rows, json_rows, expected_count, id_prefix
            )
        )
    unique_cids, prov_errs = _check_provenance(json_rows, known_catalogue_ids)
    violations.extend(prov_errs)
    return _build_report(json_rows, unique_cids, tsv_sha, violations)


def _build_report(
    json_rows: list[MatrixSignalRecord],
    unique_cids: list[int],
    tsv_sha: str,
    violations: list[str],
) -> SurpassGateReport:
    surpassed = sum(1 for r in json_rows if r.tier == "surpassed_with_receipt")
    parity = sum(1 for r in json_rows if r.tier == "parity_verified")
    open_cnt = sum(1 for r in json_rows if r.tier == "open_next_wave_opportunity")
    attest_payload = {
        "tsv_sha256": tsv_sha,
        "total_signals": len(json_rows),
        "surpassed_count": surpassed,
        "parity_count": parity,
        "open_count": open_cnt,
        "signals": [
            {
                "signal_id": r.signal_id,
                "lane": r.lane,
                "tier": r.tier,
                "evidence_catalogue_ids": list(r.evidence_catalogue_ids),
            }
            for r in sorted(json_rows, key=lambda x: x.signal_id)
        ],
    }
    return SurpassGateReport(
        passed=len(violations) == 0,
        total_signals=len(json_rows),
        surpassed_count=surpassed,
        parity_count=parity,
        open_count=open_cnt,
        unique_catalogue_ids=len(unique_cids),
        tsv_sha256=tsv_sha,
        surpass_attestation_sha256=canonical_sha256_hex(attest_payload),
        violations=tuple(violations),
    )


def _fail_report(message: str, tsv_sha: str) -> SurpassGateReport:
    return SurpassGateReport(
        passed=False,
        total_signals=0,
        surpassed_count=0,
        parity_count=0,
        open_count=0,
        unique_catalogue_ids=0,
        tsv_sha256=tsv_sha,
        surpass_attestation_sha256="",
        violations=(message,),
    )


def verify_surpass_matrix_files(
    tsv_path: Path | str,
    matrix_path: Path | str,
    *,
    known_catalogue_ids: set[int] | None = None,
    expected_count: int = 76,
    id_prefix: str = "CS-",
) -> SurpassGateReport:
    """Load TSV and JSON files from disk and verify fail-closed."""
    try:
        tsv_bytes = Path(tsv_path).read_bytes()
        matrix_obj = json.loads(Path(matrix_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return _fail_report(f"io_error: {exc}", "")
    return verify_surpass_matrix(
        tsv_bytes,
        matrix_obj,
        known_catalogue_ids=known_catalogue_ids,
        expected_count=expected_count,
        id_prefix=id_prefix,
    )
