# SPDX-License-Identifier: MIT
"""Pure-stdlib parser for the 8-column renderer_parity_index.tsv ledger.

Parses C++23-to-BuildLang 0-ULP renderer parity entries, validating header
columns, module numbering uniqueness, 64-bit FNV-1a pins, ULP errors, and
planted perturbation control flags.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

from .pin_guards import (
    normalize_fnv1a_pin,
    parse_strict_flag_01,
    parse_strict_positive_int,
    parse_strict_ulp,
)

HONEST_SCOPE_LIMIT = (
    "Parses and validates the 8-column renderer_parity_index.tsv schema, "
    "FNV-1a pin formatting, ULP values, and planted control flags in memory. "
    "Does not run C++ or BuildLang compilers."
)

REQUIRED_PARITY_COLUMNS: tuple[str, ...] = (
    "module_num",
    "module_name",
    "catalogue_id",
    "receipt_path",
    "bld_path",
    "fnv1a_pin",
    "ulp_err",
    "planted_ctrl_caught",
)


@dataclass(frozen=True)
class RendererParityRow:
    """One validated C++23 <-> BuildLang renderer parity module entry."""

    module_num: int
    module_name: str
    catalogue_id: int
    receipt_path: str
    bld_path: str
    fnv1a_pin: str
    ulp_err: float
    planted_ctrl_caught: int


def parse_renderer_parity_tsv(
    tsv_text: str,
) -> tuple[list[RendererParityRow], list[str]]:
    """Parse and validate 8-column renderer_parity_index.tsv text."""
    if not isinstance(tsv_text, str) or not tsv_text.strip():
        return [], ["parity_tsv: empty or non-string input"]
    reader = csv.reader(io.StringIO(tsv_text), delimiter="\t")
    rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows:
        return [], ["parity_tsv: missing header row"]
    header = tuple(col.strip() for col in rows[0])
    if header != REQUIRED_PARITY_COLUMNS:
        return [], [f"parity_tsv: header mismatch {header!r}"]
    return _parse_body(rows[1:])


def _parse_body(
    body: list[list[str]],
) -> tuple[list[RendererParityRow], list[str]]:
    records: list[RendererParityRow] = []
    errors: list[str] = []
    seen_nums: set[int] = set()
    seen_names: set[str] = set()
    for line_no, cols in enumerate(body, start=2):
        rec, row_errs = _parse_one_row(cols, line_no, seen_nums, seen_names)
        errors.extend(row_errs)
        if rec is not None:
            records.append(rec)
    return records, errors


def _parse_one_row(
    cols: list[str],
    line_no: int,
    seen_nums: set[int],
    seen_names: set[str],
) -> tuple[RendererParityRow | None, list[str]]:
    if len(cols) != len(REQUIRED_PARITY_COLUMNS):
        return None, [f"parity_tsv:L{line_no}: expected 8 cols, got {len(cols)}"]
    errs: list[str] = []
    mnum, e1 = parse_strict_positive_int(cols[0], f"L{line_no}.module_num")
    cid, e2 = parse_strict_positive_int(cols[2], f"L{line_no}.catalogue_id")
    pin, e3 = normalize_fnv1a_pin(cols[5], f"L{line_no}.fnv1a_pin")
    ulp, e4 = parse_strict_ulp(cols[6], f"L{line_no}.ulp_err")
    ctrl, e5 = parse_strict_flag_01(cols[7], f"L{line_no}.planted_ctrl_caught")
    for err in (e1, e2, e3, e4, e5):
        if err:
            errs.append(err)
    mname = cols[1].strip()
    if not mname.endswith(".bld"):
        errs.append(f"L{line_no}.module_name: expected .bld module, got {mname!r}")
    if mnum is not None:
        if mnum in seen_nums:
            errs.append(f"L{line_no}: duplicate module_num {mnum}")
        seen_nums.add(mnum)
    if mname in seen_names:
        errs.append(f"L{line_no}: duplicate module_name {mname}")
    seen_names.add(mname)
    if errs or mnum is None or cid is None or pin is None or ulp is None or ctrl is None:
        return None, errs
    return RendererParityRow(
        mnum, mname, cid, cols[3].strip(), cols[4].strip(), pin, ulp, ctrl
    ), []
