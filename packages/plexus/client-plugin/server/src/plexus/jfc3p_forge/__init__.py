"""JFC-3P Stage-1 Data Curation, Model-Carving/Loom-mHC, NOH-3 Living World, and Colab/RTX 4090 Forge.

Pure Python 3.11+ stdlib package with zero runtime dependencies.
"""
from .colab_h100_runner import (
    ENGINE_RECEIPT_SCHEMA,
    benchmark_151k_reverse_kl,
    build_forge_receipt,
    chunked_exact_reverse_kl,
    dense_exact_reverse_kl,
    run_colab_forge_pipeline,
    verify_forge_receipt,
)
from .model_carving_arch import (
    BuildLangOracleHead,
    CarvedSublayerGate,
    CarvingHealthReport,
    JFC3PCarvedModel,
    LoomMHCRouter,
    OracleCheckResult,
    compute_capacity_bit_transfer,
    sinkhorn_knopp,
    validate_carving_health,
)
from .noh3_living_world import (
    ENV_NAMES,
    ORGANELLE_NAMES,
    BuckinghamPiNormalizer,
    CODITImmuneOrgan,
    CausticTickGate,
    ImmuneEvent,
    NOH3LivingWorldOrganism,
    evaluate_noh3_suite,
)
from .rtx4090_model_forge import (
    APACHE2_BASE_MODELS,
    TIER_A_TRAIN_SOURCES,
    BaseModelSpec,
    adapt_colab_gpu_profile,
    build_oracle_training_mix,
    build_rtx4090_serving_spec,
    evaluate_oracle_verifiable_suite,
    run_rtx4090_forge,
)
from .stage1_curator import (
    FROZEN_DS_HOLDOUTS,
    LANE_14_SPECS,
    TIER_A_LICENSES,
    ContaminationIndex,
    ContaminationMatch,
    CurationSummary,
    LaneSpec,
    LaneStats,
    LicenseDecision,
    ReadinessReport,
    check_license_firewall,
    curate_records,
    evaluate_readiness,
    extract_13grams,
    normalize_tokens,
)

__all__ = [
    "TIER_A_LICENSES", "LANE_14_SPECS", "FROZEN_DS_HOLDOUTS",
    "LicenseDecision", "ContaminationMatch", "ContaminationIndex",
    "LaneSpec", "LaneStats", "CurationSummary", "ReadinessReport",
    "check_license_firewall", "normalize_tokens", "extract_13grams",
    "curate_records", "evaluate_readiness",
    "CarvedSublayerGate", "CarvingHealthReport", "LoomMHCRouter",
    "OracleCheckResult", "BuildLangOracleHead", "JFC3PCarvedModel",
    "sinkhorn_knopp", "validate_carving_health", "compute_capacity_bit_transfer",
    "ENGINE_RECEIPT_SCHEMA", "dense_exact_reverse_kl", "chunked_exact_reverse_kl",
    "benchmark_151k_reverse_kl", "build_forge_receipt", "verify_forge_receipt",
    "run_colab_forge_pipeline",
    "ORGANELLE_NAMES", "ENV_NAMES", "ImmuneEvent", "BuckinghamPiNormalizer",
    "CausticTickGate", "CODITImmuneOrgan", "NOH3LivingWorldOrganism", "evaluate_noh3_suite",
    "BaseModelSpec", "APACHE2_BASE_MODELS", "TIER_A_TRAIN_SOURCES",
    "adapt_colab_gpu_profile", "build_oracle_training_mix", "build_rtx4090_serving_spec",
    "evaluate_oracle_verifiable_suite", "run_rtx4090_forge",
]
