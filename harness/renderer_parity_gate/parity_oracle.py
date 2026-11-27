# SPDX-License-Identifier: MIT
"""Fail-closed Flywheel oracle for C++23 <-> BuildLang 0-ULP renderer parity.

Verifies module coverage (#12..#24+), strict 0-ULP bit-exactness, 64-bit
FNV-1a IEEE-754 pin integrity, planted perturbation control rejections, live
catalogue/receipt provenance, and deterministic attestation hashing.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .parity_parser import RendererParityRow, parse_renderer_parity_tsv
from .pin_guards import (
    canonical_sha256_hex,
    is_strict_finite_float,
    is_strict_int,
    normalize_fnv1a_pin,
)

HONEST_SCOPE_LIMIT = (
    "Verifies 0-ULP renderer parity index integrity, FNV-1a pin matching, "
    "planted perturbation rejection flags, and caller-supplied catalogue or "
    "receipt match verdicts in pure Python stdlib. Does not execute live GPU "
    "or C++23 binaries."
)


@dataclass(frozen=True)
class RendererParityReport:
    """Fail-closed attestation verdict for C++23 <-> BuildLang parity."""

    passed: bool
    module_count: int
    min_module_num: int
    max_module_num: int
    zero_ulp_count: int
    planted_controls_caught: int
    index_sha256: str
    renderer_parity_attestation_sha256: str
    violations: tuple[str, ...]
    honest_scope_limit: str = HONEST_SCOPE_LIMIT


def _validate_policy_params(
    max_ulp_err: float,
    expected_range: tuple[int, int] | None,
    known_cids: set[int] | None,
) -> list[str]:
    errors: list[str] = []
    if not is_strict_finite_float(max_ulp_err) or float(max_ulp_err) < 0.0:
        errors.append(f"max_ulp_err: invalid {max_ulp_err!r}")
    if expected_range is not None:
        if (
            not isinstance(expected_range, tuple)
            or len(expected_range) != 2
            or not is_strict_int(expected_range[0])
            or not is_strict_int(expected_range[1])
            or expected_range[0] <= 0
            or expected_range[1] < expected_range[0]
        ):
            errors.append(f"expected_module_range: invalid {expected_range!r}")
    if known_cids is not None:
        for cid in known_cids:
            if not is_strict_int(cid) or cid <= 0:
                errors.append(f"known_catalogue_ids: invalid ID {cid!r}")
                break
    return errors


def _check_rows_against_policy(
    rows: list[RendererParityRow],
    max_ulp: float,
    expected_range: tuple[int, int] | None,
    known_cids: set[int] | None,
    expected_fnv_pins: dict[str, str] | None,
    receipt_verdicts: dict[int, bool] | None,
) -> list[str]:
    errors: list[str] = []
    if not rows:
        return ["parity_tsv: zero valid module rows"]
    for row in rows:
        if row.ulp_err > max_ulp:
            errors.append(f"{row.module_name}: ulp_err {row.ulp_err} > {max_ulp}")
        if row.planted_ctrl_caught != 1:
            errors.append(f"{row.module_name}: planted control not caught")
        if known_cids is not None and row.catalogue_id not in known_cids:
            errors.append(
                f"{row.module_name}: forged or absent catalogue_id {row.catalogue_id}"
            )
        if receipt_verdicts is not None and receipt_verdicts.get(row.catalogue_id) is not True:
            errors.append(f"{row.module_name}: receipt {row.catalogue_id} not MATCH")
        if expected_fnv_pins is not None and row.module_name in expected_fnv_pins:
            exp_pin, pin_err = normalize_fnv1a_pin(
                expected_fnv_pins[row.module_name], f"expected[{row.module_name}]"
            )
            if pin_err or exp_pin != row.fnv1a_pin:
                errors.append(
                    f"{row.module_name}: FNV-1a pin mismatch {row.fnv1a_pin} != {exp_pin}"
                )
    if expected_range is not None:
        got_nums = {r.module_num for r in rows}
        want_nums = set(range(expected_range[0], expected_range[1] + 1))
        missing = sorted(want_nums - got_nums)
        if missing:
            errors.append(f"module_range: missing module numbers {missing}")
    return errors


def verify_renderer_parity(
    tsv_bytes: bytes,
    *,
    max_ulp_err: float = 0.0,
    expected_module_range: tuple[int, int] | None = None,
    known_catalogue_ids: set[int] | None = None,
    expected_fnv_pins: dict[str, str] | None = None,
    receipt_verdicts: dict[int, bool] | None = None,
) -> RendererParityReport:
    """Run fail-closed verification on renderer parity TSV bytes."""
    if not isinstance(tsv_bytes, (bytes, bytearray)):
        return _fail_report("tsv_bytes: expected bytes", "")
    raw = bytes(tsv_bytes)
    idx_sha = hashlib.sha256(raw).hexdigest()
    pre_errs = _validate_policy_params(
        max_ulp_err, expected_module_range, known_catalogue_ids
    )
    if pre_errs:
        return _fail_report("; ".join(pre_errs), idx_sha)
    try:
        tsv_text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return _fail_report("tsv_bytes: invalid UTF-8", idx_sha)
    rows, parse_errs = parse_renderer_parity_tsv(tsv_text)
    policy_errs = _check_rows_against_policy(
        rows,
        float(max_ulp_err),
        expected_module_range,
        known_catalogue_ids,
        expected_fnv_pins,
        receipt_verdicts,
    )
    return _build_report(rows, idx_sha, parse_errs + policy_errs)


def _build_report(
    rows: list[RendererParityRow],
    idx_sha: str,
    violations: list[str],
) -> RendererParityReport:
    ordered = sorted(rows, key=lambda r: r.module_num)
    min_num = ordered[0].module_num if ordered else 0
    max_num = ordered[-1].module_num if ordered else 0
    zero_ulp = sum(1 for r in ordered if r.ulp_err == 0.0)
    ctrl_caught = sum(1 for r in ordered if r.planted_ctrl_caught == 1)
    attest = {
        "index_sha256": idx_sha,
        "module_count": len(ordered),
        "modules": [
            {
                "module_num": r.module_num,
                "module_name": r.module_name,
                "catalogue_id": r.catalogue_id,
                "fnv1a_pin": r.fnv1a_pin,
                "ulp_err": r.ulp_err,
                "planted_ctrl_caught": r.planted_ctrl_caught,
            }
            for r in ordered
        ],
    }
    return RendererParityReport(
        passed=len(violations) == 0,
        module_count=len(ordered),
        min_module_num=min_num,
        max_module_num=max_num,
        zero_ulp_count=zero_ulp,
        planted_controls_caught=ctrl_caught,
        index_sha256=idx_sha,
        renderer_parity_attestation_sha256=canonical_sha256_hex(attest),
        violations=tuple(violations),
    )


def _fail_report(message: str, idx_sha: str) -> RendererParityReport:
    return RendererParityReport(
        passed=False,
        module_count=0,
        min_module_num=0,
        max_module_num=0,
        zero_ulp_count=0,
        planted_controls_caught=0,
        index_sha256=idx_sha,
        renderer_parity_attestation_sha256="",
        violations=(message,),
    )


def verify_renderer_parity_files(
    tsv_path: Path | str,
    *,
    max_ulp_err: float = 0.0,
    expected_module_range: tuple[int, int] | None = None,
    known_catalogue_ids: set[int] | None = None,
    expected_fnv_pins: dict[str, str] | None = None,
    receipt_verdicts: dict[int, bool] | None = None,
) -> RendererParityReport:
    """Load renderer_parity_index.tsv from disk and verify fail-closed."""
    try:
        raw = Path(tsv_path).read_bytes()
    except OSError as exc:
        return _fail_report(f"io_error: {exc}", "")
    return verify_renderer_parity(
        raw,
        max_ulp_err=max_ulp_err,
        expected_module_range=expected_module_range,
        known_catalogue_ids=known_catalogue_ids,
        expected_fnv_pins=expected_fnv_pins,
        receipt_verdicts=receipt_verdicts,
    )
