# SPDX-License-Identifier: MIT
"""Pure-stdlib Flywheel verifier for Zero-C 5-ISA BuildOS slices (17..24).

Verifies 5-ISA completeness (x64-pe, x64-elf, rv64-elf, aarch64-elf, wasm),
zero-C compilation flags, planted security attack rejections, catalogue
provenance, on-disk binary hashes, and zero_c_os_attestation_sha256 sealing.
"""

from __future__ import annotations

from .isa_guards import (
    HONEST_SCOPE_LIMIT as GUARDS_HONEST_SCOPE_LIMIT,
)
from .isa_guards import (
    REQUIRED_ISAS,
    REQUIRED_SLICE_COLUMNS,
    SHA256_HEX_RE,
    canonical_sha256_hex,
    is_strict_finite_float,
    is_strict_int,
    normalize_sha256,
    parse_strict_nonneg_int,
    parse_strict_positive_int,
    validate_binary_magic,
)
from .os_oracle import (
    HONEST_SCOPE_LIMIT as ORACLE_HONEST_SCOPE_LIMIT,
)
from .os_oracle import (
    ZeroCOSReport,
    hash_binary_file,
    verify_zero_c_os,
    verify_zero_c_os_tsv,
)
from .slice_parser import (
    HONEST_SCOPE_LIMIT as PARSER_HONEST_SCOPE_LIMIT,
)
from .slice_parser import (
    ZeroCSliceBinary,
    extract_slice_binaries_from_receipt,
    infer_isa_from_rel_path,
    parse_slices_index_tsv,
)

HONEST_SCOPE_LIMIT = (
    "Pure-Python stdlib fail-closed verifier for Zero-C 5-ISA BuildOS slices "
    "(Slices 17..24), binary magic/SHA-256 parity, attack rejection floors, "
    "and caller-supplied catalogue provenance. Does not execute BuildOS "
    "binaries or emulate CPU architectures."
)

HONEST_SCOPE_LIMITS: dict[str, str] = {
    "isa_guards": GUARDS_HONEST_SCOPE_LIMIT,
    "slice_parser": PARSER_HONEST_SCOPE_LIMIT,
    "os_oracle": ORACLE_HONEST_SCOPE_LIMIT,
}

__all__ = [
    "HONEST_SCOPE_LIMIT",
    "HONEST_SCOPE_LIMITS",
    "REQUIRED_ISAS",
    "REQUIRED_SLICE_COLUMNS",
    "SHA256_HEX_RE",
    "ZeroCOSReport",
    "ZeroCSliceBinary",
    "canonical_sha256_hex",
    "extract_slice_binaries_from_receipt",
    "hash_binary_file",
    "infer_isa_from_rel_path",
    "is_strict_finite_float",
    "is_strict_int",
    "normalize_sha256",
    "parse_slices_index_tsv",
    "parse_strict_nonneg_int",
    "parse_strict_positive_int",
    "validate_binary_magic",
    "verify_zero_c_os",
    "verify_zero_c_os_tsv",
]
