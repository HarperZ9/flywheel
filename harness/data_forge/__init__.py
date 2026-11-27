"""Proof-Carrying Data Forge: 6-stage fail-closed dataset synthesis and sealing engine."""

from __future__ import annotations

from .adapters import (
    DOMAIN_ADAPTERS,
    HIPAA_RESTRICTED_ZIP3,
    SI_UNIT_DIMS,
    DomainAdapter,
    MedicalHipaaSafeHarborAdapter,
    ScientificPhysicsSensorAdapter,
    assign_patient_level_split,
    run_domain_adapter,
    stage1_provenance_firewall,
    verify_zero_patient_bleed,
)
from .common import (
    ALLOWED_LICENSES,
    DENIED_LICENSES,
    DISALLOWED_COLLECTION_MODES,
    FLYWHEEL_MODULES_LINKED,
    SCHEMA_CARD,
    SCHEMA_MERKLE,
    canonical_json_bytes,
    extract_code_snippet,
    extract_row_text,
    normalize_text,
    normalized_ast_hash,
    word_tokens,
)
from .dedup_and_holdout import (
    HoldoutDecontaminator,
    ThreeTierDeduplicator,
    compute_minhash8,
    compute_simhash64,
)
from .oracles import (
    BUILTIN_SFTS_RECORDS,
    synthesize_oracle_verified_rows,
    synthesize_search_from_the_start_rows,
    validate_oracle_candidate,
)
from .pipeline import iter_raw_jsonl, main, run_data_forge
from .scoring_and_seal import (
    build_merkle_and_seal,
    score_entropy_and_difficulty,
    score_subjective_slop_density,
    verify_sealed_dataset,
)

__all__ = [
    "ALLOWED_LICENSES",
    "BUILTIN_SFTS_RECORDS",
    "DENIED_LICENSES",
    "DISALLOWED_COLLECTION_MODES",
    "DOMAIN_ADAPTERS",
    "FLYWHEEL_MODULES_LINKED",
    "HIPAA_RESTRICTED_ZIP3",
    "SCHEMA_CARD",
    "SCHEMA_MERKLE",
    "SI_UNIT_DIMS",
    "DomainAdapter",
    "HoldoutDecontaminator",
    "MedicalHipaaSafeHarborAdapter",
    "ScientificPhysicsSensorAdapter",
    "ThreeTierDeduplicator",
    "assign_patient_level_split",
    "build_merkle_and_seal",
    "canonical_json_bytes",
    "compute_minhash8",
    "compute_simhash64",
    "extract_code_snippet",
    "extract_row_text",
    "iter_raw_jsonl",
    "main",
    "normalize_text",
    "normalized_ast_hash",
    "run_data_forge",
    "run_domain_adapter",
    "score_entropy_and_difficulty",
    "score_subjective_slop_density",
    "stage1_provenance_firewall",
    "synthesize_oracle_verified_rows",
    "synthesize_search_from_the_start_rows",
    "validate_oracle_candidate",
    "verify_sealed_dataset",
    "verify_zero_patient_bleed",
    "word_tokens",
]
