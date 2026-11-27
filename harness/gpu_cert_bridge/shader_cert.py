# SPDX-License-Identifier: MIT
"""GPU shader translation-validation certificate verifier.

Verifies buildlang.gpu-tv-cert/v1 certificates against on-disk or in-memory
shader bytes across all five supported GPU targets (wgsl, hlsl, msl, spirv,
glsl), failing closed on schema errors, target mismatch, unverified flags,
subgroup uniformity failures, or single-bit shader tampering.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

HONEST_SCOPE_LIMIT = (
    "Verifies buildlang.gpu-tv-cert/v1 JSON schema fields, constant-time "
    "shader_sha256 parity against raw shader bytes, subgroup uniformity "
    "metadata, and polyhedral schedule verification flags. Does not execute "
    "GPU shaders or invoke external validators such as naga, dxc, or spirv-val."
)

GPU_CERT_SCHEMA = "buildlang.gpu-tv-cert/v1"
TARGET_SHADER_EXT: dict[str, str] = {
    "wgsl": ".wgsl",
    "hlsl": ".hlsl",
    "msl": ".metal",
    "spirv": ".spv",
    "glsl": ".glsl",
}
REQUIRED_GPU_TARGETS: tuple[str, ...] = ("wgsl", "hlsl", "msl", "spirv", "glsl")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ShaderCertReport:
    """Fail-closed verification result for one GPU shader certificate."""

    passed: bool
    target: str
    shader_sha256: str
    actual_shader_sha256: str | None
    shader_bytes: int
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic JSON-serializable summary."""
        return {
            "passed": self.passed,
            "target": self.target,
            "shader_sha256": self.shader_sha256,
            "actual_shader_sha256": self.actual_shader_sha256,
            "shader_bytes": self.shader_bytes,
            "reasons": list(self.reasons),
        }


def sha256_hex(data: bytes) -> str:
    """Return lowercase hexadecimal SHA-256 digest of bytes."""
    return hashlib.sha256(data).hexdigest()


def is_hex64(value: object) -> bool:
    """Return True iff value is a 64-character lowercase hex string."""
    return isinstance(value, str) and bool(_HEX64_RE.fullmatch(value))


def _check_subgroup_plan(plan: object, reasons: list[str]) -> None:
    if plan is None:
        return
    if not isinstance(plan, Mapping):
        reasons.append("SUBGROUP_PLAN_INVALID")
        return
    if plan.get("uniformity_verified") is not True:
        reasons.append("SUBGROUP_UNIFORMITY_FAILED")
    if not is_hex64(plan.get("width_invariance_sha256")):
        reasons.append("MALFORMED_WIDTH_INVARIANCE_SHA256")
    widths = plan.get("widths_verified")
    if not isinstance(widths, list) or not widths or not all(
        isinstance(w, int) and not isinstance(w, bool) and w > 0 for w in widths
    ):
        reasons.append("SUBGROUP_WIDTHS_INVALID")
    mode = plan.get("mode")
    max_diff = plan.get("max_cross_width_abs_diff")
    if isinstance(mode, Mapping) and mode.get("kind") == "strict_bit_exact":
        if not isinstance(max_diff, (int, float)) or isinstance(max_diff, bool) or max_diff != 0.0:
            reasons.append("SUBGROUP_BIT_EXACT_DRIFT")


def _check_polyhedral_schedules(schedules: object, reasons: list[str]) -> None:
    if schedules is None:
        return
    if not isinstance(schedules, list):
        reasons.append("POLYHEDRAL_SCHEDULES_INVALID")
        return
    for idx, item in enumerate(schedules):
        if not isinstance(item, Mapping):
            reasons.append(f"POLYHEDRAL_SCHEDULE_INVALID:{idx}")
            continue
        if item.get("verified") is False:
            reasons.append(f"POLYHEDRAL_SCHEDULE_UNVERIFIED:{idx}")


def verify_shader_cert(
    cert: Mapping[str, object],
    shader_bytes: bytes,
    *,
    expected_target: str | None = None,
) -> ShaderCertReport:
    """Verify one GPU shader certificate against its raw shader bytes."""
    reasons: list[str] = []
    if not isinstance(cert, Mapping):
        return ShaderCertReport(False, "", "", None, 0, ("INVALID_CERT_OBJECT",))

    target = str(cert.get("target", ""))
    declared_sha = str(cert.get("shader_sha256", ""))
    if cert.get("schema") != GPU_CERT_SCHEMA:
        reasons.append("INVALID_SCHEMA")
    if target not in TARGET_SHADER_EXT:
        reasons.append(f"UNKNOWN_TARGET:{target}")
    if expected_target is not None and target != expected_target:
        reasons.append(f"TARGET_MISMATCH:{target}!={expected_target}")
    if cert.get("verified") is not True:
        reasons.append("CERT_NOT_VERIFIED")
    if not is_hex64(cert.get("cert_sha256")):
        reasons.append("MALFORMED_CERT_SHA256")
    if not is_hex64(declared_sha):
        reasons.append("MALFORMED_SHADER_SHA256")

    actual_sha: str | None = None
    size = 0
    if not isinstance(shader_bytes, (bytes, bytearray)) or len(shader_bytes) == 0:
        reasons.append("EMPTY_SHADER_BYTES")
    else:
        raw = bytes(shader_bytes)
        size = len(raw)
        actual_sha = sha256_hex(raw)
        if is_hex64(declared_sha) and not hmac.compare_digest(actual_sha, declared_sha):
            reasons.append("SHADER_SHA256_MISMATCH")

    _check_subgroup_plan(cert.get("subgroup_plan"), reasons)
    _check_polyhedral_schedules(cert.get("polyhedral_schedules"), reasons)

    return ShaderCertReport(
        passed=not reasons,
        target=target,
        shader_sha256=declared_sha,
        actual_shader_sha256=actual_sha,
        shader_bytes=size,
        reasons=tuple(reasons),
    )


def verify_shader_cert_files(
    cert_path: Path,
    shader_path: Path,
    *,
    expected_target: str | None = None,
) -> ShaderCertReport:
    """Load certificate JSON and shader file from disk and verify fail-closed."""
    if not cert_path.is_file():
        return ShaderCertReport(False, expected_target or "", "", None, 0, ("MISSING_CERT_FILE",))
    if not shader_path.is_file():
        return ShaderCertReport(False, expected_target or "", "", None, 0, ("MISSING_SHADER_FILE",))
    try:
        cert = json.loads(cert_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ShaderCertReport(False, expected_target or "", "", None, 0, ("INVALID_CERT_JSON",))
    return verify_shader_cert(cert, shader_path.read_bytes(), expected_target=expected_target)
