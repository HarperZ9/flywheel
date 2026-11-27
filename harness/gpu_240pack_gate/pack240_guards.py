# SPDX-License-Identifier: MIT
"""Fail-closed shader, validator, and planted-control guards for the GPU 240-pack."""

from __future__ import annotations

from typing import Any, Mapping

REQUIRED_TARGETS: tuple[str, ...] = ("wgsl", "hlsl", "msl", "spirv", "glsl")
EXPECTED_KERNELS: int = 48
EXPECTED_SHADERS: int = 240
MIN_SUPEROPT_REWRITES: int = 1425

REQUIRED_VALIDATORS: tuple[str, ...] = (
    "verify_cert",
    "dxc",
    "glslang",
    "spirv_val_direct",
    "spirv_val_glsl",
    "spirv_val_naga",
    "naga_wgsl",
    "naga_msl31",
    "msl_spec",
)

_HEX_CHARS = frozenset("0123456789abcdef")


def is_strict_int(value: Any) -> bool:
    """Return True only for plain integers, excluding booleans."""
    return isinstance(value, int) and not isinstance(value, bool)


def normalize_sha256(digest: Any) -> str:
    """Strip an optional sha256: prefix and validate 64 lowercase hex characters."""
    if not isinstance(digest, str):
        return ""
    raw = digest[7:] if digest.startswith("sha256:") else digest
    if len(raw) != 64:
        return ""
    low = raw.lower()
    if any(ch not in _HEX_CHARS for ch in low):
        return ""
    return low


def is_sha256_hex(digest: Any) -> bool:
    """Return True when digest is a valid 64-char hex SHA-256 string."""
    return bool(normalize_sha256(digest))


def check_shader_entry(entry: Any) -> list[str]:
    """Validate one certified GPU shader entry fail-closed."""
    errs: list[str] = []
    kernel = getattr(entry, "kernel", "")
    target = getattr(entry, "target", "")
    tag = f"{kernel}:{target}"
    if not isinstance(kernel, str) or not kernel.strip():
        errs.append("shader_missing_kernel")
    if target not in REQUIRED_TARGETS:
        errs.append(f"invalid_target:{tag}")
    if getattr(entry, "verify_cert", "") != "PASS":
        errs.append(f"uncertified_shader:{tag}:{getattr(entry, 'verify_cert', '')}")
    size = getattr(entry, "shader_bytes", -1)
    if not is_strict_int(size) or size <= 0:
        errs.append(f"invalid_shader_bytes:{tag}:{size!r}")
    rewrites = getattr(entry, "rewrites", -1)
    if not is_strict_int(rewrites) or rewrites < 0:
        errs.append(f"invalid_rewrites:{tag}:{rewrites!r}")
    if not is_sha256_hex(getattr(entry, "shader_sha256", "")):
        errs.append(f"invalid_shader_sha256:{tag}")
    if not is_sha256_hex(getattr(entry, "cert_sha256", "")):
        errs.append(f"invalid_cert_sha256:{tag}")
    return errs


def check_validation_counts(
    counts: Any,
    min_new_kernels: int = 8,
) -> list[str]:
    """Verify external shader validator counts (dxc, glslang, spirv-val, naga, msl)."""
    if not isinstance(counts, Mapping):
        return ["validation_counts_not_mapping"]
    errs: list[str] = []
    for key in REQUIRED_VALIDATORS:
        val = counts.get(key)
        min_req = min_new_kernels * 5 if key == "verify_cert" else min_new_kernels
        if not is_strict_int(val) or val < min_req:
            errs.append(f"validator_count_low:{key}:{val!r}<{min_req}")
    return errs


def check_planted_shader_controls(
    controls: Any,
    min_controls: int = 3,
) -> tuple[int, list[str]]:
    """Verify planted shader tamper controls all fail closed."""
    if not isinstance(controls, Mapping):
        return 0, ["planted_controls_not_mapping"]
    errs: list[str] = []
    passed = 0
    for name, rec in controls.items():
        if not isinstance(rec, Mapping):
            errs.append(f"control_not_mapping:{name}")
            continue
        if rec.get("rejected") is not True:
            errs.append(f"control_not_rejected:{name}")
            continue
        passed += 1
    if passed < min_controls:
        errs.append(f"controls_below_min:{passed}<{min_controls}")
    return passed, errs
