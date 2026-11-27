# SPDX-License-Identifier: MIT
"""Per-pillar and cross-pillar invariant checks for BuildLang MIR assurance."""

from __future__ import annotations

from harness.mir_assurance_gate.mir_guards import (
    DEFAULT_MIN_INTEGRATION_TESTS,
    DEFAULT_MIN_PLANTED_CONTROLS,
    REQUIRED_DENIED_EFFECTS,
)
from harness.mir_assurance_gate.mir_models import (
    CtPillarManifest,
    DetPillarManifest,
    EffectPillarManifest,
    MirAssuranceBundle,
    WcetPillarManifest,
)


def check_effect_pillar(
    eff: EffectPillarManifest, min_files: int, reasons: list[str]
) -> None:
    """Validate capability effect denial and zero-egress confinement."""
    if eff.integration_tests_passed < DEFAULT_MIN_INTEGRATION_TESTS:
        reasons.append("effect: insufficient integration tests")
    if eff.files_audited < min_files or eff.files_passed != eff.files_audited:
        reasons.append("effect: files_passed mismatch or below minimum")
    if len(eff.modules) != eff.files_audited:
        reasons.append("effect: module count disagrees with files_audited")
    if not REQUIRED_DENIED_EFFECTS.issubset(set(eff.denied_effects)):
        reasons.append("effect: missing required denied effects")
    if not eff.zero_egress_all:
        reasons.append("effect: zero_egress_all is false")
    denied = set(eff.denied_effects) | REQUIRED_DENIED_EFFECTS
    if sum(m.functions for m in eff.modules) != eff.total_functions:
        reasons.append("effect: function count sum mismatch")
    if sum(m.pure_functions for m in eff.modules) != eff.pure_functions:
        reasons.append("effect: pure_functions sum mismatch")
    for mod in eff.modules:
        if not mod.zero_egress or mod.pure_functions > mod.functions:
            reasons.append(f"effect: module {mod.file} failed confinement invariants")
        leaked = sorted(denied.intersection(mod.module_effects))
        if leaked:
            reasons.append(f"effect: module {mod.file} leaked denied effects {leaked}")


def check_wcet_pillar(
    wcet: WcetPillarManifest,
    min_files: int,
    frame_ceiling: int,
    page_budget: int,
    reasons: list[str],
) -> None:
    """Validate recursion freedom and RV64 single-frame + transitive stack budgets."""
    if wcet.integration_tests_passed < DEFAULT_MIN_INTEGRATION_TESTS:
        reasons.append("wcet: insufficient integration tests")
    if wcet.files_audited < min_files or wcet.files_passed_4096 != wcet.files_audited:
        reasons.append("wcet: files_passed_4096 mismatch or below minimum")
    if len(wcet.modules) != wcet.files_audited:
        reasons.append("wcet: module count disagrees with files_audited")
    if (
        wcet.single_frame_limit_bytes > frame_ceiling
        or wcet.page_budget_bytes > page_budget
    ):
        reasons.append("wcet: declared stack limits exceed RV64 ceiling")
    if (
        not wcet.recursion_free_all
        or wcet.functions_under_2048_frame != wcet.total_functions
    ):
        reasons.append("wcet: recursion detected or frame ceiling exceeded")
    if (
        wcet.max_single_frame_bytes > frame_ceiling
        or wcet.peak_transitive_stack_bytes > page_budget
    ):
        reasons.append("wcet: peak stack exceeds RV64 budget")
    if sum(m.functions for m in wcet.modules) != wcet.total_functions:
        reasons.append("wcet: function count sum mismatch")
    if max(m.max_frame_bytes for m in wcet.modules) != wcet.max_single_frame_bytes:
        reasons.append("wcet: max_single_frame_bytes inconsistent with modules")
    if max(m.max_stack_bytes for m in wcet.modules) != wcet.peak_transitive_stack_bytes:
        reasons.append("wcet: peak_transitive_stack_bytes inconsistent with modules")
    for mod in wcet.modules:
        if mod.has_recursion or not mod.stack_bounded:
            reasons.append(f"wcet: module {mod.file} unbounded or recursive")
        if mod.max_frame_bytes > frame_ceiling or mod.max_stack_bytes > page_budget:
            reasons.append(f"wcet: module {mod.file} exceeds RV64 stack limits")
        if mod.max_stack_bytes < mod.max_frame_bytes:
            reasons.append(f"wcet: module {mod.file} max_stack_bytes < max_frame_bytes")


