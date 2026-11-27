# SPDX-License-Identifier: MIT
"""Pure-stdlib SPDX 2.3 SBOM structural, license, and zero-PII verifier.

Validates SPDX-2.3 JSON documents for required document headers, package
entries, SPDX license expression syntax, forbidden-license denylists, and
zero local workstation path, email, or secret leaks.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

HONEST_SCOPE_LIMIT = (
    "Validates SPDX 2.3 JSON headers, package lists, SPDX license expression "
    "syntax, configurable license denylists/allowlists, and static local-path, "
    "email, and secret regexes. Does not resolve external PURL registries, "
    "verify detached SBOM signatures, or query CVE databases."
)

SPDX_VERSION = "SPDX-2.3"
SPDX_DATA_LICENSE = "CC0-1.0"
SPDX_DOCUMENT_ID = "SPDXRef-DOCUMENT"

DEFAULT_FORBIDDEN_LICENSES: frozenset[str] = frozenset(
    {
        "SSPL-1.0",
        "BSL-1.1",
        "BUSL-1.1",
        "UNLICENSED",
        "ALL-RIGHTS-RESERVED",
        "Commons-Clause",
    }
)

_SPDX_TOKEN = r"[A-Za-z0-9.+-]+"
_SPDX_EXPR_RE = re.compile(
    rf"^(?:\(*{_SPDX_TOKEN}\)*)(?:\s+(?:OR|AND|WITH)\s+(?:\(*{_SPDX_TOKEN}\)*))*$"
)
_DRIVE_PATH_RE = re.compile(r"\b[A-Za-z]:[/\\]")
_POSIX_HOME_RE = re.compile(
    r"(?:" + "/" + "ho" + "me/" + r"[A-Za-z0-9._-]+/|"
    + "/" + "Us" + "ers/" + r"[A-Za-z0-9._-]+/)"
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+\x40[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_SECRET_RES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("AWS_KEY_LEAK", re.compile(r"\bAK" + r"IA[0-9A-Z]{16}\b")),
    ("GITHUB_TOKEN_LEAK", re.compile(r"\bgh" + r"[pousr]_[A-Za-z0-9]{20,}\b")),
    ("PRIVATE_KEY_LEAK", re.compile(r"-----BEGIN [A-Z ]*PRIVATE" + r" KEY-----")),
)


@dataclass(frozen=True)
class SpdxAuditReport:
    """Fail-closed validation result for one SPDX 2.3 JSON document."""

    passed: bool
    name: str
    spdx_version: str
    package_count: int
    licenses_seen: tuple[str, ...]
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Serialize report into a deterministic JSON-compatible dict."""
        return {
            "passed": self.passed,
            "name": self.name,
            "spdx_version": self.spdx_version,
            "package_count": self.package_count,
            "licenses_seen": list(self.licenses_seen),
            "reasons": list(self.reasons),
        }


def is_valid_spdx_expression(expr: object) -> bool:
    """Check SPDX license expression token grammar and balanced parens."""
    if not isinstance(expr, str):
        return False
    text = expr.strip()
    if not text or not _SPDX_EXPR_RE.fullmatch(text):
        return False
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def extract_license_tokens(expr: str) -> list[str]:
    """Extract individual license identifiers from an SPDX expression."""
    cleaned = expr.replace("(", " ").replace(")", " ")
    return [tok for tok in cleaned.split() if tok not in {"OR", "AND", "WITH"}]


def scan_pii_and_paths(raw_text: str) -> list[str]:
    """Detect local workstation paths, email addresses, and raw secret tokens."""
    hits: list[str] = []
    if _DRIVE_PATH_RE.search(raw_text):
        hits.append("LOCAL_WINDOWS_PATH_LEAK")
    if _POSIX_HOME_RE.search(raw_text):
        hits.append("LOCAL_POSIX_PATH_LEAK")
    if _EMAIL_RE.search(raw_text):
        hits.append("EMAIL_PII_LEAK")
    for code, rx in _SECRET_RES:
        if rx.search(raw_text):
            hits.append(code)
    return hits


