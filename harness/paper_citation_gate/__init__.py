# SPDX-License-Identifier: MIT
"""Pure-stdlib Flywheel oracle for Technical Papers and Executive Dossiers.

Verifies the 3-Paper Technical Trilogy and Enterprise Dossier against live
catalogue provenance and engine-receipt/1 MATCH verdicts while rejecting forged
catalogue IDs, local path leaks, em/en dashes, and false LLC/Inc claims.
"""

from __future__ import annotations

from .citation_auditor import (
    HONEST_SCOPE_LIMIT as AUDITOR_HONEST_SCOPE_LIMIT,
)
from .citation_auditor import (
    PaperSpec,
    audit_single_paper,
    validate_paper_specs,
)
from .hygiene_scanner import (
    BARE_CID_RE,
    ENTITY_TOKEN_RE,
    EXPLICIT_CID_RE,
    WIN_PATH_RE,
    DocumentHygieneResult,
    canonical_sha256_hex,
    is_strict_finite_float,
    is_strict_int,
    scan_document_hygiene,
)
from .hygiene_scanner import (
    HONEST_SCOPE_LIMIT as SCANNER_HONEST_SCOPE_LIMIT,
)
from .paper_oracle import (
    HONEST_SCOPE_LIMIT as ORACLE_HONEST_SCOPE_LIMIT,
)
from .paper_oracle import (
    PaperCitationReport,
    verify_paper_bundle,
    verify_paper_bundle_files,
)

HONEST_SCOPE_LIMIT = (
    "Pure-Python stdlib fail-closed verifier for technical papers and "
    "dossiers (catalogue ID provenance, receipt MATCH proofs, zero local "
    "path leaks, zero em/en dashes, and zero affirmative LLC/Inc claims). "
    "Does not render or parse PDF binary layouts."
)

HONEST_SCOPE_LIMITS: dict[str, str] = {
    "hygiene_scanner": SCANNER_HONEST_SCOPE_LIMIT,
    "citation_auditor": AUDITOR_HONEST_SCOPE_LIMIT,
    "paper_oracle": ORACLE_HONEST_SCOPE_LIMIT,
}

__all__ = [
    "BARE_CID_RE",
    "DocumentHygieneResult",
    "ENTITY_TOKEN_RE",
    "EXPLICIT_CID_RE",
    "HONEST_SCOPE_LIMIT",
    "HONEST_SCOPE_LIMITS",
    "PaperCitationReport",
    "PaperSpec",
    "WIN_PATH_RE",
    "audit_single_paper",
    "canonical_sha256_hex",
    "is_strict_finite_float",
    "is_strict_int",
    "scan_document_hygiene",
    "validate_paper_specs",
    "verify_paper_bundle",
    "verify_paper_bundle_files",
]
