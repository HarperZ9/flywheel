# SPDX-License-Identifier: MIT
"""Pure-stdlib parser for the 200-shader 5-backend GPU compute manifest.

Validates gpu_200pack_manifest.json structure, strict MIT licensing, 5-target
completeness per kernel, verify_cert PASS status, external validator pass tags,
positive byte sizes, 64-hex shader/cert digests, and aggregate arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .shader_guards import (
    REQUIRED_GPU_TARGETS,
    is_passing_validator_tag,
    is_strict_int,
    normalize_sha256,
)

HONEST_SCOPE_LIMIT = (
    "Parses and validates gpu_200pack_manifest.json entries and aggregate "
    "counters in pure Python stdlib. Does not recompile BuildLang shaders."
)


@dataclass(frozen=True)
class CertifiedShaderEntry:
    """One validated shader entry in the 200-shader 5-backend pack."""

    batch: str
    kernel: str
    target: str
    shader_bytes: int
    shader_sha256: str
    cert_sha256: str
    rewrites: int
    external_validator: str


def parse_gpu_200_manifest(
    manifest: Any,
) -> tuple[list[CertifiedShaderEntry], list[str]]:
    """Parse and validate all shader entries and header fields in a manifest."""
    if not isinstance(manifest, dict):
        return [], ["manifest: root must be a JSON object"]
    errors: list[str] = []
    if manifest.get("license") != "MIT":
        errors.append(f"manifest.license: expected MIT, got {manifest.get('license')!r}")
    raw_shaders = manifest.get("shaders")
    if not isinstance(raw_shaders, list) or not raw_shaders:
        return [], errors + ["manifest.shaders: expected non-empty list"]
    entries: list[CertifiedShaderEntry] = []
    seen_pairs: set[tuple[str, str]] = set()
    for idx, item in enumerate(raw_shaders):
        entry, item_errs = _parse_one_shader(item, idx, seen_pairs)
        errors.extend(item_errs)
        if entry is not None:
            entries.append(entry)
    errors.extend(_check_manifest_totals(manifest, entries))
    return entries, errors


def _parse_one_shader(
    item: Any,
    idx: int,
    seen_pairs: set[tuple[str, str]],
) -> tuple[CertifiedShaderEntry | None, list[str]]:
    if not isinstance(item, dict):
        return None, [f"shaders[{idx}]: expected object"]
    errs: list[str] = []
    kernel = str(item.get("kernel", "")).strip()
    target = str(item.get("target", "")).strip().lower()
    batch = str(item.get("batch", "")).strip()
    if not kernel:
        errs.append(f"shaders[{idx}]: empty kernel")
    if target not in REQUIRED_GPU_TARGETS:
        errs.append(f"shaders[{idx}]({kernel}): unknown target {target!r}")
    if (kernel, target) in seen_pairs:
        errs.append(f"shaders[{idx}]: duplicate ({kernel}, {target})")
    else:
        seen_pairs.add((kernel, target))
    s_bytes = item.get("shader_bytes")
    if not is_strict_int(s_bytes) or s_bytes <= 0:
        errs.append(f"shaders[{idx}]({kernel}/{target}): invalid shader_bytes {s_bytes!r}")
    rewrites = item.get("rewrites")
    if not is_strict_int(rewrites) or rewrites < 0:
        errs.append(f"shaders[{idx}]({kernel}/{target}): invalid rewrites {rewrites!r}")
    if item.get("verify_cert") != "PASS":
        errs.append(f"shaders[{idx}]({kernel}/{target}): verify_cert != PASS")
    ext_val = item.get("external_validator")
    if not is_passing_validator_tag(ext_val):
        errs.append(f"shaders[{idx}]({kernel}/{target}): failing external_validator {ext_val!r}")
    s_sha, e1 = normalize_sha256(item.get("shader_sha256"), f"shaders[{idx}].shader_sha256")
    c_sha, e2 = normalize_sha256(item.get("cert_sha256"), f"shaders[{idx}].cert_sha256")
    errs.extend([e for e in (e1, e2) if e])
    if errs or s_sha is None or c_sha is None:
        return None, errs
    return CertifiedShaderEntry(batch, kernel, target, s_bytes, s_sha, c_sha, rewrites, str(ext_val).strip()), []


def _check_manifest_totals(
    manifest: dict[str, Any],
    entries: list[CertifiedShaderEntry],
) -> list[str]:
    errors: list[str] = []
    kernels = {e.kernel for e in entries}
    actual_bytes = sum(e.shader_bytes for e in entries)
    actual_rewrites = sum(e.rewrites for e in entries)
    checks = (
        ("unique_kernels", len(kernels)),
        ("total_certified_shaders", len(entries)),
        ("total_shader_bytes", actual_bytes),
        ("total_superopt_rewrites", actual_rewrites),
    )
    for key, actual in checks:
        got = manifest.get(key)
        if not is_strict_int(got) or got != actual:
            errors.append(f"manifest.{key}: reported {got!r} != actual {actual}")
    ptc = manifest.get("per_target_counts")
    if not isinstance(ptc, dict):
        errors.append("manifest.per_target_counts: missing mapping")
    else:
        for tgt in sorted(REQUIRED_GPU_TARGETS):
            cnt = sum(1 for e in entries if e.target == tgt)
            got = ptc.get(tgt)
            if not is_strict_int(got) or got != cnt:
                errors.append(f"per_target_counts[{tgt}]: {got!r} != {cnt}")
    return errors
