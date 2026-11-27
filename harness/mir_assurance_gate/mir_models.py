# SPDX-License-Identifier: MIT
"""Typed data models for the 4-pillar BuildLang MIR assurance verifier."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EffectModuleRecord:
    file: str
    functions: int
    pure_functions: int
    module_effects: tuple[str, ...]
    zero_egress: bool
    manifest_sha256_prefix: str


@dataclass(frozen=True)
class EffectPillarManifest:
    commit_sha: str
    lib_tests_passed: int
    integration_tests_passed: int
    denied_effects: tuple[str, ...]
    files_audited: int
    files_passed: int
    total_functions: int
    pure_functions: int
    zero_egress_all: bool
    modules: tuple[EffectModuleRecord, ...]


@dataclass(frozen=True)
class WcetModuleRecord:
    file: str
    functions: int
    max_frame_bytes: int
    max_stack_bytes: int
    max_wcet_cost: int
    stack_bounded: bool
    has_recursion: bool
    manifest_sha256_prefix: str


@dataclass(frozen=True)
class WcetPillarManifest:
    commit_sha: str
    lib_tests_passed: int
    integration_tests_passed: int
    single_frame_limit_bytes: int
    page_budget_bytes: int
    files_audited: int
    files_passed_4096: int
    total_functions: int
    functions_under_2048_frame: int
    recursion_free_all: bool
    max_single_frame_bytes: int
    peak_transitive_stack_bytes: int
    modules: tuple[WcetModuleRecord, ...]


@dataclass(frozen=True)
class CtModuleRecord:
    file: str
    functions: int
    secret_sources: int
    violations: int
    constant_time_verified: bool
    manifest_sha256_prefix: str


@dataclass(frozen=True)
class CtPillarManifest:
    commit_sha: str
    lib_tests_passed: int
    integration_tests_passed: int
    planted_side_channel_controls_caught: int
    files_audited: int
    files_passed: int
    total_functions: int
    total_violations: int
    constant_time_verified_all: bool
    modules: tuple[CtModuleRecord, ...]


@dataclass(frozen=True)
class DetModuleRecord:
    file: str
    functions: int
    deterministic_functions: int
    violations: int
    bit_exact_deterministic: bool
    manifest_sha256_prefix: str


@dataclass(frozen=True)
class DetPillarManifest:
    commit_sha: str
    lib_tests_passed: int
    integration_tests_passed: int
    planted_nondeterminism_hazards_caught: int
    files_audited: int
    files_passed: int
    total_functions: int
    deterministic_functions: int
    total_violations: int
    bit_exact_deterministic_all: bool
    modules: tuple[DetModuleRecord, ...]


@dataclass(frozen=True)
class MirAssuranceBundle:
    effect: EffectPillarManifest
    wcet: WcetPillarManifest
    ct: CtPillarManifest
    det: DetPillarManifest
