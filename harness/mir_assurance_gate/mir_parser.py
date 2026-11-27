# SPDX-License-Identifier: MIT
"""Typed parsers for all four BuildLang compile-time MIR verifier manifests."""

from __future__ import annotations

from typing import Any

from harness.mir_assurance_gate.mir_guards import (
    MirGateError,
    require_bool,
    require_dict,
    require_hex_40,
    require_hex_prefix,
    require_int,
    require_list,
    require_str,
    require_str_tuple,
)
from harness.mir_assurance_gate.mir_models import (
    CtModuleRecord,
    CtPillarManifest,
    DetModuleRecord,
    DetPillarManifest,
    EffectModuleRecord,
    EffectPillarManifest,
    MirAssuranceBundle,
    WcetModuleRecord,
    WcetPillarManifest,
)

EFFECT_SCHEMA = "buildlang.effect-manifest/v1"
WCET_SCHEMA = "buildlang.wcet-manifest/v1"
CT_SCHEMA = "buildlang.ct-manifest/v1"
DET_SCHEMA = "buildlang.det-manifest/v1"

__all__ = [
    "CT_SCHEMA",
    "DET_SCHEMA",
    "EFFECT_SCHEMA",
    "WCET_SCHEMA",
    "CtModuleRecord",
    "CtPillarManifest",
    "DetModuleRecord",
    "DetPillarManifest",
    "EffectModuleRecord",
    "EffectPillarManifest",
    "MirAssuranceBundle",
    "WcetModuleRecord",
    "WcetPillarManifest",
    "parse_ct_manifest",
    "parse_det_manifest",
    "parse_effect_manifest",
    "parse_wcet_manifest",
]


def _parse_header(
    raw: dict[str, Any],
    expected_schema: str,
    label: str,
) -> tuple[str, int, int, dict[str, Any]]:
    schema = require_str(raw, "schema", label)
    if schema != expected_schema:
        raise MirGateError(
            f"{label}: expected schema '{expected_schema}', got '{schema}'"
        )
    sha = require_hex_40(raw, "commit_sha", label)
    lib_t = require_int(raw, "lib_tests_passed", label, minimum=1)
    int_t = require_int(raw, "integration_tests_passed", label, minimum=0)
    return sha, lib_t, int_t, require_dict(raw, "buildos_core_sweep", label)


def _iter_module_dicts(
    sw: dict[str, Any], label: str
) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for idx, entry in enumerate(require_list(sw, "modules", label)):
        if not isinstance(entry, dict):
            raise MirGateError(f"{label}: module[{idx}] is not an object")
        out.append((f"{label}.modules[{idx}]", entry))
    return out


def parse_effect_manifest(raw: dict[str, Any]) -> EffectPillarManifest:
    """Parse a buildlang.effect-manifest/v1 payload."""
    lbl = "effect"
    sha, lib_t, int_t, sw = _parse_header(raw, EFFECT_SCHEMA, lbl)
    mods = tuple(
        EffectModuleRecord(
            file=require_str(e, "file", ml),
            functions=require_int(e, "functions", ml, minimum=1),
            pure_functions=require_int(e, "pure_functions", ml, minimum=0),
            module_effects=require_str_tuple(e, "module_effects", ml, allow_empty=True),
            zero_egress=require_bool(e, "zero_egress", ml),
            manifest_sha256_prefix=require_hex_prefix(e, "manifest_sha256_prefix", ml),
        )
        for ml, e in _iter_module_dicts(sw, lbl)
    )
    return EffectPillarManifest(
        commit_sha=sha,
        lib_tests_passed=lib_t,
        integration_tests_passed=int_t,
        denied_effects=require_str_tuple(sw, "denied_effects", lbl),
        files_audited=require_int(sw, "files_audited", lbl, minimum=1),
        files_passed=require_int(sw, "files_passed", lbl, minimum=0),
        total_functions=require_int(sw, "total_functions", lbl, minimum=1),
        pure_functions=require_int(sw, "pure_functions", lbl, minimum=0),
        zero_egress_all=require_bool(sw, "zero_egress_all", lbl),
        modules=mods,
    )


