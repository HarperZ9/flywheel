# SPDX-License-Identifier: MIT
"""5-target GPU shader certificate matrix gate.

Audits an emitted shader directory for complete target coverage (wgsl, hlsl,
msl, spirv, glsl), shader_sha256 integrity against on-disk shader bytes, and
embedded Superoptimizer V6 monotone MIR cost certificates.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .shader_cert import (
    REQUIRED_GPU_TARGETS,
    TARGET_SHADER_EXT,
    sha256_hex,
    verify_shader_cert,
)
from .superopt_chain import extract_superopt_cert, verify_superopt_cert

HONEST_SCOPE_LIMIT = (
    "Audits an emitted directory of GPU shader certificates for complete "
    "5-target coverage, raw shader SHA-256 parity, and monotone superoptimizer "
    "MIR cost. Does not compile BuildLang source files or execute GPU kernels."
)

_CERT_SUFFIX = ".gpu-cert.json"


@dataclass(frozen=True)
class KernelMatrixEntry:
    """Verification summary for one GPU kernel across required targets."""

    kernel: str
    passed: bool
    targets_verified: tuple[str, ...]
    missing_targets: tuple[str, ...]
    total_cost_before: int
    total_cost_after: int
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic JSON-serializable summary."""
        return {
            "kernel": self.kernel,
            "passed": self.passed,
            "targets_verified": list(self.targets_verified),
            "missing_targets": list(self.missing_targets),
            "total_cost_before": self.total_cost_before,
            "total_cost_after": self.total_cost_after,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class GpuMatrixReport:
    """Fail-closed result for a full multi-kernel, 5-target GPU cert matrix."""

    passed: bool
    kernels_checked: int
    shaders_verified: int
    required_targets: tuple[str, ...]
    entries: tuple[KernelMatrixEntry, ...]
    reasons: tuple[str, ...]
    attestation_sha256: str

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic JSON-serializable summary."""
        return {
            "passed": self.passed,
            "kernels_checked": self.kernels_checked,
            "shaders_verified": self.shaders_verified,
            "required_targets": list(self.required_targets),
            "entries": [entry.to_dict() for entry in self.entries],
            "reasons": list(self.reasons),
            "attestation_sha256": self.attestation_sha256,
        }


def discover_kernel_certs(emitted_dir: Path) -> dict[str, dict[str, Path]]:
    """Map kernel name -> target -> cert path for all *.gpu-cert.json files."""
    found: dict[str, dict[str, Path]] = {}
    if not emitted_dir.is_dir():
        return found
    for cert_path in sorted(emitted_dir.glob(f"*{_CERT_SUFFIX}")):
        stem = cert_path.name[: -len(_CERT_SUFFIX)]
        if "." not in stem:
            continue
        kernel, target = stem.rsplit(".", 1)
        found.setdefault(kernel, {})[target] = cert_path
    return found


def _seal_matrix(entries: Sequence[KernelMatrixEntry], passed: bool, reasons: Sequence[str]) -> str:
    payload = {
        "passed": passed,
        "reasons": list(reasons),
        "entries": [e.to_dict() for e in entries],
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_hex(raw)


def _verify_target_pair(
    emitted_dir: Path,
    kernel: str,
    target: str,
    cert_path: Path,
    max_allowed_ulps: int,
    k_reasons: list[str],
) -> tuple[bool, int, int]:
    ext = TARGET_SHADER_EXT.get(target)
    if ext is None:
        k_reasons.append(f"UNSUPPORTED_TARGET:{kernel}:{target}")
        return False, 0, 0
    shader_path = emitted_dir / f"{kernel}{ext}"
    if not shader_path.is_file():
        k_reasons.append(f"MISSING_SHADER_FILE:{kernel}:{target}")
        return False, 0, 0
    try:
        cert_obj = json.loads(cert_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        k_reasons.append(f"INVALID_CERT_JSON:{kernel}:{target}")
        return False, 0, 0
    shader_rep = verify_shader_cert(cert_obj, shader_path.read_bytes(), expected_target=target)
    if not shader_rep.passed:
        k_reasons.extend(f"{kernel}:{target}:{r}" for r in shader_rep.reasons)
    superopt_obj = extract_superopt_cert(cert_obj)
    if superopt_obj is None:
        k_reasons.append(f"MISSING_SUPEROPT_CERT:{kernel}:{target}")
        return False, 0, 0
    so_rep = verify_superopt_cert(superopt_obj, expected_target=target, max_allowed_ulps=max_allowed_ulps)
    if not so_rep.passed:
        k_reasons.extend(f"{kernel}:{target}:{r}" for r in so_rep.reasons)
    return shader_rep.passed and so_rep.passed, so_rep.total_cost_before, so_rep.total_cost_after


def _verify_kernel_entry(
    emitted_dir: Path,
    kernel: str,
    target_map: dict[str, Path],
    req_targets: tuple[str, ...],
    max_allowed_ulps: int,
) -> KernelMatrixEntry:
    k_reasons: list[str] = []
    verified: list[str] = []
    missing: list[str] = []
    cb_sum = ca_sum = 0
    for target in req_targets:
        cert_path = target_map.get(target)
        if cert_path is None:
            missing.append(target)
            k_reasons.append(f"MISSING_TARGET:{kernel}:{target}")
            continue
        ok, cb, ca = _verify_target_pair(emitted_dir, kernel, target, cert_path, max_allowed_ulps, k_reasons)
        cb_sum += cb
        ca_sum += ca
        if ok:
            verified.append(target)
    passed = not k_reasons and len(verified) == len(req_targets)
    return KernelMatrixEntry(kernel, passed, tuple(verified), tuple(missing), cb_sum, ca_sum, tuple(k_reasons))


def verify_gpu_cert_matrix(
    emitted_dir: Path,
    *,
    required_targets: Sequence[str] = REQUIRED_GPU_TARGETS,
    expected_kernels: Sequence[str] | None = None,
    max_allowed_ulps: int = 1,
) -> GpuMatrixReport:
    """Verify every kernel in emitted_dir across all required GPU targets."""
    req_targets = tuple(required_targets)
    global_reasons: list[str] = []
    if not req_targets:
        global_reasons.append("EMPTY_REQUIRED_TARGETS")
    if not emitted_dir.is_dir():
        global_reasons.append("MISSING_EMITTED_DIR")
        return GpuMatrixReport(False, 0, 0, req_targets, (), tuple(global_reasons), _seal_matrix((), False, global_reasons))
    discovered = discover_kernel_certs(emitted_dir)
    kernel_names = sorted(set(discovered) | set(expected_kernels or ()))
    if not kernel_names:
        global_reasons.append("EMPTY_MATRIX")
    entries: list[KernelMatrixEntry] = []
    shaders_verified = 0
    for kernel in kernel_names:
        entry = _verify_kernel_entry(emitted_dir, kernel, discovered.get(kernel, {}), req_targets, max_allowed_ulps)
        entries.append(entry)
        shaders_verified += len(entry.targets_verified)
        global_reasons.extend(entry.reasons)
    passed = not global_reasons and bool(entries) and all(e.passed for e in entries)
    seal = _seal_matrix(entries, passed, global_reasons)
    return GpuMatrixReport(passed, len(entries), shaders_verified, req_targets, tuple(entries), tuple(global_reasons), seal)
