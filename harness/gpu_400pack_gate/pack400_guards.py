# SPDX-License-Identifier: MIT
"""Fail-closed shader and JFC3P-14B-Oracle-v12 RLVR guards for the GPU 400-pack."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

REQUIRED_TARGETS: tuple[str, ...] = ("wgsl", "hlsl", "msl", "spirv", "glsl")
EXPECTED_KERNELS: int = 80
EXPECTED_SHADERS: int = 400
MIN_SUPEROPT_REWRITES: int = 2817
EXPECTED_RLVR_TASKS: int = 1024
EXPECTED_RLVR_CATEGORIES: int = 28

_HEX_CHARS = frozenset("0123456789abcdef")


def is_strict_int(value: Any) -> bool:
    """Return True only for plain integers, excluding booleans."""
    return isinstance(value, int) and not isinstance(value, bool)


def normalize_sha256(digest: Any) -> str:
    """Strip optional sha256: prefix and validate 64 lowercase hex characters."""
    if not isinstance(digest, str):
        return ""
    raw = digest[7:] if digest.startswith("sha256:") else digest
    if len(raw) != 64:
        return ""
    low = raw.lower()
    return low if all(ch in _HEX_CHARS for ch in low) else ""


def is_sha256_hex(digest: Any) -> bool:
    """Return True when digest is a valid 64-char hex SHA-256 string."""
    return bool(normalize_sha256(digest))


def sha256_file(path: Path) -> str:
    """Compute streaming SHA-256 hex digest for an artifact file."""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


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


def check_rlvr_v12_manifest(
    rlvr: Any,
    expected_tasks: int = EXPECTED_RLVR_TASKS,
    expected_cats: int = EXPECTED_RLVR_CATEGORIES,
    rlvr_root: Path | None = None,
    check_on_disk: bool = False,
) -> tuple[int, int, list[str]]:
    """Verify JFC3P-14B-Oracle-v12 (1,024/1,024 pure-MIT RLVR) manifest fail-closed."""
    if not isinstance(rlvr, Mapping):
        return 0, 0, ["rlvr_manifest_not_mapping"]
    errs: list[str] = []
    if rlvr.get("schema") != "jfc3p-14b-oracle-rlvr-pack/12":
        errs.append(f"invalid_rlvr_schema:{rlvr.get('schema')!r}")
    if rlvr.get("license") != "MIT":
        errs.append(f"rlvr_non_mit_license:{rlvr.get('license')!r}")
    total = rlvr.get("total_tasks")
    train = rlvr.get("train_tasks")
    ev = rlvr.get("eval_tasks")
    cats = rlvr.get("categories")
    if not (is_strict_int(total) and is_strict_int(train) and is_strict_int(ev)):
        errs.append("rlvr_task_counts_invalid")
        return 0, 0, errs
    if total != expected_tasks or (train + ev) != total or train <= 0 or ev <= 0:
        errs.append(f"rlvr_split_mismatch:{train}+{ev}!={total}/{expected_tasks}")
    if not isinstance(cats, Mapping) or len(cats) != expected_cats:
        errs.append(f"rlvr_category_count_mismatch:{len(cats) if isinstance(cats, Mapping) else -1}!={expected_cats}")
    elif sum(v for v in cats.values() if is_strict_int(v)) != total:
        errs.append("rlvr_category_sum_mismatch")
    arts = rlvr.get("artifacts")
    if not isinstance(arts, Mapping) or len(arts) < 4:
        errs.append("rlvr_artifacts_incomplete")
    else:
        for fname, meta in arts.items():
            sha = normalize_sha256(meta.get("sha256", "") if isinstance(meta, Mapping) else "")
            if not sha:
                errs.append(f"rlvr_bad_artifact_sha256:{fname}")
            elif check_on_disk and rlvr_root is not None:
                fp = rlvr_root / fname
                if not fp.is_file() or sha256_file(fp) != sha:
                    errs.append(f"rlvr_disk_hash_mismatch:{fname}")
    cat_cnt = len(cats) if isinstance(cats, Mapping) else 0
    return (total if not errs else 0), cat_cnt, errs
