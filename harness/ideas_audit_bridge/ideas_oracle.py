# SPDX-License-Identifier: MIT
"""Fail-closed Flywheel oracle for AUTHOR_IDEAS_REGISTER claim-to-receipt audit.

Verifies the 18-column AUTHOR_IDEAS_REGISTER.tsv schema, strict integer score
bounds, zero FLAG cells, zero forged catalogue IDs, strict VERIFIED_MATCH vs
UNVERIFIED partition, and deterministic ideas_attestation_sha256 sealing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .receipt_parity import (
    ParityPartition,
    classify_built_parity,
    compute_match_ratio,
    parse_receipt_index,
    validate_known_catalogue_ids,
    validate_ratio_threshold,
)
from .register_parser import IdeaRow, parse_ideas_register

HONEST_SCOPE_LIMIT = (
    "Verifies 18-column ideas register schema, score bounds, forged catalogue "
    "ID rejection, and strict VERIFIED_MATCH vs UNVERIFIED parity from "
    "caller-provided receipt index and verification outcomes. Does not invoke "
    "external binaries or modify registers."
)


@dataclass(frozen=True)
class IdeasAuditReport:
    """Fail-closed attestation verdict for AUTHOR_IDEAS_REGISTER parity."""

    passed: bool
    total_rows: int
    built_count: int
    partial_count: int
    unbuilt_count: int
    verified_match_count: int
    unverified_count: int
    verified_match_ratio: float
    forged_catalogue_ids: tuple[int, ...]
    unverified_no_receipt_ids: tuple[str, ...]
    unverified_drift_ids: tuple[str, ...]
    register_sha256: str
    ideas_attestation_sha256: str
    violations: tuple[str, ...]
    honest_scope_limit: str = HONEST_SCOPE_LIMIT


def _canonical_sha256(payload: Any) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def verify_ideas_audit(
    tsv_bytes: bytes,
    *,
    known_catalogue_ids: set[int] | None = None,
    known_json_names: set[str] | None = None,
    verified_tokens: dict[str, bool] | None = None,
    min_verified_ratio: float = 0.0,
    require_all_built_verified: bool = False,
) -> IdeasAuditReport:
    """Run fail-closed schema and claim-to-receipt parity verification."""
    if not isinstance(tsv_bytes, (bytes, bytearray)):
        return _fail_report("tsv_bytes: expected bytes", "")
    if not isinstance(require_all_built_verified, bool):
        return _fail_report("require_all_built_verified: must be bool", "")
    raw_bytes = bytes(tsv_bytes)
    reg_sha = hashlib.sha256(raw_bytes).hexdigest()
    pre_errs = validate_ratio_threshold(min_verified_ratio, "min_verified_ratio")
    clean_cids, cid_errs = validate_known_catalogue_ids(known_catalogue_ids)
    pre_errs.extend(cid_errs)
    if pre_errs:
        return _fail_report("; ".join(pre_errs), reg_sha)
    try:
        tsv_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return _fail_report("tsv_bytes: invalid UTF-8 encoding", reg_sha)
    rows, parse_errs = parse_ideas_register(tsv_text)
    part = classify_built_parity(
        rows,
        known_catalogue_ids=clean_cids,
        known_json_names=known_json_names,
        verified_tokens=verified_tokens,
    )
    return _finalize_report(
        rows,
        part,
        parse_errs,
        reg_sha,
        float(min_verified_ratio),
        require_all_built_verified,
    )


def _finalize_report(
    rows: list[IdeaRow],
    part: ParityPartition,
    parse_errs: list[str],
    reg_sha: str,
    min_ratio: float,
    require_all: bool,
) -> IdeasAuditReport:
    built = sum(1 for r in rows if r.status == "BUILT")
    partial = sum(1 for r in rows if r.status == "PARTIAL")
    unbuilt = sum(1 for r in rows if r.status == "UNBUILT")
    v_cnt = len(part.verified_match_ids)
    u_cnt = len(part.unverified_no_receipt_ids) + len(part.unverified_drift_ids)
    ratio = compute_match_ratio(v_cnt, built)
    violations = list(parse_errs) + list(part.violations)
    if require_all and u_cnt > 0:
        violations.append(f"unverified_built_rows: {u_cnt} BUILT rows unverified")
    if ratio < min_ratio:
        violations.append(
            f"verified_match_ratio {ratio:.6f} < min_verified_ratio {min_ratio:.6f}"
        )
    attest_payload = {
        "register_sha256": reg_sha,
        "total_rows": len(rows),
        "built_count": built,
        "partial_count": partial,
        "unbuilt_count": unbuilt,
        "verified_match_ids": list(part.verified_match_ids),
        "unverified_no_receipt_ids": list(part.unverified_no_receipt_ids),
        "unverified_drift_ids": list(part.unverified_drift_ids),
        "forged_catalogue_ids": list(part.forged_catalogue_ids),
    }
    return IdeasAuditReport(
        passed=len(violations) == 0,
        total_rows=len(rows),
        built_count=built,
        partial_count=partial,
        unbuilt_count=unbuilt,
        verified_match_count=v_cnt,
        unverified_count=u_cnt,
        verified_match_ratio=ratio,
        forged_catalogue_ids=part.forged_catalogue_ids,
        unverified_no_receipt_ids=part.unverified_no_receipt_ids,
        unverified_drift_ids=part.unverified_drift_ids,
        register_sha256=reg_sha,
        ideas_attestation_sha256=_canonical_sha256(attest_payload),
        violations=tuple(violations),
    )


def _fail_report(message: str, reg_sha: str) -> IdeasAuditReport:
    return IdeasAuditReport(
        passed=False,
        total_rows=0,
        built_count=0,
        partial_count=0,
        unbuilt_count=0,
        verified_match_count=0,
        unverified_count=0,
        verified_match_ratio=0.0,
        forged_catalogue_ids=(),
        unverified_no_receipt_ids=(),
        unverified_drift_ids=(),
        register_sha256=reg_sha,
        ideas_attestation_sha256="",
        violations=(message,),
    )


def verify_ideas_audit_files(
    tsv_path: Path | str,
    *,
    receipt_index_path: Path | str | None = None,
    verified_tokens: dict[str, bool] | None = None,
    min_verified_ratio: float = 0.0,
    require_all_built_verified: bool = False,
) -> IdeasAuditReport:
    """Load register TSV and optional receipt index from disk and verify."""
    try:
        tsv_bytes = Path(tsv_path).read_bytes()
    except OSError as exc:
        return _fail_report(f"io_error: {exc}", "")
    known_cids: set[int] | None = None
    known_jsons: set[str] | None = None
    if receipt_index_path is not None:
        try:
            idx_text = Path(receipt_index_path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return _fail_report(f"receipt_index_io_error: {exc}", "")
        parsed_idx, idx_errs = parse_receipt_index(idx_text)
        if idx_errs:
            return _fail_report("; ".join(idx_errs), "")
        known_cids = set(parsed_idx.cid_to_path)
        known_jsons = set(parsed_idx.file_to_path)
    return verify_ideas_audit(
        tsv_bytes,
        known_catalogue_ids=known_cids,
        known_json_names=known_jsons,
        verified_tokens=verified_tokens,
        min_verified_ratio=min_verified_ratio,
        require_all_built_verified=require_all_built_verified,
    )
