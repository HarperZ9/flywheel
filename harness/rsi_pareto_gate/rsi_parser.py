# SPDX-License-Identifier: MIT
"""Typed parsers for RSI Pareto orchestrator reports and MIT WASM 100-packs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from harness.rsi_pareto_gate.rsi_guards import (
    RsiGateError,
    require_bool,
    require_dict,
    require_finite_float,
    require_int,
    require_list,
    require_sha256,
    require_str,
    validate_relative_wasm_path,
)

RSI_REPORT_SCHEMA = "wave149b-rsi-pareto-orchestrator/1"
WASM_PACK_SCHEMA = "site-dropin-wasm-100pack/1"


@dataclass(frozen=True)
class RsiParetoReport:
    ok: bool
    verdict: str
    wasm_bytes: int
    cycles: int
    lanes: int
    initial_score: float
    final_score: float
    compound_gain_x: float
    goodhart_traps_total: float
    goodhart_traps_blocked: float
    regressions: float
    monotonic_ok: float
    failures: float
    max_3way_err: float
    ctrl1_goodhart_rolled_back: bool
    ctrl2_nonpos_budget_trapped: bool
    ctrl3_forged_superopt_cert_rejected: bool
    controls_caught: int
    controls_total: int


@dataclass(frozen=True)
class WasmModuleEntry:
    pack: int
    idea_id: str
    slug: str
    wasm_path: str
    wasm_bytes: int
    wasm_sha256: str
    license: str


@dataclass(frozen=True)
class WasmPackManifest:
    license: str
    module_count: int
    zero_import_count: int
    total_bytes: int
    under_1_25mb: bool
    modules: tuple[WasmModuleEntry, ...]


def parse_rsi_pareto_report(raw: dict[str, Any]) -> RsiParetoReport:
    """Parse a wave149b-rsi-pareto-orchestrator/1 report payload."""
    lbl = "rsi_report"
    schema = require_str(raw, "schema", lbl)
    if schema != RSI_REPORT_SCHEMA:
        raise RsiGateError(
            f"{lbl}: expected schema '{RSI_REPORT_SCHEMA}', got '{schema}'"
        )
    metrics = require_dict(raw, "metrics", lbl)
    parity = require_dict(raw, "parity", lbl)
    controls = require_dict(raw, "controls", lbl)
    return RsiParetoReport(
        ok=require_bool(raw, "ok", lbl),
        verdict=require_str(raw, "verdict", lbl),
        wasm_bytes=require_int(raw, "wasm_bytes", lbl, minimum=1),
        cycles=require_int(raw, "cycles", lbl, minimum=1),
        lanes=require_int(raw, "lanes", lbl, minimum=1),
        initial_score=require_finite_float(metrics, "initial_score", f"{lbl}.metrics"),
        final_score=require_finite_float(metrics, "final_score", f"{lbl}.metrics"),
        compound_gain_x=require_finite_float(
            metrics, "compound_gain_x", f"{lbl}.metrics"
        ),
        goodhart_traps_total=require_finite_float(
            metrics, "goodhart_traps_total", f"{lbl}.metrics"
        ),
        goodhart_traps_blocked=require_finite_float(
            metrics, "goodhart_traps_blocked", f"{lbl}.metrics"
        ),
        regressions=require_finite_float(metrics, "regressions", f"{lbl}.metrics"),
        monotonic_ok=require_finite_float(metrics, "monotonic_ok", f"{lbl}.metrics"),
        failures=require_finite_float(metrics, "failures", f"{lbl}.metrics"),
        max_3way_err=require_finite_float(parity, "max_3way_err", f"{lbl}.parity"),
        ctrl1_goodhart_rolled_back=require_bool(
            controls, "ctrl1_goodhart_rolled_back", f"{lbl}.controls"
        ),
        ctrl2_nonpos_budget_trapped=require_bool(
            controls, "ctrl2_nonpos_budget_trapped", f"{lbl}.controls"
        ),
        ctrl3_forged_superopt_cert_rejected=require_bool(
            controls, "ctrl3_forged_superopt_cert_rejected", f"{lbl}.controls"
        ),
        controls_caught=require_int(raw, "controls_caught", lbl, minimum=0),
        controls_total=require_int(raw, "controls_total", lbl, minimum=1),
    )


def parse_wasm_pack_manifest(raw: dict[str, Any]) -> WasmPackManifest:
    """Parse a site-dropin-wasm-100pack/1 manifest payload."""
    lbl = "wasm_pack"
    schema = require_str(raw, "schema", lbl)
    if schema != WASM_PACK_SCHEMA:
        raise RsiGateError(
            f"{lbl}: expected schema '{WASM_PACK_SCHEMA}', got '{schema}'"
        )
    modules_raw = require_list(raw, "modules", lbl)
    entries: list[WasmModuleEntry] = []
    for idx, item in enumerate(modules_raw):
        if not isinstance(item, dict):
            raise RsiGateError(f"{lbl}: modules[{idx}] must be an object")
        ml = f"{lbl}.modules[{idx}]"
        wasm_path = require_str(item, "wasm_path", ml)
        validate_relative_wasm_path(wasm_path, ml)
        entries.append(
            WasmModuleEntry(
                pack=require_int(item, "pack", ml, minimum=1),
                idea_id=require_str(item, "idea_id", ml),
                slug=require_str(item, "slug", ml),
                wasm_path=wasm_path,
                wasm_bytes=require_int(item, "wasm_bytes", ml, minimum=1),
                wasm_sha256=require_sha256(item, "wasm_sha256", ml),
                license=require_str(item, "license", ml),
            )
        )
    return WasmPackManifest(
        license=require_str(raw, "license", lbl),
        module_count=require_int(raw, "module_count", lbl, minimum=1),
        zero_import_count=require_int(raw, "zero_import_count", lbl, minimum=0),
        total_bytes=require_int(raw, "total_bytes", lbl, minimum=1),
        under_1_25mb=require_bool(raw, "under_1_25mb", lbl),
        modules=tuple(entries),
    )
