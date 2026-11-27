# SPDX-License-Identifier: MIT
"""Multi-flagship SPDX 2.3 and CycloneDX 1.5 supply-chain gate.

Discovers and validates all *.spdx.json and *.cdx.json SBOM documents in a
pack directory, enforces license and zero-PII/path hygiene fail-closed, and
seals a deterministic sbom_attestation_sha256 digest.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .cyclonedx_check import verify_cyclonedx_file
from .spdx_check import DEFAULT_FORBIDDEN_LICENSES, verify_spdx_file

HONEST_SCOPE_LIMIT = (
    "Audits an on-disk directory of SPDX 2.3 (*.spdx.json) and CycloneDX 1.5 "
    "(*.cdx.json) files for structural validity, license policy, and zero-PII "
    "hygiene, sealing a deterministic sbom_attestation_sha256. Does not "
    "generate SBOMs from build lockfiles or query vulnerability databases."
)


@dataclass(frozen=True)
class SbomFileResult:
    """Verification outcome for one SBOM file in a supply-chain pack."""

    rel_path: str
    fmt: str
    passed: bool
    item_count: int
    sha256: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Serialize file result into a JSON-compatible dictionary."""
        return {
            "rel_path": self.rel_path,
            "format": self.fmt,
            "passed": self.passed,
            "item_count": self.item_count,
            "sha256": self.sha256,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class SupplyChainGateReport:
    """Fail-closed attestation report for a full SBOM pack directory."""

    passed: bool
    sboms_checked: int
    sboms_passed: int
    spdx_count: int
    cyclonedx_count: int
    unified_components: int
    results: tuple[SbomFileResult, ...]
    reasons: tuple[str, ...]
    sbom_attestation_sha256: str

    def to_dict(self) -> dict[str, object]:
        """Serialize pack report into a deterministic JSON-compatible dict."""
        return {
            "passed": self.passed,
            "sboms_checked": self.sboms_checked,
            "sboms_passed": self.sboms_passed,
            "spdx_count": self.spdx_count,
            "cyclonedx_count": self.cyclonedx_count,
            "unified_components": self.unified_components,
            "results": [r.to_dict() for r in self.results],
            "reasons": list(self.reasons),
            "sbom_attestation_sha256": self.sbom_attestation_sha256,
        }


def discover_sbom_files(pack_dir: Path) -> list[Path]:
    """Return sorted list of all *.spdx.json and *.cdx.json files under pack_dir."""
    if not pack_dir.is_dir():
        return []
    found = [
        p
        for p in pack_dir.rglob("*.json")
        if p.is_file() and (p.name.endswith(".spdx.json") or p.name.endswith(".cdx.json"))
    ]
    return sorted(found, key=lambda p: p.relative_to(pack_dir).as_posix())


def _seal_pack(results: Sequence[SbomFileResult], passed: bool, reasons: Sequence[str]) -> str:
    payload = {
        "passed": passed,
        "reasons": list(reasons),
        "results": [r.to_dict() for r in results],
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _verify_one_sbom(
    path: Path,
    pack_dir: Path,
    forbidden_licenses: Iterable[str],
    allowed_licenses: Iterable[str] | None,
) -> SbomFileResult:
    rel = path.relative_to(pack_dir).as_posix()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if path.name.endswith(".spdx.json"):
        rep = verify_spdx_file(path, forbidden_licenses=forbidden_licenses, allowed_licenses=allowed_licenses)
        return SbomFileResult(rel, "SPDX-2.3", rep.passed, rep.package_count, digest, rep.reasons)
    rep_cdx = verify_cyclonedx_file(path, forbidden_licenses=forbidden_licenses, allowed_licenses=allowed_licenses)
    return SbomFileResult(rel, "CycloneDX-1.5", rep_cdx.passed, rep_cdx.component_count, digest, rep_cdx.reasons)


def verify_sbom_pack(
    pack_dir: Path,
    *,
    forbidden_licenses: Iterable[str] = DEFAULT_FORBIDDEN_LICENSES,
    allowed_licenses: Iterable[str] | None = None,
    expected_sbom_count: int | None = None,
    unified_cdx_name: str = "harper-stack-5flagships.cdx.json",
) -> SupplyChainGateReport:
    """Verify every SPDX 2.3 and CycloneDX 1.5 SBOM under pack_dir."""
    if not pack_dir.is_dir():
        r = ("MISSING_PACK_DIR",)
        return SupplyChainGateReport(False, 0, 0, 0, 0, 0, (), r, _seal_pack((), False, r))
    files = discover_sbom_files(pack_dir)
    if not files:
        r = ("EMPTY_SBOM_PACK",)
        return SupplyChainGateReport(False, 0, 0, 0, 0, 0, (), r, _seal_pack((), False, r))
    reasons: list[str] = []
    if expected_sbom_count is not None and len(files) != expected_sbom_count:
        reasons.append(f"SBOM_COUNT_MISMATCH:{len(files)}!={expected_sbom_count}")
    results: list[SbomFileResult] = []
    spdx_count = cdx_count = passed_count = unified_components = 0
    for path in files:
        f_res = _verify_one_sbom(path, pack_dir, forbidden_licenses, allowed_licenses)
        if f_res.fmt == "SPDX-2.3":
            spdx_count += 1
        else:
            cdx_count += 1
            if path.name == unified_cdx_name:
                unified_components = f_res.item_count
        if f_res.passed:
            passed_count += 1
        else:
            reasons.extend(f"{f_res.rel_path}:{x}" for x in f_res.reasons)
        results.append(f_res)
    passed = not reasons and passed_count == len(files)
    seal = _seal_pack(results, passed, reasons)
    return SupplyChainGateReport(
        passed, len(results), passed_count, spdx_count, cdx_count,
        unified_components, tuple(results), tuple(reasons), seal,
    )
