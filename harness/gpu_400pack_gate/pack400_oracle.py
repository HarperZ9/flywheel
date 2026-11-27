# SPDX-License-Identifier: MIT
"""Fail-closed oracle for the Quadricentennial GPU 400-pack and RLVR v12."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Sequence

from harness.gpu_400pack_gate.pack400_guards import (
    EXPECTED_KERNELS,
    EXPECTED_RLVR_CATEGORIES,
    EXPECTED_RLVR_TASKS,
    EXPECTED_SHADERS,
    MIN_SUPEROPT_REWRITES,
    REQUIRED_TARGETS,
    check_rlvr_v12_manifest,
    check_shader_entry,
    is_strict_int,
)
from harness.gpu_400pack_gate.pack400_parser import (
    Gpu400RlvrBundle,
    parse_gpu_400pack_bundle,
)


@dataclass(frozen=True)
class Gpu400Policy:
    """Configurable thresholds for the GPU 400-pack and RLVR v12 verifier."""

    expected_kernels: int = EXPECTED_KERNELS
    expected_shaders: int = EXPECTED_SHADERS
    min_superopt_rewrites: int = MIN_SUPEROPT_REWRITES
    require_mit_license: bool = True
    require_rlvr_v12: bool = False
    expected_rlvr_tasks: int = EXPECTED_RLVR_TASKS
    expected_rlvr_categories: int = EXPECTED_RLVR_CATEGORIES
    check_rlvr_on_disk: bool = False


@dataclass(frozen=True)
class Gpu400Report:
    """Deterministic fail-closed verdict emitted by gpu_400pack_gate."""

    ok: bool
    verdict: str
    unique_kernels: int
    shaders_verified: int
    total_rewrites: int
    total_shader_bytes: int
    rlvr_tasks_verified: int
    rlvr_categories_verified: int
    errors: tuple[str, ...]
    report_sha256: str


def _seal(
    ok: bool, kernels: int, shaders: int, rewrites: int,
    total_bytes: int, rlvr_tasks: int, rlvr_cats: int, errs: list[str],
) -> Gpu400Report:
    verdict = "PASS" if ok else "REJECT"
    body = {
        "ok": ok, "verdict": verdict, "unique_kernels": kernels,
        "shaders_verified": shaders, "total_rewrites": rewrites,
        "total_shader_bytes": total_bytes, "rlvr_tasks_verified": rlvr_tasks,
        "rlvr_categories_verified": rlvr_cats, "errors": list(errs),
    }
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return Gpu400Report(ok, verdict, kernels, shaders, rewrites, total_bytes, rlvr_tasks, rlvr_cats, tuple(errs), digest)


def _scan_shaders(
    bundle: Gpu400RlvrBundle, errs: list[str]
) -> tuple[int, int, int, int]:
    kernel_targets: dict[str, set[str]] = {}
    verified, total_bytes, total_rewrites = 0, 0, 0
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
        verified += 1
        total_bytes += rec.shader_bytes
        total_rewrites += rec.rewrites
    for kernel, targets in sorted(kernel_targets.items()):
        missing = [t for t in REQUIRED_TARGETS if t not in targets]
        if missing:
            errs.append(f"kernel_missing_targets:{kernel}:{','.join(missing)}")
    return len(kernel_targets), verified, total_bytes, total_rewrites


def verify_gpu_400pack_bundle(
    bundle: Gpu400RlvrBundle,
    policy: Gpu400Policy | None = None,
    rlvr_root: Path | None = None,
) -> Gpu400Report:
    """Verify the Quadricentennial GPU 400-pack and optional RLVR v12 manifest."""
    pol = policy or Gpu400Policy()
    errs: list[str] = list(bundle.parse_errors)
    if bundle.schema != "buildlang-workstation-gpu-400pack/1":
        errs.append(f"invalid_schema:{bundle.schema}")
    if pol.require_mit_license and bundle.license_id != "MIT":
        errs.append(f"non_mit_license:{bundle.license_id}")
    kernels, verified, total_bytes, total_rewrites = _scan_shaders(bundle, errs)
    if kernels != pol.expected_kernels:
        errs.append(f"kernel_count_mismatch:{kernels}!={pol.expected_kernels}")
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
    rlvr_tasks, rlvr_cats = 0, 0
    if bundle.rlvr_manifest is not None or pol.require_rlvr_v12:
        rlvr_tasks, rlvr_cats, r_errs = check_rlvr_v12_manifest(
            bundle.rlvr_manifest, pol.expected_rlvr_tasks, pol.expected_rlvr_categories, rlvr_root, pol.check_rlvr_on_disk
        )
        errs.extend(r_errs)
    return _seal(not errs, kernels, verified, total_rewrites, total_bytes, rlvr_tasks, rlvr_cats, errs)


def verify_gpu_400pack_file(
    manifest_path: Path,
    rlvr_manifest_path: Path | None = None,
    receipt_path: Path | None = None,
    policy: Gpu400Policy | None = None,
) -> Gpu400Report:
    """Load and verify gpu_400pack_manifest.json with optional RLVR v12 and receipt."""
    man = json.loads(manifest_path.read_text(encoding="utf-8"))
    rlvr = json.loads(rlvr_manifest_path.read_text(encoding="utf-8")) if rlvr_manifest_path else None
    rec = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path else None
    rlvr_root = rlvr_manifest_path.parent if rlvr_manifest_path else None
    return verify_gpu_400pack_bundle(parse_gpu_400pack_bundle(man, rlvr, rec), policy=policy, rlvr_root=rlvr_root)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point returning 0 on PASS and 2 on REJECT."""
    parser = argparse.ArgumentParser(description="Verify Quadricentennial GPU 400-pack and RLVR v12.")
    parser.add_argument("manifest_json", type=Path)
    parser.add_argument("--rlvr", type=Path, default=None)
    parser.add_argument("--receipt", type=Path, default=None)
    parser.add_argument("--check-rlvr-on-disk", action="store_true")
    args = parser.parse_args(argv)
    pol = Gpu400Policy(require_rlvr_v12=args.rlvr is not None, check_rlvr_on_disk=args.check_rlvr_on_disk)
    rep = verify_gpu_400pack_file(args.manifest_json, args.rlvr, args.receipt, policy=pol)
    print(json.dumps(asdict(rep), indent=2, sort_keys=True))
    return 0 if rep.ok else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
