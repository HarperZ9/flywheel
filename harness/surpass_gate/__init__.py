# SPDX-License-Identifier: MIT
"""Pure-stdlib Flywheel oracle for the 76-row Competitive Surpass Matrix.

Verifies exact 1-to-1 partition between COMMONS_COMPETITIVE_SIGNALS.tsv and
the competitive surpass matrix JSON, CS-001..CS-076 completeness, raw TSV
SHA-256 integrity, live catalogue provenance, and deterministic
surpass_attestation_sha256 sealing.
"""

from __future__ import annotations

from .matrix_parser import (
    HONEST_SCOPE_LIMIT as PARSER_HONEST_SCOPE_LIMIT,
)
from .matrix_parser import (
    LEGAL_TIERS,
    REQUIRED_TSV_COLUMNS,
    MatrixSignalRecord,
    SignalTsvRecord,
    parse_matrix_signals,
    parse_signals_tsv,
    validate_summary_block,
)
from .numeric_guards import (
    HONEST_SCOPE_LIMIT as GUARDS_HONEST_SCOPE_LIMIT,
)
from .numeric_guards import (
    canonical_sha256_hex,
    is_strict_finite_float,
    is_strict_int,
    parse_strict_positive_int,
    sha256_bytes_hex,
    validate_catalogue_id_list,
    validate_percentage,
)
from .surpass_oracle import (
    HONEST_SCOPE_LIMIT as ORACLE_HONEST_SCOPE_LIMIT,
)
from .surpass_oracle import (
    SurpassGateReport,
    verify_surpass_matrix,
    verify_surpass_matrix_files,
)

HONEST_SCOPE_LIMIT = (
    "Pure-Python stdlib fail-closed verifier for the Competitive Surpass "
    "Matrix TSV/JSON 1-to-1 partition, CS-001..CS-076 completeness, strict "
    "IEEE-754 finite metrics, and caller-supplied catalogue provenance. Does "
    "not re-execute underlying compiler or GPU benchmark binaries."
)

HONEST_SCOPE_LIMITS: dict[str, str] = {
    "numeric_guards": GUARDS_HONEST_SCOPE_LIMIT,
    "matrix_parser": PARSER_HONEST_SCOPE_LIMIT,
    "surpass_oracle": ORACLE_HONEST_SCOPE_LIMIT,
}

__all__ = [
    "HONEST_SCOPE_LIMIT",
    "HONEST_SCOPE_LIMITS",
    "LEGAL_TIERS",
    "MatrixSignalRecord",
    "REQUIRED_TSV_COLUMNS",
    "SignalTsvRecord",
    "SurpassGateReport",
    "canonical_sha256_hex",
    "is_strict_finite_float",
    "is_strict_int",
    "parse_matrix_signals",
    "parse_signals_tsv",
    "parse_strict_positive_int",
    "sha256_bytes_hex",
    "validate_catalogue_id_list",
    "validate_percentage",
    "validate_summary_block",
    "verify_surpass_matrix",
    "verify_surpass_matrix_files",
]
