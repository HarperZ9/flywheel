# SPDX-License-Identifier: MIT
"""Pure-stdlib parser for Zero-C 5-ISA BuildOS slices index and receipts.

Parses the 10-column buildos_zeroc_slices_index.tsv table and extracts 5-ISA
Zero-C binary records from canonical engine-receipt/1 JSON envelopes.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Any

from .isa_guards import (
    REQUIRED_ISAS,
    REQUIRED_SLICE_COLUMNS,
    normalize_sha256,
    parse_strict_nonneg_int,
    parse_strict_positive_int,
)

HONEST_SCOPE_LIMIT = (
    "Parses Zero-C BuildOS slice index tables and engine-receipt/1 subject "
    "artifact arrays in pure Python stdlib. Does not execute BuildOS binaries."
)


@dataclass(frozen=True)
class ZeroCSliceBinary:
    """One validated 5-ISA binary entry belonging to a Zero-C BuildOS slice."""

    slice_id: str
    catalogue_id: int
    receipt_path: str
    isa: str
    zero_c: int
    runs_verified: int
    attacks_caught: int
    bin_path: str
    bin_bytes: int
    bin_sha256: str


def infer_isa_from_rel_path(rel_path: str) -> str | None:
    """Map a BuildOS output binary filename to one of the 5 target ISAs."""
    low = rel_path.strip().lower()
    if low.endswith(".aarch64.elf"):
        return "aarch64-elf"
    if low.endswith(".rv64.elf"):
        return "rv64-elf"
    if low.endswith(".x64.elf"):
        return "x64-elf"
    if low.endswith(".exe"):
        return "x64-pe"
    if low.endswith(".wasm"):
        return "wasm"
    return None


def parse_slices_index_tsv(
    tsv_text: str,
) -> tuple[list[ZeroCSliceBinary], list[str]]:
    """Parse and validate 10-column buildos_zeroc_slices_index.tsv text."""
    if not isinstance(tsv_text, str) or not tsv_text.strip():
        return [], ["slices_tsv: empty or non-string input"]
    reader = csv.reader(io.StringIO(tsv_text), delimiter="\t")
    rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows:
        return [], ["slices_tsv: missing header row"]
    header = tuple(col.strip() for col in rows[0])
    if header != REQUIRED_SLICE_COLUMNS:
        return [], [f"slices_tsv: header mismatch {header!r}"]
    return _parse_body(rows[1:])


def _parse_body(
    body: list[list[str]],
) -> tuple[list[ZeroCSliceBinary], list[str]]:
    records: list[ZeroCSliceBinary] = []
    errors: list[str] = []
    for line_no, cols in enumerate(body, start=2):
        rec, row_errs = _parse_one_row(cols, line_no)
        errors.extend(row_errs)
        if rec is not None:
            records.append(rec)
    return records, errors


def _parse_one_row(
    cols: list[str],
    line_no: int,
) -> tuple[ZeroCSliceBinary | None, list[str]]:
    if len(cols) != len(REQUIRED_SLICE_COLUMNS):
        return None, [f"slices_tsv:L{line_no}: expected 10 cols, got {len(cols)}"]
    errs: list[str] = []
    sid = cols[0].strip()
    isa = cols[3].strip()
    if not sid:
        errs.append(f"slices_tsv:L{line_no}: empty slice_id")
    if isa not in REQUIRED_ISAS:
        errs.append(f"slices_tsv:L{line_no}({sid}): unknown ISA {isa!r}")
    cid, e1 = parse_strict_positive_int(cols[1], f"L{line_no}.catalogue_id")
    zc, e2 = parse_strict_nonneg_int(cols[4], f"L{line_no}.zero_c")
    runs, e3 = parse_strict_nonneg_int(cols[5], f"L{line_no}.runs_verified")
    att, e4 = parse_strict_nonneg_int(cols[6], f"L{line_no}.attacks_caught")
    bbytes, e5 = parse_strict_positive_int(cols[8], f"L{line_no}.bin_bytes")
    bsha, e6 = normalize_sha256(cols[9], f"L{line_no}.bin_sha256")
    for err in (e1, e2, e3, e4, e5, e6):
        if err:
            errs.append(err)
    if errs or None in (cid, zc, runs, att, bbytes, bsha):
        return None, errs
    return ZeroCSliceBinary(
        sid, cid, cols[2].strip(), isa, zc, runs, att, cols[7].strip(), bbytes, bsha
    ), []


def extract_slice_binaries_from_receipt(
    slice_id: str,
    catalogue_id: int,
    receipt_obj: Any,
    *,
    receipt_path: str = "",
    runs_verified: int = 25,
    attacks_caught: int = 4,
) -> tuple[list[ZeroCSliceBinary], list[str]]:
    """Extract 5-ISA Zero-C binary records from an engine-receipt/1 JSON dict."""
    if not isinstance(receipt_obj, dict):
        return [], [f"{slice_id}: receipt must be a JSON object"]
    subj = receipt_obj.get("subject")
    if not isinstance(subj, dict) or not isinstance(subj.get("artifacts"), list):
        return [], [f"{slice_id}: missing subject.artifacts list"]
    art_paths = receipt_obj.get("artifact_paths")
    path_map = art_paths if isinstance(art_paths, dict) else {}
    records: list[ZeroCSliceBinary] = []
    errors: list[str] = []
    for item in subj["artifacts"]:
        if not isinstance(item, dict):
            continue
        rel = str(item.get("rel_path", "")).strip()
        isa = infer_isa_from_rel_path(rel)
        if isa is None:
            continue
        bbytes, e1 = parse_strict_positive_int(item.get("bytes"), f"{slice_id}.{isa}.bytes")
        bsha, e2 = normalize_sha256(item.get("sha256"), f"{slice_id}.{isa}.sha256")
        if e1 or e2 or bbytes is None or bsha is None:
            errors.extend([e for e in (e1, e2) if e])
            continue
        records.append(
            ZeroCSliceBinary(
                slice_id=slice_id,
                catalogue_id=catalogue_id,
                receipt_path=receipt_path,
                isa=isa,
                zero_c=1,
                runs_verified=runs_verified,
                attacks_caught=attacks_caught,
                bin_path=str(path_map.get(rel, rel)),
                bin_bytes=bbytes,
                bin_sha256=bsha,
            )
        )
    return records, errors
