# SPDX-License-Identifier: MIT
"""Fail-closed oracle and CLI for the 4-pillar BuildLang MIR assurance gate."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from harness.mir_assurance_gate.mir_checks import (
    check_cross_pillar_consistency,
    check_ct_pillar,
    check_det_pillar,
    check_effect_pillar,
    check_wcet_pillar,
)
from harness.mir_assurance_gate.mir_guards import (
    DEFAULT_MIN_FILES,
    DEFAULT_RV64_FRAME_CEILING,
    DEFAULT_RV64_PAGE_BUDGET,
    MirGateError,
    load_json_object,
)
from harness.mir_assurance_gate.mir_models import MirAssuranceBundle
from harness.mir_assurance_gate.mir_parser import (
    parse_ct_manifest,
    parse_det_manifest,
    parse_effect_manifest,
    parse_wcet_manifest,
)


@dataclass(frozen=True)
class MirAssuranceVerdict:
    passed: bool
    pillars_verified: int
    files_audited: int
    total_functions: int
    peak_single_frame_bytes: int
    peak_transitive_stack_bytes: int
    total_violations: int
    reasons: tuple[str, ...]


def verify_mir_assurance_bundle(
    bundle: MirAssuranceBundle,
    *,
    min_files: int = DEFAULT_MIN_FILES,
    frame_ceiling: int = DEFAULT_RV64_FRAME_CEILING,
    page_budget: int = DEFAULT_RV64_PAGE_BUDGET,
) -> MirAssuranceVerdict:
    """Verify all four BuildLang compile-time MIR assurance pillars."""
    reasons: list[str] = []
    check_effect_pillar(bundle.effect, min_files, reasons)
    check_wcet_pillar(bundle.wcet, min_files, frame_ceiling, page_budget, reasons)
    check_ct_pillar(bundle.ct, min_files, reasons)
    check_det_pillar(bundle.det, min_files, reasons)
    check_cross_pillar_consistency(bundle, reasons)
    total_v = bundle.ct.total_violations + bundle.det.total_violations
    return MirAssuranceVerdict(
        passed=not reasons,
        pillars_verified=4 if not reasons else 0,
        files_audited=bundle.effect.files_audited,
        total_functions=bundle.effect.total_functions,
        peak_single_frame_bytes=bundle.wcet.max_single_frame_bytes,
        peak_transitive_stack_bytes=bundle.wcet.peak_transitive_stack_bytes,
        total_violations=total_v,
        reasons=tuple(reasons),
    )


def verify_mir_assurance_files(
    effect_path: Path,
    wcet_path: Path,
    ct_path: Path,
    det_path: Path,
    *,
    min_files: int = DEFAULT_MIN_FILES,
    frame_ceiling: int = DEFAULT_RV64_FRAME_CEILING,
    page_budget: int = DEFAULT_RV64_PAGE_BUDGET,
) -> MirAssuranceVerdict:
    """Load, parse, and verify four MIR pillar JSON manifests from disk."""
    try:
        bundle = MirAssuranceBundle(
            effect=parse_effect_manifest(load_json_object(effect_path, "effect")),
            wcet=parse_wcet_manifest(load_json_object(wcet_path, "wcet")),
            ct=parse_ct_manifest(load_json_object(ct_path, "ct")),
            det=parse_det_manifest(load_json_object(det_path, "det")),
        )
    except MirGateError as exc:
        return MirAssuranceVerdict(
            passed=False,
            pillars_verified=0,
            files_audited=0,
            total_functions=0,
            peak_single_frame_bytes=0,
            peak_transitive_stack_bytes=0,
            total_violations=0,
            reasons=(str(exc),),
        )
    return verify_mir_assurance_bundle(
        bundle,
        min_files=min_files,
        frame_ceiling=frame_ceiling,
        page_budget=page_budget,
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point returning 0 on PASS and 2 on fail-closed rejection."""
    parser = argparse.ArgumentParser(
        description="Verify BuildLang 4-pillar MIR assurance sweeps."
    )
    parser.add_argument("--effect", type=Path, required=True)
    parser.add_argument("--wcet", type=Path, required=True)
    parser.add_argument("--ct", type=Path, required=True)
    parser.add_argument("--det", type=Path, required=True)
    parser.add_argument("--frame-ceiling", type=int, default=DEFAULT_RV64_FRAME_CEILING)
    parser.add_argument("--page-budget", type=int, default=DEFAULT_RV64_PAGE_BUDGET)
    args = parser.parse_args(argv)
    verdict = verify_mir_assurance_files(
        args.effect,
        args.wcet,
        args.ct,
        args.det,
        frame_ceiling=args.frame_ceiling,
        page_budget=args.page_budget,
    )
    print(json.dumps(asdict(verdict), indent=2))
    return 0 if verdict.passed else 2


if __name__ == "__main__":
    sys.exit(main())
