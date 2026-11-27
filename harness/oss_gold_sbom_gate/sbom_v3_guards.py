# SPDX-License-Identifier: MIT
"""Fail-closed OSI license, SPDX-2.3, CycloneDX 1.5, and on-disk hash guards for SBOM V3."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

EXPECTED_REPOS: int = 15
EXPECTED_SBOM_FILES: int = 30
MIN_COMPONENTS: int = 259

ALLOWED_OSI_LICENSES: frozenset[str] = frozenset(
    {"MIT", "AGPL-3.0-only", "CC-BY-4.0", "Apache-2.0", "BSD-3-Clause"}
)

FORBIDDEN_LICENSE_TOKENS: tuple[str, ...] = (
    "FSL-1.1",
    "PROPRIETARY",
    "ALL-RIGHTS-RESERVED",
    "BSL-1.1",
)

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
    if any(ch not in _HEX_CHARS for ch in low):
        return ""
    return low


def is_sha256_hex(digest: Any) -> bool:
    """Return True when digest is a valid 64-char hex SHA-256 string."""
    return bool(normalize_sha256(digest))


def is_git_sha40(value: Any) -> bool:
    """Return True when value is a 40-char lowercase/uppercase hex git SHA."""
    if not isinstance(value, str) or len(value) != 40:
        return False
    return all(ch in _HEX_CHARS for ch in value.lower())


def sha256_file(path: Path) -> str:
    """Compute streaming SHA-256 hex digest for an SBOM file."""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def check_osi_policy(audit: Any) -> list[str]:
    """Enforce zero FSL-1.1-MIT, zero proprietary, and zero copyleft-in-MIT drift."""
    if not isinstance(audit, Mapping):
        return ["osi_policy_audit_missing"]
    errs: list[str] = []
    for key in ("stale_fsl_in_sboms", "proprietary_in_sboms", "copyleft_in_mit_repos"):
        val = audit.get(key)
        if not is_strict_int(val) or val != 0:
            errs.append(f"osi_policy_violation:{key}:{val!r}")
    return errs


def _check_sbom_disk_file(
    path: Path,
    expected_sha: str,
    label: str,
    expected_marker: str,
) -> list[str]:
    if not path.is_file():
        return [f"sbom_missing_on_disk:{label}"]
    if sha256_file(path) != expected_sha:
        return [f"sbom_sha256_mismatch:{label}"]
    text = path.read_text(encoding="utf-8")
    errs: list[str] = []
    if expected_marker not in text:
        errs.append(f"sbom_missing_version_marker:{label}")
    upper = text.upper()
    for token in FORBIDDEN_LICENSE_TOKENS:
        if token in upper:
            errs.append(f"sbom_forbidden_license:{label}:{token}")
    return errs


def check_repo_entry(
    rec: Any,
    sbom_root: Path | None = None,
    check_on_disk: bool = False,
) -> list[str]:
    """Validate one repository entry in SBOM V3 fail-closed."""
    errs: list[str] = []
    slug = getattr(rec, "slug", "")
    if not isinstance(slug, str) or not slug:
        errs.append("repo_missing_slug")
    if not is_git_sha40(getattr(rec, "commit_sha", "")):
        errs.append(f"invalid_commit_sha:{slug}")
    lic = getattr(rec, "license_id", "")
    if lic not in ALLOWED_OSI_LICENSES:
        errs.append(f"disallowed_license:{slug}:{lic!r}")
    if any(tok in str(lic).upper() for tok in FORBIDDEN_LICENSE_TOKENS):
        errs.append(f"forbidden_license_token:{slug}:{lic!r}")
    cnt = getattr(rec, "component_count", -1)
    if not is_strict_int(cnt) or cnt <= 0:
        errs.append(f"invalid_component_count:{slug}:{cnt!r}")
    spdx_sha = getattr(rec, "spdx_sha256", "")
    cdx_sha = getattr(rec, "cdx_sha256", "")
    if not is_sha256_hex(spdx_sha):
        errs.append(f"invalid_spdx_sha256:{slug}")
    if not is_sha256_hex(cdx_sha):
        errs.append(f"invalid_cdx_sha256:{slug}")
    if check_on_disk and sbom_root is not None and not errs:
        errs.extend(_check_sbom_disk_file(sbom_root / rec.spdx_file, spdx_sha, f"{slug}:spdx", "SPDX-2.3"))
        errs.extend(_check_sbom_disk_file(sbom_root / rec.cdx_file, cdx_sha, f"{slug}:cdx", "CycloneDX"))
    return errs