def parse_wcet_manifest(raw: dict[str, Any]) -> WcetPillarManifest:
    """Parse a buildlang.wcet-manifest/v1 payload."""
    lbl = "wcet"
    sha, lib_t, int_t, sw = _parse_header(raw, WCET_SCHEMA, lbl)
    mods = tuple(
        WcetModuleRecord(
            file=require_str(e, "file", ml),
            functions=require_int(e, "functions", ml, minimum=1),
            max_frame_bytes=require_int(e, "max_frame_bytes", ml, minimum=0),
            max_stack_bytes=require_int(e, "max_stack_bytes", ml, minimum=0),
            max_wcet_cost=require_int(e, "max_wcet_cost", ml, minimum=0),
            stack_bounded=require_bool(e, "stack_bounded", ml),
            has_recursion=require_bool(e, "has_recursion", ml),
            manifest_sha256_prefix=require_hex_prefix(e, "manifest_sha256_prefix", ml),
        )
        for ml, e in _iter_module_dicts(sw, lbl)
    )
    return WcetPillarManifest(
        commit_sha=sha,
        lib_tests_passed=lib_t,
        integration_tests_passed=int_t,
        single_frame_limit_bytes=require_int(
            sw, "single_frame_limit_bytes", lbl, minimum=1
        ),
        page_budget_bytes=require_int(sw, "page_budget_bytes", lbl, minimum=1),
        files_audited=require_int(sw, "files_audited", lbl, minimum=1),
        files_passed_4096=require_int(sw, "files_passed_4096", lbl, minimum=0),
        total_functions=require_int(sw, "total_functions", lbl, minimum=1),
        functions_under_2048_frame=require_int(
            sw, "functions_under_2048_frame", lbl, minimum=0
        ),
        recursion_free_all=require_bool(sw, "recursion_free_all", lbl),
        max_single_frame_bytes=require_int(
            sw, "max_single_frame_bytes", lbl, minimum=0
        ),
        peak_transitive_stack_bytes=require_int(
            sw, "peak_transitive_stack_bytes", lbl, minimum=0
        ),
        modules=mods,
    )


def parse_ct_manifest(raw: dict[str, Any]) -> CtPillarManifest:
    """Parse a buildlang.ct-manifest/v1 payload."""
    lbl = "ct"
    sha, lib_t, int_t, sw = _parse_header(raw, CT_SCHEMA, lbl)
    controls = require_int(raw, "planted_side_channel_controls_caught", lbl, minimum=0)
    mods = tuple(
        CtModuleRecord(
            file=require_str(e, "file", ml),
            functions=require_int(e, "functions", ml, minimum=1),
            secret_sources=require_int(e, "secret_sources", ml, minimum=0),
            violations=require_int(e, "violations", ml, minimum=0),
            constant_time_verified=require_bool(e, "constant_time_verified", ml),
            manifest_sha256_prefix=require_hex_prefix(e, "manifest_sha256_prefix", ml),
        )
        for ml, e in _iter_module_dicts(sw, lbl)
    )
    return CtPillarManifest(
        commit_sha=sha,
        lib_tests_passed=lib_t,
        integration_tests_passed=int_t,
        planted_side_channel_controls_caught=controls,
        files_audited=require_int(sw, "files_audited", lbl, minimum=1),
        files_passed=require_int(sw, "files_passed", lbl, minimum=0),
        total_functions=require_int(sw, "total_functions", lbl, minimum=1),
        total_violations=require_int(sw, "total_violations", lbl, minimum=0),
        constant_time_verified_all=require_bool(sw, "constant_time_verified_all", lbl),
        modules=mods,
    )


def parse_det_manifest(raw: dict[str, Any]) -> DetPillarManifest:
    """Parse a buildlang.det-manifest/v1 payload."""
    lbl = "det"
    sha, lib_t, int_t, sw = _parse_header(raw, DET_SCHEMA, lbl)
    hazards = require_int(raw, "planted_nondeterminism_hazards_caught", lbl, minimum=0)
    mods = tuple(
        DetModuleRecord(
            file=require_str(e, "file", ml),
            functions=require_int(e, "functions", ml, minimum=1),
            deterministic_functions=require_int(
                e, "deterministic_functions", ml, minimum=0
            ),
            violations=require_int(e, "violations", ml, minimum=0),
            bit_exact_deterministic=require_bool(e, "bit_exact_deterministic", ml),
            manifest_sha256_prefix=require_hex_prefix(e, "manifest_sha256_prefix", ml),
        )
        for ml, e in _iter_module_dicts(sw, lbl)
    )
    return DetPillarManifest(
        commit_sha=sha,
        lib_tests_passed=lib_t,
        integration_tests_passed=int_t,
        planted_nondeterminism_hazards_caught=hazards,
        files_audited=require_int(sw, "files_audited", lbl, minimum=1),
        files_passed=require_int(sw, "files_passed", lbl, minimum=0),
        total_functions=require_int(sw, "total_functions", lbl, minimum=1),
        deterministic_functions=require_int(
            sw, "deterministic_functions", lbl, minimum=0
        ),
        total_violations=require_int(sw, "total_violations", lbl, minimum=0),
        bit_exact_deterministic_all=require_bool(
            sw, "bit_exact_deterministic_all", lbl
        ),
        modules=mods,
    )
