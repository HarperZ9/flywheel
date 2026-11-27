# SPDX-License-Identifier: MIT
"""Pure-stdlib SPDX 2.3 and CycloneDX 1.5 supply-chain policy verifier.

Provides fail-closed validation of SPDX 2.3 and CycloneDX 1.5 SBOM JSON
documents, SPDX license expression and denylist/allowlist checks, zero-PII
and zero-local-path leak scanning, and deterministic pack attestation.
"""

from __future__ import annotations

from .cyclonedx_check import (
    CYCLONEDX_FORMAT,
    CYCLONEDX_SPEC_VERSION,
    CycloneDxAuditReport,
    verify_cyclonedx_doc,
    verify_cyclonedx_file,
)
from .cyclonedx_check import (
    HONEST_SCOPE_LIMIT as CYCLONEDX_HONEST_SCOPE_LIMIT,
)
from .spdx_check import (
    DEFAULT_FORBIDDEN_LICENSES,
    SPDX_DATA_LICENSE,
    SPDX_DOCUMENT_ID,
    SPDX_VERSION,
    SpdxAuditReport,
    check_license_policy,
    extract_license_tokens,
    is_valid_spdx_expression,
    scan_pii_and_paths,
    verify_spdx_doc,
    verify_spdx_file,
)
from .spdx_check import (
    HONEST_SCOPE_LIMIT as SPDX_HONEST_SCOPE_LIMIT,
)
from .supply_chain_gate import (
    HONEST_SCOPE_LIMIT as GATE_HONEST_SCOPE_LIMIT,
)
from .supply_chain_gate import (
    SbomFileResult,
    SupplyChainGateReport,
    discover_sbom_files,
    verify_sbom_pack,
)

HONEST_SCOPE_LIMIT = (
    "Pure-Python stdlib static validator for SPDX 2.3 and CycloneDX 1.5 SBOM "
    "JSON packs, license policies, and zero-PII/local-path hygiene. Does not "
    "generate SBOMs from build graphs, verify detached signatures, or query "
    "external vulnerability databases."
)

HONEST_SCOPE_LIMITS: dict[str, str] = {
    "spdx_check": SPDX_HONEST_SCOPE_LIMIT,
    "cyclonedx_check": CYCLONEDX_HONEST_SCOPE_LIMIT,
    "supply_chain_gate": GATE_HONEST_SCOPE_LIMIT,
}

__all__ = [
    "CYCLONEDX_FORMAT",
    "CYCLONEDX_SPEC_VERSION",
    "CycloneDxAuditReport",
    "DEFAULT_FORBIDDEN_LICENSES",
    "HONEST_SCOPE_LIMIT",
    "HONEST_SCOPE_LIMITS",
    "SPDX_DATA_LICENSE",
    "SPDX_DOCUMENT_ID",
    "SPDX_VERSION",
    "SbomFileResult",
    "SpdxAuditReport",
    "SupplyChainGateReport",
    "check_license_policy",
    "discover_sbom_files",
    "extract_license_tokens",
    "is_valid_spdx_expression",
    "scan_pii_and_paths",
    "verify_cyclonedx_doc",
    "verify_cyclonedx_file",
    "verify_sbom_pack",
    "verify_spdx_doc",
    "verify_spdx_file",
]
