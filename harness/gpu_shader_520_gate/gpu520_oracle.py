# SPDX-License-Identifier: MIT
"""Fail-closed oracle and CLI for GPU 520-pack, RLVR v14, and Paper #8 Octet."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from harness.gpu_shader_520_gate.gpu520_guards import (
    ORCID_RE,
    REQUIRED_GPU_TARGETS,
    REQUIRED_RLVR_ARTIFACTS,
    REQUIRED_VALIDATORS,
    Gpu520GateError,
    load_json_object,
)
from harness.gpu_shader_520_gate.gpu520_models import (
    Gpu520Manifest,
    Gpu520Report,
    Paper8Manifest,
    QuingentennialBundle,
    RlvrV14Manifest,
)
from harness.gpu_shader_520_gate.gpu520_parser import (
    parse_gpu_520_manifest,
    parse_gpu_520_report,
    parse_paper8_manifest,
    parse_rlvr_v14_manifest,
)


@dataclass(frozen=True)
class Gpu520Verdict:
    passed: bool
    certified_shaders: int
    unique_kernels: int
    total_superopt_rewrites: int
    rlvr_v14_tasks: int
    paper8_pages: int
    reasons: tuple[str, ...]


def _check_gpu_520_manifest(man: Gpu520Manifest, reasons: list[str]) -> None:
    if man.license != "MIT":
        reasons.append(f"gpu520: non-MIT license '{man.license}'")
    if (
        man.unique_kernels != 104
        or man.gpu_targets != 5
        or man.total_certified_shaders != 520
    ):
        reasons.append(
            "gpu520: expected 104 kernels x 5 targets = 520 certified shaders"
        )
    if set(man.per_target_counts.keys()) != REQUIRED_GPU_TARGETS:
        reasons.append("gpu520: per_target_counts missing required GPU backends")
    if any(v != man.unique_kernels for v in man.per_target_counts.values()):
        reasons.append("gpu520: imbalanced per_target_counts across backends")
    if len(man.shaders) != man.total_certified_shaders:
        reasons.append("gpu520: shaders array length != total_certified_shaders")
    if sum(s.shader_bytes for s in man.shaders) != man.total_shader_bytes:
        reasons.append("gpu520: shader_bytes sum mismatch")
    if sum(s.rewrites for s in man.shaders) != man.total_superopt_rewrites:
        reasons.append("gpu520: superopt rewrites sum mismatch")
    seen_pairs: set[tuple[str, str]] = set()
    for s in man.shaders:
        if s.verify_cert != "PASS" or s.target not in REQUIRED_GPU_TARGETS:
            reasons.append(
                f"gpu520: shader {s.kernel}:{s.target} failed cert or target check"
            )
            break
        pair = (s.kernel, s.target)
        if pair in seen_pairs:
            reasons.append(f"gpu520: duplicate shader entry {pair}")
            break
        seen_pairs.add(pair)


def _check_gpu_520_report(
    man: Gpu520Manifest, rep: Gpu520Report, reasons: list[str]
) -> None:
    if not rep.ok or rep.verdict != "PASS":
        reasons.append("gpu520_report: ok is false or verdict != PASS")
    if rep.combined_520pack_shaders != man.total_certified_shaders:
        reasons.append(
            "gpu520_report: combined_520pack_shaders disagrees with manifest"
        )
    if rep.combined_520pack_rewrites != man.total_superopt_rewrites:
        reasons.append(
            "gpu520_report: combined_520pack_rewrites disagrees with manifest"
        )
    if rep.combined_520pack_bytes != man.total_shader_bytes:
        reasons.append("gpu520_report: combined_520pack_bytes disagrees with manifest")
    if rep.validation_counts.get("verify_cert", 0) != rep.new_certified_shaders:
        reasons.append("gpu520_report: verify_cert count != new_certified_shaders")
    for val_key in REQUIRED_VALIDATORS:
        if rep.validation_counts.get(val_key, 0) < rep.new_kernels:
            reasons.append(f"gpu520_report: validator '{val_key}' below new_kernels")
    if (
        rep.controls_caught < 3
        or len(rep.controls_rejected) < 3
        or not all(rep.controls_rejected)
    ):
        reasons.append("gpu520_report: planted fail-closed controls incomplete")


def _check_rlvr_v14(rlvr: RlvrV14Manifest, reasons: list[str]) -> None:
    if rlvr.license != "MIT" or rlvr.push_to_hub:
        reasons.append("rlvr_v14: license must be MIT and push_to_hub must be false")
    if (
        rlvr.total_tasks != 1280
        or rlvr.train_tasks + rlvr.eval_tasks != rlvr.total_tasks
    ):
        reasons.append("rlvr_v14: total_tasks must be 1280 and equal train + eval")
    if rlvr.v13_preserved_tasks + rlvr.new_v14_tasks != rlvr.total_tasks:
        reasons.append("rlvr_v14: v13_preserved + new_v14 != total_tasks")
    if len(rlvr.category_counts) != rlvr.categories:
        reasons.append("rlvr_v14: category count mismatch")
    if sum(rlvr.category_counts.values()) != rlvr.total_tasks:
        reasons.append("rlvr_v14: category_counts sum != total_tasks")
    if rlvr.category_counts.get("planted_negative_trap", 0) < 64:
        reasons.append("rlvr_v14: planted_negative_trap below 64")
    by_name = {a.name: a for a in rlvr.artifacts}
    if not set(REQUIRED_RLVR_ARTIFACTS).issubset(by_name.keys()):
        reasons.append("rlvr_v14: missing required JSONL or notebook artifact")
    elif by_name["jfc3p_14b_oracle_v14_mit.jsonl"].rows != rlvr.total_tasks:
        reasons.append("rlvr_v14: full jsonl rows != total_tasks")
    if len(rlvr.immutable_pins) < 5:
        reasons.append("rlvr_v14: missing immutable upstream pins")


def _check_paper8(p8: Paper8Manifest, reasons: list[str]) -> None:
    if p8.paper_license != "CC-BY-4.0" or "MIT" not in p8.code_licenses:
        reasons.append("paper8: unexpected paper or code license")
    if not ORCID_RE.match(p8.orcid):
        reasons.append("paper8: invalid ORCID identifier")
    if (
        p8.send_policy != "STAGED_ON_DISK_ONLY_ZERO_EXTERNAL_UPLOADS"
        or not p8.prior_untouched
    ):
        reasons.append("paper8: external upload policy or prior immutability violated")
    if len(p8.arxiv_categories) < 3 or len(p8.verified_catalogue_ids) < 8:
        reasons.append(
            "paper8: insufficient arXiv categories or verified catalogue IDs"
        )
    if (
        p8.paper_pages != 6
        or len(p8.page_pngs) != p8.paper_pages
        or p8.paper_words < 1000
    ):
        reasons.append("paper8: page count, PNG count, or word count below threshold")


def verify_gpu_520_bundle(bundle: QuingentennialBundle) -> Gpu520Verdict:
    """Verify Quingentennial GPU 520-pack, RLVR v14, and Paper #8 Octet together."""
    reasons: list[str] = []
    _check_gpu_520_manifest(bundle.gpu_manifest, reasons)
    _check_gpu_520_report(bundle.gpu_manifest, bundle.gpu_report, reasons)
    _check_rlvr_v14(bundle.rlvr_v14, reasons)
    _check_paper8(bundle.paper8, reasons)
    return Gpu520Verdict(
        passed=not reasons,
        certified_shaders=bundle.gpu_manifest.total_certified_shaders,
        unique_kernels=bundle.gpu_manifest.unique_kernels,
        total_superopt_rewrites=bundle.gpu_manifest.total_superopt_rewrites,
        rlvr_v14_tasks=bundle.rlvr_v14.total_tasks,
        paper8_pages=bundle.paper8.paper_pages,
        reasons=tuple(reasons),
    )


