# SPDX-License-Identifier: MIT
"""Pure-stdlib Flywheel oracle for C++23 <-> BuildLang 0-ULP renderer parity.

Verifies native/bld/ renderer parity receipts (#12..#24+), 64-bit FNV-1a
IEEE-754 hash pins, planted perturbation rejections, and deterministic
renderer_parity_attestation_sha256 sealing.
"""

from __future__ import annotations

from .parity_oracle import (
    HONEST_SCOPE_LIMIT as ORACLE_HONEST_SCOPE_LIMIT,
)
from .parity_oracle import (
    RendererParityReport,
    verify_renderer_parity,
    verify_renderer_parity_files,
)
from .parity_parser import (
    HONEST_SCOPE_LIMIT as PARSER_HONEST_SCOPE_LIMIT,
)
from .parity_parser import (
    REQUIRED_PARITY_COLUMNS,
    RendererParityRow,
    parse_renderer_parity_tsv,
)
from .pin_guards import (
    FNV1A_64_RE,
    canonical_sha256_hex,
    is_strict_finite_float,
    is_strict_int,
    normalize_fnv1a_pin,
    parse_strict_flag_01,
    parse_strict_positive_int,
    parse_strict_ulp,
)
from .pin_guards import (
    HONEST_SCOPE_LIMIT as GUARDS_HONEST_SCOPE_LIMIT,
)

HONEST_SCOPE_LIMIT = (
    "Pure-Python stdlib fail-closed verifier for C++23 <-> BuildLang 0-ULP "
    "renderer parity receipts, FNV-1a IEEE-754 pins, planted perturbation "
    "controls, and caller-supplied catalogue provenance. Does not compile "
    "C++23 or BuildLang sources."
)

HONEST_SCOPE_LIMITS: dict[str, str] = {
    "pin_guards": GUARDS_HONEST_SCOPE_LIMIT,
    "parity_parser": PARSER_HONEST_SCOPE_LIMIT,
    "parity_oracle": ORACLE_HONEST_SCOPE_LIMIT,
}

__all__ = [
    "FNV1A_64_RE",
    "HONEST_SCOPE_LIMIT",
    "HONEST_SCOPE_LIMITS",
    "REQUIRED_PARITY_COLUMNS",
    "RendererParityReport",
    "RendererParityRow",
    "canonical_sha256_hex",
    "is_strict_finite_float",
    "is_strict_int",
    "normalize_fnv1a_pin",
    "parse_renderer_parity_tsv",
    "parse_strict_flag_01",
    "parse_strict_positive_int",
    "parse_strict_ulp",
    "verify_renderer_parity",
    "verify_renderer_parity_files",
]