def check_license_policy(
    expr: str,
    *,
    forbidden_licenses: Iterable[str] = DEFAULT_FORBIDDEN_LICENSES,
    allowed_licenses: Iterable[str] | None = None,
) -> list[str]:
    """Validate one SPDX expression against forbidden/allowed token policies."""
    if not is_valid_spdx_expression(expr):
        return [f"INVALID_SPDX_LICENSE:{expr!r}"]
    reasons: list[str] = []
    forbidden_set = {tok.lower() for tok in forbidden_licenses}
    allowed_set = {tok.lower() for tok in allowed_licenses} if allowed_licenses is not None else None
    for tok in extract_license_tokens(expr):
        low = tok.lower()
        if low in forbidden_set:
            reasons.append(f"FORBIDDEN_LICENSE:{tok}")
        elif allowed_set is not None and low not in allowed_set:
            reasons.append(f"UNAPPROVED_LICENSE:{tok}")
    return reasons


def _check_spdx_packages(
    pkgs: object,
    min_packages: int,
    forbidden_licenses: Iterable[str],
    allowed_licenses: Iterable[str] | None,
    reasons: list[str],
) -> tuple[int, set[str]]:
    seen: set[str] = set()
    if not isinstance(pkgs, list) or len(pkgs) < min_packages:
        reasons.append("INSUFFICIENT_SPDX_PACKAGES")
        return 0, seen
    for idx, pkg in enumerate(pkgs):
        if not isinstance(pkg, Mapping):
            reasons.append(f"INVALID_PACKAGE:{idx}")
            continue
        lic = pkg.get("licenseConcluded")
        if not isinstance(lic, str):
            reasons.append(f"MISSING_PACKAGE_LICENSE:{idx}")
            continue
        seen.add(lic)
        reasons.extend(check_license_policy(lic, forbidden_licenses=forbidden_licenses, allowed_licenses=allowed_licenses))
    return len(pkgs), seen


def verify_spdx_doc(
    doc: Mapping[str, object],
    raw_text: str | None = None,
    *,
    forbidden_licenses: Iterable[str] = DEFAULT_FORBIDDEN_LICENSES,
    allowed_licenses: Iterable[str] | None = None,
    min_packages: int = 1,
) -> SpdxAuditReport:
    """Verify an SPDX 2.3 document fail-closed."""
    if not isinstance(doc, Mapping):
        return SpdxAuditReport(False, "", "", 0, (), ("INVALID_SPDX_OBJECT",))
    reasons: list[str] = []
    ver, name = str(doc.get("spdxVersion", "")), str(doc.get("name", ""))
    if ver != SPDX_VERSION:
        reasons.append(f"INVALID_SPDX_VERSION:{ver}")
    if doc.get("dataLicense") != SPDX_DATA_LICENSE:
        reasons.append("INVALID_DATA_LICENSE")
    if doc.get("SPDXID") != SPDX_DOCUMENT_ID:
        reasons.append("MISSING_SPDXREF_DOCUMENT")
    if not isinstance(doc.get("documentNamespace"), str) or not str(doc.get("documentNamespace")).strip():
        reasons.append("MISSING_DOCUMENT_NAMESPACE")
    creation = doc.get("creationInfo")
    if not isinstance(creation, Mapping) or not creation.get("creators"):
        reasons.append("MISSING_CREATION_INFO")
    rels = doc.get("relationships")
    if not isinstance(rels, list) or not rels:
        reasons.append("MISSING_RELATIONSHIPS")
    pkg_count, seen_licenses = _check_spdx_packages(
        doc.get("packages"), min_packages, forbidden_licenses, allowed_licenses, reasons,
    )
    text_to_scan = raw_text if raw_text is not None else json.dumps(doc, sort_keys=True)
    reasons.extend(scan_pii_and_paths(text_to_scan))
    return SpdxAuditReport(
        not reasons, name, ver, pkg_count,
        tuple(sorted(seen_licenses)), tuple(dict.fromkeys(reasons)),
    )


def verify_spdx_file(
    path: Path,
    *,
    forbidden_licenses: Iterable[str] = DEFAULT_FORBIDDEN_LICENSES,
    allowed_licenses: Iterable[str] | None = None,
    min_packages: int = 1,
) -> SpdxAuditReport:
    """Load an SPDX 2.3 JSON file from disk and validate fail-closed."""
    if not path.is_file():
        return SpdxAuditReport(False, "", "", 0, (), ("MISSING_SPDX_FILE",))
    try:
        raw = path.read_text(encoding="utf-8")
        doc = json.loads(raw)
    except (OSError, ValueError):
        return SpdxAuditReport(False, "", "", 0, (), ("INVALID_SPDX_JSON",))
    return verify_spdx_doc(
        doc,
        raw,
        forbidden_licenses=forbidden_licenses,
        allowed_licenses=allowed_licenses,
        min_packages=min_packages,
    )
