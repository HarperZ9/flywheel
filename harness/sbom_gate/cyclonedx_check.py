# SPDX-License-Identifier: MIT
"""Pure-stdlib CycloneDX 1.5 SBOM structural, license, and zero-PII verifier.

Validates CycloneDX 1.5 JSON documents for required bomFormat/specVersion
headers, serialNumber URN, metadata root component, non-empty components and
dependencies, valid SPDX license expressions, and zero local path/PII leaks.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from .spdx_check import (
    DEFAULT_FORBIDDEN_LICENSES,
    check_license_policy,
    scan_pii_and_paths,
)

HONEST_SCOPE_LIMIT = (
    "Validates CycloneDX 1.5 JSON headers, component/dependency lists, license "
    "expression policies, and static local-path, email, and secret patterns. "
    "Does not resolve remote PURLs, verify JWS signatures, or query CVE feeds."
)

CYCLONEDX_FORMAT = "CycloneDX"
CYCLONEDX_SPEC_VERSION = "1.5"


@dataclass(frozen=True)
class CycloneDxAuditReport:
    """Fail-closed validation result for one CycloneDX 1.5 JSON document."""

    passed: bool
    root_name: str
    spec_version: str
    component_count: int
    licenses_seen: tuple[str, ...]
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Serialize report into a deterministic JSON-compatible dict."""
        return {
            "passed": self.passed,
            "root_name": self.root_name,
            "spec_version": self.spec_version,
            "component_count": self.component_count,
            "licenses_seen": list(self.licenses_seen),
            "reasons": list(self.reasons),
        }


def _extract_cdx_licenses(component: Mapping[str, object]) -> list[str]:
    entries = component.get("licenses")
    if not isinstance(entries, list):
        return []
    found: list[str] = []
    for item in entries:
        if not isinstance(item, Mapping):
            continue
        expr = item.get("expression")
        if isinstance(expr, str) and expr.strip():
            found.append(expr.strip())
            continue
        lic = item.get("license")
        if isinstance(lic, Mapping):
            val = lic.get("id") or lic.get("name")
            if isinstance(val, str) and val.strip():
                found.append(val.strip())
    return found


def _check_cdx_components(
    comps: object,
    min_components: int,
    forbidden_licenses: Iterable[str],
    allowed_licenses: Iterable[str] | None,
    reasons: list[str],
) -> tuple[int, set[str]]:
    seen: set[str] = set()
    if not isinstance(comps, list) or len(comps) < min_components:
        reasons.append("INSUFFICIENT_CYCLONEDX_COMPONENTS")
        return 0, seen
    for idx, comp in enumerate(comps):
        if not isinstance(comp, Mapping):
            reasons.append(f"INVALID_COMPONENT:{idx}")
            continue
        for expr in _extract_cdx_licenses(comp):
            seen.add(expr)
            reasons.extend(check_license_policy(expr, forbidden_licenses=forbidden_licenses, allowed_licenses=allowed_licenses))
    return len(comps), seen


def verify_cyclonedx_doc(
    doc: Mapping[str, object],
    raw_text: str | None = None,
    *,
    forbidden_licenses: Iterable[str] = DEFAULT_FORBIDDEN_LICENSES,
    allowed_licenses: Iterable[str] | None = None,
    min_components: int = 1,
) -> CycloneDxAuditReport:
    """Verify a CycloneDX 1.5 document fail-closed."""
    if not isinstance(doc, Mapping):
        return CycloneDxAuditReport(False, "", "", 0, (), ("INVALID_CYCLONEDX_OBJECT",))
    reasons: list[str] = []
    spec_ver = str(doc.get("specVersion", ""))
    if doc.get("bomFormat") != CYCLONEDX_FORMAT:
        reasons.append("INVALID_OR_MISSING_BOM_FORMAT")
    if spec_ver != CYCLONEDX_SPEC_VERSION:
        reasons.append(f"INVALID_SPEC_VERSION:{spec_ver}")
    serial = doc.get("serialNumber")
    if not isinstance(serial, str) or not serial.startswith("urn:uuid:"):
        reasons.append("INVALID_SERIAL_NUMBER")
    meta = doc.get("metadata")
    root_name = ""
    if not isinstance(meta, Mapping) or not isinstance(meta.get("component"), Mapping):
        reasons.append("MISSING_METADATA_COMPONENT")
    else:
        root_name = str(meta["component"].get("name", ""))
    deps = doc.get("dependencies")
    if not isinstance(deps, list) or not deps:
        reasons.append("MISSING_DEPENDENCIES")
    comp_count, seen_licenses = _check_cdx_components(
        doc.get("components"), min_components, forbidden_licenses, allowed_licenses, reasons,
    )
    text_to_scan = raw_text if raw_text is not None else json.dumps(doc, sort_keys=True)
    reasons.extend(scan_pii_and_paths(text_to_scan))
    return CycloneDxAuditReport(
        not reasons, root_name, spec_ver, comp_count,
        tuple(sorted(seen_licenses)), tuple(dict.fromkeys(reasons)),
    )


def verify_cyclonedx_file(
    path: Path,
    *,
    forbidden_licenses: Iterable[str] = DEFAULT_FORBIDDEN_LICENSES,
    allowed_licenses: Iterable[str] | None = None,
    min_components: int = 1,
) -> CycloneDxAuditReport:
    """Load a CycloneDX 1.5 JSON file from disk and validate fail-closed."""
    if not path.is_file():
        return CycloneDxAuditReport(False, "", "", 0, (), ("MISSING_CYCLONEDX_FILE",))
    try:
        raw = path.read_text(encoding="utf-8")
        doc = json.loads(raw)
    except (OSError, ValueError):
        return CycloneDxAuditReport(False, "", "", 0, (), ("INVALID_CYCLONEDX_JSON",))
    return verify_cyclonedx_doc(
        doc,
        raw,
        forbidden_licenses=forbidden_licenses,
        allowed_licenses=allowed_licenses,
        min_components=min_components,
    )
