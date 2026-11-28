# SPDX-License-Identifier: MIT
"""Typed parsers for Slice 36 Threshold HSM and Slice 37 Erasure RAID-6 receipts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from harness.threshold_storage_attest.storage_guards import (
    HEX_64_RE,
    StorageAttestError,
    classify_isa_relpath,
    require_dict,
    require_int,
    require_list,
    require_prefixed_sha256,
    require_str,
    validate_safe_relpath,
)

RECEIPT_SCHEMA = "engine-receipt/1"
HSM_ROOT_RE = re.compile(r'"hsm_audit_root_hex"\s*:\s*"([0-9a-f]{64})"')
RAID_ROOT_RE = re.compile(r'"raid_merkle_root_hex"\s*:\s*"([0-9a-f]{64})"')
BIN_COUNT_RE = re.compile(r'"total_verified_zero_c_binaries"\s*:\s*(\d+)')
EXCERPT_SCHEMA_RE = re.compile(r'"schema"\s*:\s*"([^"]+)"')
EXCERPT_OK_RE = re.compile(r'"ok"\s*:\s*(true|false)')
EXCERPT_INT_RE = {
    "t": re.compile(r'"t"\s*:\s*(\d+)'),
    "n": re.compile(r'"n"\s*:\s*(\d+)'),
    "k": re.compile(r'"k"\s*:\s*(\d+)'),
    "m": re.compile(r'"m"\s*:\s*(\d+)'),
    "healed_patterns": re.compile(r'"healed_patterns"\s*:\s*(\d+)'),
}


@dataclass(frozen=True)
class IsaBinaryRecord:
    isa: str
    rel_path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class SliceReceiptSummary:
    label: str
    task_id: str
    engine: str
    verdict: str
    exit_code: int
    claim_sha256: str
    subject_sha256: str
    envelope_sha256: str
    source_bld_relpath: str | None
    isa_binaries: tuple[IsaBinaryRecord, ...]
    excerpt_schema: str
    excerpt_ok: bool
    merkle_root_hex: str
    total_verified_zero_c_binaries: int
    params: dict[str, int]
    attacks_caught: int | None
    attacks_total: int | None


@dataclass(frozen=True)
class ThresholdStorageBundle:
    hsm: SliceReceiptSummary
    raid: SliceReceiptSummary


def _extract_excerpt_fields(
    excerpt: str,
    root_pattern: re.Pattern[str],
    param_keys: tuple[str, ...],
    label: str,
) -> tuple[str, bool, str, int, dict[str, int]]:
    sch_m = EXCERPT_SCHEMA_RE.search(excerpt)
    ok_m = EXCERPT_OK_RE.search(excerpt)
    root_m = root_pattern.search(excerpt)
    bin_m = BIN_COUNT_RE.search(excerpt)
    if not sch_m or not ok_m or not root_m or not bin_m:
        raise StorageAttestError(
            f"{label}: oracle stdout_excerpt missing required proof markers"
        )
    root_hex = root_m.group(1)
    if not HEX_64_RE.match(root_hex):
        raise StorageAttestError(f"{label}: invalid 64-hex RFC 6962 merkle root")
    params: dict[str, int] = {}
    for pk in param_keys:
        pm = EXCERPT_INT_RE[pk].search(excerpt)
        if not pm:
            raise StorageAttestError(
                f"{label}: oracle stdout_excerpt missing param '{pk}'"
            )
        params[pk] = int(pm.group(1))
    return (
        sch_m.group(1),
        ok_m.group(1) == "true",
        root_hex,
        int(bin_m.group(1)),
        params,
    )


def _extract_artifacts(
    subject: dict[str, Any],
    label: str,
) -> tuple[str | None, tuple[IsaBinaryRecord, ...]]:
    src_bld: str | None = None
    bins: list[IsaBinaryRecord] = []
    for idx, entry in enumerate(require_list(subject, "artifacts", f"{label}.subject")):
        if not isinstance(entry, dict):
            raise StorageAttestError(f"{label}: artifacts[{idx}] must be an object")
        al = f"{label}.artifacts[{idx}]"
        rel = require_str(entry, "rel_path", al)
        validate_safe_relpath(rel, al)
        size = require_int(entry, "bytes", al, minimum=1)
        sha = require_prefixed_sha256(entry, "sha256", al)
        if rel.endswith(".bld"):
            src_bld = rel
        isa = classify_isa_relpath(rel)
        if isa is not None:
            bins.append(
                IsaBinaryRecord(isa=isa, rel_path=rel, size_bytes=size, sha256=sha)
            )
    return src_bld, tuple(bins)


def _parse_attack_counts(
    attack_summary: dict[str, Any] | None,
    label: str,
) -> tuple[int | None, int | None]:
    if attack_summary is None:
        return None, None
    caught = require_int(attack_summary, "attacks_caught", f"{label}.attacks")
    total = require_int(attack_summary, "attacks_total", f"{label}.attacks", minimum=1)
    return caught, total


def _parse_digests(raw: dict[str, Any], label: str) -> tuple[str, str, str]:
    digests = require_dict(raw, "digests", label)
    dl = f"{label}.digests"
    return (
        require_prefixed_sha256(digests, "claim_sha256", dl),
        require_prefixed_sha256(digests, "subject_sha256", dl),
        require_prefixed_sha256(digests, "envelope_sha256", dl),
    )


def parse_slice_receipt(
    raw: dict[str, Any],
    *,
    slice_kind: str,
    attack_summary: dict[str, Any] | None = None,
) -> SliceReceiptSummary:
    """Parse an engine-receipt/1 file for Slice 36 (hsm) or Slice 37 (raid)."""
    if slice_kind not in ("hsm", "raid"):
        raise StorageAttestError(f"unsupported slice_kind: {slice_kind!r}")
    if require_str(raw, "schema", slice_kind) != RECEIPT_SCHEMA:
        raise StorageAttestError(f"{slice_kind}: unexpected receipt schema")
    claim_sha, subj_sha, env_sha = _parse_digests(raw, slice_kind)
    oracle = require_dict(raw, "oracle", slice_kind)
    subject = require_dict(raw, "subject", slice_kind)
    src_bld, isa_bins = _extract_artifacts(subject, slice_kind)
    root_pat = HSM_ROOT_RE if slice_kind == "hsm" else RAID_ROOT_RE
    pkeys = ("t", "n") if slice_kind == "hsm" else ("k", "m", "healed_patterns")
    excerpt = require_str(oracle, "stdout_excerpt", f"{slice_kind}.oracle")
    ex_schema, ex_ok, root_hex, bin_cnt, params = _extract_excerpt_fields(
        excerpt, root_pat, pkeys, slice_kind
    )
    atk_caught, atk_total = _parse_attack_counts(attack_summary, slice_kind)
    return SliceReceiptSummary(
        label=slice_kind,
        task_id=require_str(subject, "task_id", f"{slice_kind}.subject"),
        engine=require_str(subject, "engine", f"{slice_kind}.subject"),
        verdict=require_str(raw, "verdict", slice_kind),
        exit_code=require_int(oracle, "exit_code", f"{slice_kind}.oracle", minimum=0),
        claim_sha256=claim_sha,
        subject_sha256=subj_sha,
        envelope_sha256=env_sha,
        source_bld_relpath=src_bld,
        isa_binaries=isa_bins,
        excerpt_schema=ex_schema,
        excerpt_ok=ex_ok,
        merkle_root_hex=root_hex,
        total_verified_zero_c_binaries=bin_cnt,
        params=params,
        attacks_caught=atk_caught,
        attacks_total=atk_total,
    )