def check_ct_pillar(ct: CtPillarManifest, min_files: int, reasons: list[str]) -> None:
    """Validate constant-time secret taint freedom and planted controls."""
    if ct.integration_tests_passed < DEFAULT_MIN_INTEGRATION_TESTS:
        reasons.append("ct: insufficient integration tests")
    if ct.planted_side_channel_controls_caught < DEFAULT_MIN_PLANTED_CONTROLS:
        reasons.append("ct: planted side-channel controls below threshold")
    if ct.files_audited < min_files or ct.files_passed != ct.files_audited:
        reasons.append("ct: files_passed mismatch or below minimum")
    if len(ct.modules) != ct.files_audited:
        reasons.append("ct: module count disagrees with files_audited")
    if ct.total_violations != 0 or not ct.constant_time_verified_all:
        reasons.append("ct: side-channel violations or unverified sweep")
    if sum(m.functions for m in ct.modules) != ct.total_functions:
        reasons.append("ct: function count sum mismatch")
    if sum(m.violations for m in ct.modules) != ct.total_violations:
        reasons.append("ct: module violations sum mismatch")
    for mod in ct.modules:
        if mod.violations != 0 or not mod.constant_time_verified:
            reasons.append(f"ct: module {mod.file} failed constant-time verification")


def check_det_pillar(
    det: DetPillarManifest, min_files: int, reasons: list[str]
) -> None:
    """Validate bit-exact floating-point determinism and hazard controls."""
    if det.integration_tests_passed < DEFAULT_MIN_INTEGRATION_TESTS:
        reasons.append("det: insufficient integration tests")
    if det.planted_nondeterminism_hazards_caught < DEFAULT_MIN_PLANTED_CONTROLS:
        reasons.append("det: planted nondeterminism hazards below threshold")
    if det.files_audited < min_files or det.files_passed != det.files_audited:
        reasons.append("det: files_passed mismatch or below minimum")
    if len(det.modules) != det.files_audited:
        reasons.append("det: module count disagrees with files_audited")
    if det.total_violations != 0 or not det.bit_exact_deterministic_all:
        reasons.append("det: nondeterminism violations or unverified sweep")
    if det.deterministic_functions != det.total_functions:
        reasons.append("det: deterministic_functions != total_functions")
    if sum(m.functions for m in det.modules) != det.total_functions:
        reasons.append("det: function count sum mismatch")
    if (
        sum(m.deterministic_functions for m in det.modules)
        != det.deterministic_functions
    ):
        reasons.append("det: deterministic_functions sum mismatch")
    if sum(m.violations for m in det.modules) != det.total_violations:
        reasons.append("det: module violations sum mismatch")
    for mod in det.modules:
        if mod.violations != 0 or not mod.bit_exact_deterministic:
            reasons.append(f"det: module {mod.file} failed bit-exact determinism")
        if mod.deterministic_functions != mod.functions:
            reasons.append(f"det: module {mod.file} partial deterministic coverage")


def check_cross_pillar_consistency(
    bundle: MirAssuranceBundle, reasons: list[str]
) -> None:
    """Ensure all four MIR pillars audited the exact same deduplicated file set."""
    eff_files = tuple(sorted(m.file for m in bundle.effect.modules))
    if len(set(eff_files)) != len(eff_files):
        reasons.append("effect: duplicate module file entries")
    for name, mods in (
        ("wcet", bundle.wcet.modules),
        ("ct", bundle.ct.modules),
        ("det", bundle.det.modules),
    ):
        other_files = tuple(sorted(m.file for m in mods))
        if len(set(other_files)) != len(other_files):
            reasons.append(f"{name}: duplicate module file entries")
        if other_files != eff_files:
            reasons.append(f"{name}: audited file set diverges from effect pillar")
    fn_counts = {
        bundle.effect.total_functions,
        bundle.wcet.total_functions,
        bundle.ct.total_functions,
        bundle.det.total_functions,
    }
    if len(fn_counts) != 1:
        reasons.append("cross-pillar: total_functions mismatch across MIR pillars")