def verify_gpu_520_files(
    gpu_manifest_path: Path,
    gpu_report_path: Path,
    rlvr_manifest_path: Path,
    paper8_manifest_path: Path,
) -> Gpu520Verdict:
    """Load, parse, and verify all four Quingentennial JSON manifests from disk."""
    try:
        bundle = QuingentennialBundle(
            gpu_manifest=parse_gpu_520_manifest(
                load_json_object(gpu_manifest_path, "gpu520")
            ),
            gpu_report=parse_gpu_520_report(
                load_json_object(gpu_report_path, "gpu520_report")
            ),
            rlvr_v14=parse_rlvr_v14_manifest(
                load_json_object(rlvr_manifest_path, "rlvr_v14")
            ),
            paper8=parse_paper8_manifest(
                load_json_object(paper8_manifest_path, "paper8")
            ),
        )
    except Gpu520GateError as exc:
        return Gpu520Verdict(
            passed=False,
            certified_shaders=0,
            unique_kernels=0,
            total_superopt_rewrites=0,
            rlvr_v14_tasks=0,
            paper8_pages=0,
            reasons=(str(exc),),
        )
    return verify_gpu_520_bundle(bundle)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point returning 0 on PASS and 2 on fail-closed rejection."""
    parser = argparse.ArgumentParser(
        description="Verify Quingentennial GPU 520-pack, RLVR v14, and Paper #8 manifests."
    )
    parser.add_argument("--gpu-manifest", type=Path, required=True)
    parser.add_argument("--gpu-report", type=Path, required=True)
    parser.add_argument("--rlvr-manifest", type=Path, required=True)
    parser.add_argument("--paper8-manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    verdict = verify_gpu_520_files(
        args.gpu_manifest,
        args.gpu_report,
        args.rlvr_manifest,
        args.paper8_manifest,
    )
    print(json.dumps(asdict(verdict), indent=2))
    return 0 if verdict.passed else 2


if __name__ == "__main__":
    sys.exit(main())
