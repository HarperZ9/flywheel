# SPDX-License-Identifier: MIT
"""Fail-closed attestation oracle for the 240-shader 5-backend GPU compute suite."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Sequence

from harness.gpu_240pack_gate.pack240_guards import (
    EXPECTED_KERNELS,
    EXPECTED_SHADERS,
    MIN_SUPEROPT_REWRITES,
    REQUIRED_TARGETS,
    check_planted_shader_controls,
    check_shader_entry,
    check_validation_counts,
    is_strict_int,
)
from harness.gpu_240pack_gate.pack240_parser import (
    Gpu240Bundle,
    parse_gpu_240pack_manifest,
)


@dataclass(frozen=True)
class Gpu240Policy:
    """Configurable thresholds for the 240-shader 5-backend gate."""

    expected_kernels: int = EXPECTED_KERNELS
    expected_shaders: int = EXPECTED_SHADERS
    min_superopt_rewrites: int = MIN_SUPEROPT_REWRITES
    require_mit_license: bool = True
    require_report_validators: bool = False
    min_new_kernels: int = 8


@dataclass(frozen=True)
class Gpu240Report:
    """Deterministic fail-closed verdict emitted by gpu_240pack_gate."""

    ok: bool
    verdict: str
    unique_kernels: int
    shaders_verified: int
    total_rewrites: int
    total_shader_bytes: int
    per_target_counts: dict[str, int]
    controls_verified: int
    errors: tuple[str, ...]
    report_sha256: str


def _seal(
    ok: bool,
    kernels: int,
    shaders: int,
    rewrites: int,
    total_bytes: int,
    per_target: dict[str, int],
    controls: int,
    errs: list[str],
) -> Gpu240Report:
    verdict = "PASS" if ok else "REJECT"
    body = {
        "ok": ok,
        "verdict": verdict,
        "unique_kernels": kernels,
        "shaders_verified": shaders,
        "total_rewrites": rewrites,
        "total_shader_bytes": total_bytes,
        "per_target_counts": per_target,
        "controls_verified": controls,
        "errors": list(errs),
    }
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return Gpu240Report(
        ok=ok,
        verdict=verdict,
        unique_kernels=kernels,
        shaders_verified=shaders,
        total_rewrites=rewrites,
        total_shader_bytes=total_bytes,
        per_target_counts=per_target,
        controls_verified=controls,
        errors=tuple(errs),
        report_sha256=digest,
    )


def _scan_shaders(
    bundle: Gpu240Bundle,
    errs: list[str],
) -> tuple[dict[str, set[str]], dict[str, int], int, int, int]:
    kernel_targets: dict[str, set[str]] = {}
    per_target = {t: 0 for t in REQUIRED_TARGETS}
    verified = 0
    total_bytes = 0
    total_rewrites = 0
    for rec in bundle.shaders:
        s_errs = check_shader_entry(rec)
        if s_errs:
            errs.extend(s_errs)
            continue
        targets = kernel_targets.setdefault(rec.kernel, set())
        if rec.target in targets:
            errs.append(f"duplicate_shader:{rec.kernel}:{rec.target}")
            continue
        targets.add(rec.target)
        per_target[rec.target] += 1
        verified += 1
        total_bytes += rec.shader_bytes
        total_rewrites += rec.rewrites
    for kernel, targets in sorted(kernel_targets.items()):
        missing = [t for t in REQUIRED_TARGETS if t not in targets]
        if missing:
            errs.append(f"kernel_missing_targets:{kernel}:{','.join(missing)}")
    return kernel_targets, per_target, verified, total_bytes, total_rewrites


def _check_header_and_aux(
    bundle: Gpu240Bundle,
    pol: Gpu240Policy,
    unique_kernels: int,
    verified: int,
    total_bytes: int,
    total_rewrites: int,
    errs: list[str],
) -> int:
    if bundle.schema != "buildlang-workstation-gpu-240pack/1":
        errs.append(f"invalid_schema:{bundle.schema}")
    if pol.require_mit_license and bundle.license_id != "MIT":
        errs.append(f"non_mit_license:{bundle.license_id}")
    if unique_kernels != pol.expected_kernels:
        errs.append(f"kernel_count_mismatch:{unique_kernels}!={pol.expected_kernels}")
    if verified != pol.expected_shaders:
        errs.append(f"shader_count_mismatch:{verified}!={pol.expected_shaders}")
    if total_rewrites < pol.min_superopt_rewrites:
        errs.append(f"rewrites_below_min:{total_rewrites}<{pol.min_superopt_rewrites}")
    if is_strict_int(bundle.declared_total_bytes) and bundle.declared_total_bytes != total_bytes:
        errs.append(f"declared_bytes_mismatch:{bundle.declared_total_bytes}!={total_bytes}")
    if is_strict_int(bundle.declared_total_rewrites) and bundle.declared_total_rewrites != total_rewrites:
        errs.append(f"declared_rewrites_mismatch:{bundle.declared_total_rewrites}!={total_rewrites}")
    if bundle.receipt_verdict is not None and bundle.receipt_verdict != "MATCH":
        errs.append(f"receipt_verdict_not_match:{bundle.receipt_verdict}")
    if bundle.receipt_exit_code is not None and bundle.receipt_exit_code != 0:
        errs.append(f"receipt_nonzero_exit:{bundle.receipt_exit_code}")
    controls_ok = 0
    if bundle.report_ok is not None or pol.require_report_validators:
        if bundle.report_ok is not True or bundle.report_verdict != "PASS":
            errs.append(f"report_not_pass:{bundle.report_ok!r}:{bundle.report_verdict}")
        errs.extend(check_validation_counts(bundle.validation_counts, pol.min_new_kernels))
        controls_ok, c_errs = check_planted_shader_controls(bundle.planted_controls)
        errs.extend(c_errs)
    return controls_ok


def verify_gpu_240pack_bundle(
    bundle: Gpu240Bundle,
    policy: Gpu240Policy | None = None,
) -> Gpu240Report:
    """Verify the 240-shader 5-backend GPU suite fail-closed."""
    pol = policy or Gpu240Policy()
    errs: list[str] = list(bundle.parse_errors)
    kmap, per_target, verified, total_bytes, total_rewrites = _scan_shaders(bundle, errs)
    controls_ok = _check_header_and_aux(
        bundle, pol, len(kmap), verified, total_bytes, total_rewrites, errs
    )
    return _seal(
        not errs, len(kmap), verified, total_rewrites, total_bytes, per_target, controls_ok, errs
    )


def verify_gpu_240pack_file(
    manifest_path: Path,
    report_path: Path | None = None,
    receipt_path: Path | None = None,
    policy: Gpu240Policy | None = None,
) -> Gpu240Report:
    """Load and verify a GPU 240-pack manifest plus optional report and receipt."""
    man = json.loads(manifest_path.read_text(encoding="utf-8"))
    rep = json.loads(report_path.read_text(encoding="utf-8")) if report_path else None
    rec = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path else None
    return verify_gpu_240pack_bundle(parse_gpu_240pack_manifest(man, rep, rec), policy=policy)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point returning 0 on PASS and 2 on REJECT."""
    parser = argparse.ArgumentParser(description="Verify 240-shader 5-backend GPU manifests.")
    parser.add_argument("manifest_json", type=Path)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--receipt", type=Path, default=None)
    args = parser.parse_args(argv)
    pol = Gpu240Policy(require_report_validators=args.report is not None)
    rep = verify_gpu_240pack_file(args.manifest_json, args.report, args.receipt, policy=pol)
    print(json.dumps(asdict(rep), indent=2, sort_keys=True))
    return 0 if rep.ok else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
