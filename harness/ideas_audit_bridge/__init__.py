# SPDX-License-Identifier: MIT
"""Pure-stdlib Flywheel bridge oracle for AUTHOR_IDEAS_REGISTER parity.

Validates the 18-column ideas register schema, strict integer score bounds,
zero FLAG cells, zero forged catalogue IDs, strict VERIFIED_MATCH vs
UNVERIFIED partitioning, and deterministic ideas_attestation_sha256 sealing.
"""

from __future__ import annotations

from .ideas_oracle import (
    HONEST_SCOPE_LIMIT as ORACLE_HONEST_SCOPE_LIMIT,
)
from .ideas_oracle import (
    IdeasAuditReport,
    verify_ideas_audit,
    verify_ideas_audit_files,
)
from .receipt_parity import (
    HONEST_SCOPE_LIMIT as PARITY_HONEST_SCOPE_LIMIT,
)
from .receipt_parity import (
    ParityPartition,
    ReceiptIndex,
    classify_built_parity,
    compute_match_ratio,
    parse_receipt_index,
    validate_known_catalogue_ids,
    validate_ratio_threshold,
)
from .register_parser import (
    BARE_CID_RE,
    EXPLICIT_CID_RE,
    JSON_NAME_RE,
    LEGAL_STATUSES,
    REQUIRED_IDEAS_COLUMNS,
    IdeaRow,
    extract_citations,
    is_strict_finite_float,
    is_strict_int,
    parse_ideas_register,
    parse_score_1_to_10,
)
from .register_parser import (
    HONEST_SCOPE_LIMIT as PARSER_HONEST_SCOPE_LIMIT,
)

HONEST_SCOPE_LIMIT = (
    "Pure-Python stdlib fail-closed verifier for AUTHOR_IDEAS_REGISTER "
    "18-column schema compliance, strict score and ratio bounds, forged "
    "catalogue ID detection, and VERIFIED_MATCH vs UNVERIFIED partitioning. "
    "Does not invoke external binaries or modify source registers."
)

HONEST_SCOPE_LIMITS: dict[str, str] = {
    "register_parser": PARSER_HONEST_SCOPE_LIMIT,
    "receipt_parity": PARITY_HONEST_SCOPE_LIMIT,
    "ideas_oracle": ORACLE_HONEST_SCOPE_LIMIT,
}

__all__ = [
    "BARE_CID_RE",
    "EXPLICIT_CID_RE",
    "HONEST_SCOPE_LIMIT",
    "HONEST_SCOPE_LIMITS",
    "IdeaRow",
    "IdeasAuditReport",
    "JSON_NAME_RE",
    "LEGAL_STATUSES",
    "ParityPartition",
    "REQUIRED_IDEAS_COLUMNS",
    "ReceiptIndex",
    "classify_built_parity",
    "compute_match_ratio",
    "extract_citations",
    "is_strict_finite_float",
    "is_strict_int",
    "parse_ideas_register",
    "parse_receipt_index",
    "parse_score_1_to_10",
    "validate_known_catalogue_ids",
    "validate_ratio_threshold",
    "verify_ideas_audit",
    "verify_ideas_audit_files",
]
