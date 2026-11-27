# SPDX-License-Identifier: MIT
"""Fail-closed oracle and CLI for RSI Pareto orchestration and WASM 100-packs."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from harness.rsi_pareto_gate.rsi_guards import (
    DEFAULT_MAX_3WAY_ERR,
    DEFAULT_MAX_WASM_PACK_BYTES,
    DEFAULT_MIN_ZERO_IMPORT_WASM,
    DEFAULT_REQUIRED_WASM_MODULES,
    RsiGateError,
    load_json_object,
    validate_relative_wasm_path,
    verify_wasm_file_on_disk,
)
from harness.rsi_pareto_gate.rsi_parser import (
    RsiParetoReport,
    WasmPackManifest,
    parse_rsi_pareto_report,
    parse_wasm_pack_manifest,
)


@dataclass(frozen=True)
class RsiParetoVerdict:
    passed: bool
    compound_gain_x: float
    goodhart_rollback_pct: float
    max_3way_err: float
    wasm_module_count: int
    wasm_total_bytes: int
    wasm_disk_checked: int
    reasons: tuple[str, ...]


def _check_rsi_report(
    rep: RsiParetoReport,
    max_3way_err: float,
    reasons: list[str],
) -> None:
    if not rep.ok or rep.verdict != "PASS":
        reasons.append("rsi: ok is false or verdict != PASS")
    if rep.initial_score <= 0.0 or rep.final_score <= rep.initial_score:
        reasons.append("rsi: non-monotonic or non-positive score trajectory")
    expected_gain = (
        rep.final_score / rep.initial_score if rep.initial_score > 0.0 else 0.0
    )
    if rep.compound_gain_x <= 1.0 or abs(rep.compound_gain_x - expected_gain) > 1e-3:
        reasons.append("rsi: compound_gain_x <= 1.0 or inconsistent with scores")
    if (
        rep.goodhart_traps_total <= 0.0
        or rep.goodhart_traps_blocked != rep.goodhart_traps_total
    ):
        reasons.append("rsi: goodhart rollback rate below 100%")
    if rep.regressions != 0.0 or rep.failures != 0.0 or rep.monotonic_ok != 1.0:
        reasons.append("rsi: regressions, failures, or non-monotonic cycle detected")
    if rep.max_3way_err < 0.0 or rep.max_3way_err > max_3way_err:
        reasons.append("rsi: 3-way parity error exceeds ceiling")
    controls_ok = (
        rep.ctrl1_goodhart_rolled_back
        and rep.ctrl2_nonpos_budget_trapped
        and rep.ctrl3_forged_superopt_cert_rejected
    )
    if (
        not controls_ok
        or rep.controls_caught < 3
        or rep.controls_caught != rep.controls_total
    ):
        reasons.append("rsi: planted negative controls incomplete")


def _check_wasm_pack(
    pack: WasmPackManifest,
    required_modules: int,
    min_zero_import: int,
    max_pack_bytes: int,
    pack_root: Path | None,
    reasons: list[str],
) -> int:
    if pack.license != "MIT":
        reasons.append(f"wasm_pack: non-MIT top-level license '{pack.license}'")
    if pack.module_count != required_modules or len(pack.modules) != pack.module_count:
        reasons.append("wasm_pack: module_count mismatch or below required pack size")
    if (
        pack.zero_import_count < min_zero_import
        or pack.zero_import_count > pack.module_count
    ):
        reasons.append("wasm_pack: zero_import_count out of bounds")
    if not pack.under_1_25mb or pack.total_bytes > max_pack_bytes:
        reasons.append("wasm_pack: total_bytes exceeds 1.25 MiB budget")
    if sum(m.wasm_bytes for m in pack.modules) != pack.total_bytes:
        reasons.append("wasm_pack: module wasm_bytes sum != total_bytes")
    seen_slugs: set[str] = set()
    disk_checked = 0
    for mod in pack.modules:
        if mod.license != "MIT":
            reasons.append(
                f"wasm_pack: module '{mod.slug}' non-MIT license '{mod.license}'"
            )
        if mod.slug in seen_slugs:
            reasons.append(f"wasm_pack: duplicate slug '{mod.slug}'")
        seen_slugs.add(mod.slug)
        if pack_root is not None:
            rel = validate_relative_wasm_path(mod.wasm_path, mod.slug)
            err = verify_wasm_file_on_disk(
                pack_root, rel, mod.wasm_bytes, mod.wasm_sha256
            )
            if err is not None:
                reasons.append(f"wasm_pack: {err}")
            else:
                disk_checked += 1
    return disk_checked


def verify_rsi_pareto_and_wasm_bundle(
    report: RsiParetoReport,
    wasm_pack: WasmPackManifest,
    *,
    max_3way_err: float = DEFAULT_MAX_3WAY_ERR,
    required_modules: int = DEFAULT_REQUIRED_WASM_MODULES,
    min_zero_import: int = DEFAULT_MIN_ZERO_IMPORT_WASM,
    max_pack_bytes: int = DEFAULT_MAX_WASM_PACK_BYTES,
    pack_root: Path | None = None,
) -> RsiParetoVerdict:
    """Verify both the RSI Pareto orchestrator report and MIT WASM 100-pack."""
    reasons: list[str] = []
    _check_rsi_report(report, max_3way_err, reasons)
    disk_checked = _check_wasm_pack(
        wasm_pack,
        required_modules,
        min_zero_import,
        max_pack_bytes,
        pack_root,
        reasons,
    )
    rollback_pct = (
        100.0 * report.goodhart_traps_blocked / report.goodhart_traps_total
        if report.goodhart_traps_total > 0.0
        else 0.0
    )
    return RsiParetoVerdict(
        passed=not reasons,
        compound_gain_x=report.compound_gain_x,
        goodhart_rollback_pct=rollback_pct,
        max_3way_err=report.max_3way_err,
        wasm_module_count=wasm_pack.module_count,
        wasm_total_bytes=wasm_pack.total_bytes,
        wasm_disk_checked=disk_checked,
        reasons=tuple(reasons),
    )


def verify_rsi_pareto_files(
    rsi_report_path: Path,
    wasm_manifest_path: Path,
    *,
    check_wasm_on_disk: bool = False,
    pack_root: Path | None = None,
    max_3way_err: float = DEFAULT_MAX_3WAY_ERR,
    required_modules: int = DEFAULT_REQUIRED_WASM_MODULES,
) -> RsiParetoVerdict:
    """Load, parse, and verify RSI Pareto report + WASM 100-pack manifest from disk."""
    try:
        report = parse_rsi_pareto_report(
            load_json_object(rsi_report_path, "rsi_report")
        )
        wasm_pack = parse_wasm_pack_manifest(
            load_json_object(wasm_manifest_path, "wasm_pack")
        )
    except RsiGateError as exc:
        return RsiParetoVerdict(
            passed=False,
            compound_gain_x=0.0,
            goodhart_rollback_pct=0.0,
            max_3way_err=float("inf"),
            wasm_module_count=0,
            wasm_total_bytes=0,
            wasm_disk_checked=0,
            reasons=(str(exc),),
        )
    resolved_root = (
        (pack_root or wasm_manifest_path.parent) if check_wasm_on_disk else None
    )
    return verify_rsi_pareto_and_wasm_bundle(
        report,
        wasm_pack,
        max_3way_err=max_3way_err,
        required_modules=required_modules,
        pack_root=resolved_root,
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point returning 0 on PASS and 2 on fail-closed rejection."""
    parser = argparse.ArgumentParser(
        description="Verify RSI Pareto orchestrator and Centennial MIT WASM 100-pack."
    )
    parser.add_argument("--rsi-report", type=Path, required=True)
    parser.add_argument("--wasm-manifest", type=Path, required=True)
    parser.add_argument("--check-wasm-on-disk", action="store_true")
    parser.add_argument("--pack-root", type=Path, default=None)
    parser.add_argument("--max-3way-err", type=float, default=DEFAULT_MAX_3WAY_ERR)
    args = parser.parse_args(argv)
    verdict = verify_rsi_pareto_files(
        args.rsi_report,
        args.wasm_manifest,
        check_wasm_on_disk=args.check_wasm_on_disk,
        pack_root=args.pack_root,
        max_3way_err=args.max_3way_err,
    )
    print(json.dumps(asdict(verdict), indent=2))
    return 0 if verdict.passed else 2


if __name__ == "__main__":
    sys.exit(main())
