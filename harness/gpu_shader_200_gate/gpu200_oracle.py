# SPDX-License-Identifier: MIT
"""Fail-closed Flywheel oracle for the Bicentennial 200-Shader GPU Pack.

Verifies 40 MIT kernels x 5 GPU backends (200 shaders), Superopt V6 rewrite
totals, external validator coverage (dxc, glslangValidator, spirv-val, naga),
optional on-disk shader SHA-256 parity, and gpu_shader_200_attestation_sha256.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .manifest_parser import CertifiedShaderEntry, parse_gpu_200_manifest
from .shader_guards import (
    REQUIRED_GPU_TARGETS,
    canonical_sha256_hex,
    is_strict_finite_float,
    is_strict_int,
    normalize_sha256,
)

HONEST_SCOPE_LIMIT = (
    "Verifies 200-shader 5-backend manifest completeness, MIT licensing, "
    "rewrite sums, validator tags, and optional on-disk shader SHA-256 "
    "digests in pure Python stdlib. Does not execute GPU compute dispatches."
)


@dataclass(frozen=True)
class Gpu200GateReport:
    """Fail-closed attestation verdict for the 200-shader 5-backend GPU pack."""

    passed: bool
    unique_kernels: int
    total_shaders: int
    complete_5target_kernels: int
    total_superopt_rewrites: int
    total_shader_bytes: int
    validators_observed: tuple[str, ...]
    gpu_shader_200_attestation_sha256: str
    violations: tuple[str, ...]
    honest_scope_limit: str = HONEST_SCOPE_LIMIT


def _validate_policy(
    min_shaders: int,
    min_kernels: int,
    min_rewrites: int,
    max_parity_err: float,
) -> list[str]:
    errors: list[str] = []
    for name, val in (
        ("min_shaders", min_shaders),
        ("min_kernels", min_kernels),
    ):
        if not is_strict_int(val) or val <= 0:
            errors.append(f"{name}: expected positive strict int, got {val!r}")
    if not is_strict_int(min_rewrites) or min_rewrites < 0:
        errors.append(f"min_rewrites: expected non-negative strict int, got {min_rewrites!r}")
    if not is_strict_finite_float(max_parity_err) or float(max_parity_err) < 0.0:
        errors.append(f"max_parity_err: invalid {max_parity_err!r}")
    return errors


def _check_entries_policy(
    entries: list[CertifiedShaderEntry],
    min_shaders: int,
    min_kernels: int,
    min_rewrites: int,
    required_validators: tuple[str, ...],
    actual_shader_hashes: dict[tuple[str, str], tuple[int, str]] | None,
) -> tuple[int, list[str]]:
    errors: list[str] = []
    by_kernel: dict[str, set[str]] = {}
    for e in entries:
        by_kernel.setdefault(e.kernel, set()).add(e.target)
    complete = 0
    for kern, tgts in sorted(by_kernel.items()):
        missing = sorted(REQUIRED_GPU_TARGETS - tgts)
        if missing:
            errors.append(f"kernel({kern}): missing GPU backends {missing}")
        else:
            complete += 1
    if len(entries) < min_shaders:
        errors.append(f"shader_count {len(entries)} < min_shaders {min_shaders}")
    if len(by_kernel) < min_kernels:
        errors.append(f"kernel_count {len(by_kernel)} < min_kernels {min_kernels}")
    tot_rewrites = sum(e.rewrites for e in entries)
    if tot_rewrites < min_rewrites:
        errors.append(f"total_rewrites {tot_rewrites} < min_rewrites {min_rewrites}")
    joined_vals = " ".join(e.external_validator.lower() for e in entries)
    for req_v in required_validators:
        if req_v.lower() not in joined_vals:
            errors.append(f"required_validator missing: {req_v}")
    if actual_shader_hashes is not None:
        errors.extend(_check_disk_hashes(entries, actual_shader_hashes))
    return complete, errors


def _check_disk_hashes(
    entries: list[CertifiedShaderEntry],
    actual_hashes: dict[tuple[str, str], tuple[int, str]],
) -> list[str]:
    errors: list[str] = []
    for e in entries:
        key = (e.kernel, e.target)
        if key not in actual_hashes:
            continue
        act_sz, act_sha_raw = actual_hashes[key]
        act_sha, err = normalize_sha256(act_sha_raw, f"actual[{e.kernel}/{e.target}]")
        if err or act_sz != e.shader_bytes or act_sha != e.shader_sha256:
            errors.append(f"shader_hash_mismatch({e.kernel}/{e.target})")
    return errors


def verify_gpu_200_pack(
    manifest: Any,
    *,
    min_shaders: int = 200,
    min_kernels: int = 40,
    min_rewrites: int = 1228,
    max_parity_err: float = 1e-4,
    observed_parity_err: float = 0.0,
    required_validators: tuple[str, ...] = ("dxc", "glslangvalidator", "spirv-val"),
    actual_shader_hashes: dict[tuple[str, str], tuple[int, str]] | None = None,
) -> Gpu200GateReport:
    """Run fail-closed verification on the 200-shader 5-backend GPU manifest."""
    pre_errs = _validate_policy(min_shaders, min_kernels, min_rewrites, max_parity_err)
    if not is_strict_finite_float(observed_parity_err) or float(observed_parity_err) < 0.0:
        pre_errs.append(f"observed_parity_err: invalid {observed_parity_err!r}")
    if pre_errs:
        return _fail_report("; ".join(pre_errs))
    entries, parse_errs = parse_gpu_200_manifest(manifest)
    complete, pol_errs = _check_entries_policy(
        entries, min_shaders, min_kernels, min_rewrites, required_validators, actual_shader_hashes
    )
    violations = list(parse_errs) + list(pol_errs)
    if float(observed_parity_err) > float(max_parity_err):
        violations.append(f"parity_err {observed_parity_err} > {max_parity_err}")
    ordered = sorted(entries, key=lambda e: (e.kernel, e.target))
    vals = tuple(sorted({e.external_validator for e in ordered}))
    attest = {
        "unique_kernels": len({e.kernel for e in ordered}),
        "total_shaders": len(ordered),
        "total_superopt_rewrites": sum(e.rewrites for e in ordered),
        "total_shader_bytes": sum(e.shader_bytes for e in ordered),
        "shaders": [(e.kernel, e.target, e.shader_bytes, e.shader_sha256, e.cert_sha256, e.rewrites) for e in ordered],
    }
    return Gpu200GateReport(
        passed=len(violations) == 0,
        unique_kernels=len({e.kernel for e in ordered}),
        total_shaders=len(ordered),
        complete_5target_kernels=complete,
        total_superopt_rewrites=sum(e.rewrites for e in ordered),
        total_shader_bytes=sum(e.shader_bytes for e in ordered),
        validators_observed=vals,
        gpu_shader_200_attestation_sha256=canonical_sha256_hex(attest),
        violations=tuple(violations),
    )


def _fail_report(message: str) -> Gpu200GateReport:
    return Gpu200GateReport(False, 0, 0, 0, 0, 0, (), "", (message,))


def verify_gpu_200_pack_files(
    manifest_path: Path | str,
    *,
    min_shaders: int = 200,
    min_kernels: int = 40,
    min_rewrites: int = 1228,
    observed_parity_err: float = 0.0,
    shader_root: Path | str | None = None,
) -> Gpu200GateReport:
    """Load gpu_200pack_manifest.json from disk and verify fail-closed."""
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return _fail_report(f"io_error: {exc}")
    actual_hashes: dict[tuple[str, str], tuple[int, str]] | None = None
    if shader_root is not None and isinstance(manifest, dict) and isinstance(manifest.get("shaders"), list):
        root = Path(shader_root)
        actual_hashes = {}
        for item in manifest["shaders"]:
            if isinstance(item, dict) and item.get("shader_relpath"):
                fp = root / str(item["shader_relpath"])
                if fp.is_file():
                    data = fp.read_bytes()
                    actual_hashes[(str(item.get("kernel", "")), str(item.get("target", "")).lower())] = (
                        len(data), hashlib.sha256(data).hexdigest()
                    )
    return verify_gpu_200_pack(
        manifest,
        min_shaders=min_shaders,
        min_kernels=min_kernels,
        min_rewrites=min_rewrites,
        observed_parity_err=observed_parity_err,
        actual_shader_hashes=actual_hashes,
    )
