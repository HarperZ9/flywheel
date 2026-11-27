# SPDX-License-Identifier: MIT
"""Fail-closed Flywheel oracle for BuildDB Parquet V5 and JFC3P RLVR v8 packs.

Verifies manifest integrity, zero non-MIT rows, zero duplicate IDs, exact
train/eval split disjointness, 100% oracle pass-rate floor, strict SHA-256
and IEEE-754 finite guards, and deterministic dataset_attestation_sha256.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .dataset_guards import (
    canonical_sha256_hex,
    is_mit_license,
    is_strict_finite_float,
    is_strict_int,
    validate_pass_rate,
    verify_manifest_artifacts,
)
from .jsonl_auditor import (
    JsonlAuditStats,
    audit_builddb_jsonl,
    audit_rlvr_split_jsonl,
)

HONEST_SCOPE_LIMIT = (
    "Verifies BuildDB V5 and JFC3P RLVR v8 manifests and JSONL splits for "
    "MIT license purity, ID uniqueness, train/eval disjointness, artifact "
    "SHA-256 digests, and finite oracle pass-rate floors in pure Python "
    "stdlib. Does not run model fine-tuning or parse Parquet binaries."
)


@dataclass(frozen=True)
class DatasetAttestReport:
    """Fail-closed attestation verdict for BuildDB + RLVR dataset packs."""

    passed: bool
    builddb_rows: int
    rlvr_total_tasks: int
    rlvr_train_tasks: int
    rlvr_eval_tasks: int
    non_mit_rows: int
    duplicate_ids: int
    train_eval_overlap: int
    oracle_pass_rate: float
    dataset_attestation_sha256: str
    violations: tuple[str, ...]
    honest_scope_limit: str = HONEST_SCOPE_LIMIT


def _validate_v5_manifest(
    v5: Any,
    bdb_stats: JsonlAuditStats,
    actual_hashes: dict[str, tuple[int, str]] | None,
) -> tuple[dict[str, str], list[str]]:
    digests, errs = verify_manifest_artifacts(v5, "v5_manifest", actual_hashes)
    if not isinstance(v5, dict):
        return digests, errs
    if not is_mit_license(v5.get("license")):
        errs.append(f"v5_manifest.license: expected MIT, got {v5.get('license')!r}")
    nm = v5.get("non_mit_rows")
    if not is_strict_int(nm) or nm != 0:
        errs.append(f"v5_manifest.non_mit_rows: expected 0, got {nm!r}")
    tot = v5.get("total_rows")
    if not is_strict_int(tot) or tot != bdb_stats.row_count:
        errs.append(f"v5_manifest.total_rows: {tot!r} != actual {bdb_stats.row_count}")
    counts = v5.get("record_type_counts")
    if isinstance(counts, dict) and all(is_strict_int(v) and v >= 0 for v in counts.values()):
        if sum(counts.values()) != bdb_stats.row_count:
            errs.append("v5_manifest.record_type_counts sum mismatch")
    else:
        errs.append("v5_manifest.record_type_counts: invalid mapping")
    comp = v5.get("compression")
    if isinstance(comp, dict) and "ratio_x" in comp:
        if not is_strict_finite_float(comp["ratio_x"]) or float(comp["ratio_x"]) <= 0.0:
            errs.append("v5_manifest.compression.ratio_x: invalid ratio")
    return digests, errs


def _validate_v8_manifest(
    v8: Any,
    tr_stats: JsonlAuditStats,
    ev_stats: JsonlAuditStats,
    actual_hashes: dict[str, tuple[int, str]] | None,
) -> tuple[dict[str, str], list[str]]:
    digests, errs = verify_manifest_artifacts(v8, "v8_manifest", actual_hashes)
    if not isinstance(v8, dict):
        return digests, errs
    if not is_mit_license(v8.get("license")):
        errs.append(f"v8_manifest.license: expected MIT, got {v8.get('license')!r}")
    t_cnt = v8.get("train_tasks")
    e_cnt = v8.get("eval_tasks")
    tot = v8.get("total_tasks")
    if not is_strict_int(t_cnt) or t_cnt != tr_stats.row_count:
        errs.append(f"v8_manifest.train_tasks: {t_cnt!r} != {tr_stats.row_count}")
    if not is_strict_int(e_cnt) or e_cnt != ev_stats.row_count:
        errs.append(f"v8_manifest.eval_tasks: {e_cnt!r} != {ev_stats.row_count}")
    if not is_strict_int(tot) or tot != tr_stats.row_count + ev_stats.row_count:
        errs.append(f"v8_manifest.total_tasks: {tot!r} != train + eval")
    return digests, errs


def verify_dataset_pack(
    v5_manifest: Any,
    v8_manifest: Any,
    builddb_jsonl: str,
    train_jsonl: str,
    eval_jsonl: str,
    *,
    oracle_pass_rate: float = 1.0,
    min_oracle_pass_rate: float = 1.0,
    actual_hashes: dict[str, tuple[int, str]] | None = None,
) -> DatasetAttestReport:
    """Run fail-closed verification across BuildDB V5 and RLVR v8 datasets."""
    rate_errs = validate_pass_rate(oracle_pass_rate, "oracle_pass_rate")
    rate_errs.extend(validate_pass_rate(min_oracle_pass_rate, "min_oracle_pass_rate"))
    if rate_errs:
        return _fail_report("; ".join(rate_errs))
    bdb = audit_builddb_jsonl(builddb_jsonl)
    tr = audit_rlvr_split_jsonl(train_jsonl, "train")
    ev = audit_rlvr_split_jsonl(eval_jsonl, "eval")
    overlap = sorted(tr.unique_ids & ev.unique_ids)
    v5_dig, v5_errs = _validate_v5_manifest(v5_manifest, bdb, actual_hashes)
    v8_dig, v8_errs = _validate_v8_manifest(v8_manifest, tr, ev, actual_hashes)
    violations = list(bdb.violations) + list(tr.violations) + list(ev.violations) + v5_errs + v8_errs
    if overlap:
        violations.append(f"train_eval_overlap: {len(overlap)} shared task IDs ({overlap[:3]})")
    if float(oracle_pass_rate) < float(min_oracle_pass_rate):
        violations.append(
            f"oracle_pass_rate {oracle_pass_rate} < floor {min_oracle_pass_rate}"
        )
    return _build_report(bdb, tr, ev, len(overlap), float(oracle_pass_rate), v5_dig, v8_dig, violations)


def _build_report(
    bdb: JsonlAuditStats,
    tr: JsonlAuditStats,
    ev: JsonlAuditStats,
    overlap_count: int,
    pass_rate: float,
    v5_dig: dict[str, str],
    v8_dig: dict[str, str],
    violations: list[str],
) -> DatasetAttestReport:
    non_mit = bdb.non_mit_count + tr.non_mit_count + ev.non_mit_count
    dup_cnt = len(bdb.duplicate_ids) + len(tr.duplicate_ids) + len(ev.duplicate_ids)
    attest = {
        "builddb_rows": bdb.row_count,
        "rlvr_train_tasks": tr.row_count,
        "rlvr_eval_tasks": ev.row_count,
        "non_mit_rows": non_mit,
        "duplicate_ids": dup_cnt,
        "train_eval_overlap": overlap_count,
        "oracle_pass_rate": pass_rate,
        "v5_artifacts": v5_dig,
        "v8_artifacts": v8_dig,
    }
    return DatasetAttestReport(
        passed=len(violations) == 0,
        builddb_rows=bdb.row_count,
        rlvr_total_tasks=tr.row_count + ev.row_count,
        rlvr_train_tasks=tr.row_count,
        rlvr_eval_tasks=ev.row_count,
        non_mit_rows=non_mit,
        duplicate_ids=dup_cnt,
        train_eval_overlap=overlap_count,
        oracle_pass_rate=pass_rate,
        dataset_attestation_sha256=canonical_sha256_hex(attest),
        violations=tuple(violations),
    )


def _fail_report(message: str) -> DatasetAttestReport:
    return DatasetAttestReport(False, 0, 0, 0, 0, 0, 0, 0, 0.0, "", (message,))


def verify_dataset_pack_files(
    pack_dir: Path | str,
    *,
    oracle_pass_rate: float = 1.0,
    min_oracle_pass_rate: float = 1.0,
) -> DatasetAttestReport:
    """Load BuildDB V5 and RLVR v8 files from pack_dir and verify fail-closed."""
    root = Path(pack_dir)
    try:
        v5 = json.loads((root / "v5_manifest.json").read_text(encoding="utf-8"))
        v8 = json.loads((root / "v8_rlvr_manifest.json").read_text(encoding="utf-8"))
        bdb_txt = (root / "builddb_v5_mit.jsonl").read_text(encoding="utf-8")
        tr_txt = (root / "train_rlvr_v8.jsonl").read_text(encoding="utf-8")
        ev_txt = (root / "eval_rlvr_v8.jsonl").read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return _fail_report(f"io_error: {exc}")
    actual_hashes: dict[str, tuple[int, str]] = {}
    for fname in (
        "builddb_v5_mit.jsonl",
        "builddb_v5_mit.parquet",
        "train_rlvr_v8.jsonl",
        "eval_rlvr_v8.jsonl",
        "jfc3p_14b_oracle_v8_mit.jsonl",
        "JFC3P_14B_Oracle_v8_Colab_H100_Ready.ipynb",
    ):
        fp = root / fname
        if fp.is_file():
            data = fp.read_bytes()
            actual_hashes[fname] = (len(data), hashlib.sha256(data).hexdigest())
    return verify_dataset_pack(
        v5,
        v8,
        bdb_txt,
        tr_txt,
        ev_txt,
        oracle_pass_rate=oracle_pass_rate,
        min_oracle_pass_rate=min_oracle_pass_rate,
        actual_hashes=actual_hashes,
    )
