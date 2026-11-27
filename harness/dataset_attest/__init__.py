# SPDX-License-Identifier: MIT
"""Pure-stdlib Flywheel oracle for BuildDB Parquet V5 and JFC3P RLVR v8 packs.

Verifies zero non-MIT rows, zero duplicate IDs, exact train/eval split
disjointness, 100% oracle pass-rate floor, strict SHA-256 and IEEE-754 finite
guards, and deterministic dataset_attestation_sha256 sealing.
"""

from __future__ import annotations

from .dataset_guards import (
    HONEST_SCOPE_LIMIT as GUARDS_HONEST_SCOPE_LIMIT,
)
from .dataset_guards import (
    SHA256_HEX_RE,
    canonical_sha256_hex,
    is_mit_license,
    is_strict_finite_float,
    is_strict_int,
    normalize_sha256,
    validate_pass_rate,
    verify_manifest_artifacts,
)
from .dataset_oracle import (
    HONEST_SCOPE_LIMIT as ORACLE_HONEST_SCOPE_LIMIT,
)
from .dataset_oracle import (
    DatasetAttestReport,
    verify_dataset_pack,
    verify_dataset_pack_files,
)
from .jsonl_auditor import (
    HONEST_SCOPE_LIMIT as AUDITOR_HONEST_SCOPE_LIMIT,
)
from .jsonl_auditor import (
    JsonlAuditStats,
    audit_builddb_jsonl,
    audit_rlvr_split_jsonl,
)

HONEST_SCOPE_LIMIT = (
    "Pure-Python stdlib fail-closed verifier for BuildDB Parquet V5 and "
    "JFC3P RLVR v8 manifests and JSONL splits (MIT purity, ID uniqueness, "
    "train/eval disjointness, artifact SHA-256, and finite pass-rate floor). "
    "Does not run model training or parse binary Parquet pages."
)

HONEST_SCOPE_LIMITS: dict[str, str] = {
    "dataset_guards": GUARDS_HONEST_SCOPE_LIMIT,
    "jsonl_auditor": AUDITOR_HONEST_SCOPE_LIMIT,
    "dataset_oracle": ORACLE_HONEST_SCOPE_LIMIT,
}

__all__ = [
    "DatasetAttestReport",
    "HONEST_SCOPE_LIMIT",
    "HONEST_SCOPE_LIMITS",
    "JsonlAuditStats",
    "SHA256_HEX_RE",
    "audit_builddb_jsonl",
    "audit_rlvr_split_jsonl",
    "canonical_sha256_hex",
    "is_mit_license",
    "is_strict_finite_float",
    "is_strict_int",
    "normalize_sha256",
    "validate_pass_rate",
    "verify_dataset_pack",
    "verify_dataset_pack_files",
    "verify_manifest_artifacts",
]
