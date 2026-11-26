"""JFC-3P Stage-1 Curation, Model-Carving/mHC, NOH-3/NOH-4, Colab/RTX 4090 Forge, Arm C, v2 KL & Wave 15 Ablations.

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
from .fresco_molt_bridge import (
    FRESCOOrthogonalProjector,
    KVEntry,
    MoLTCrossLoopKVCache,
    PlatoKeyLatentCodec,
    fused_single_pass_loopcd,
    run_ablation_a5_fresco_molt,
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
from .noh4_living_world import (
    NOH4LivingWorldOrganism,
    ReseatingCODITValve,
    ValveEvent,
    evaluate_noh4_vs_noh3_vs_flat,
)
from .rtx4090_armc_eval import (
    eval_safe_f64_expr,
    evaluate_armc_holdout,
    execute_f64_oracle_call,
    extract_armc_tool_calls,
    make_buildc_runner,
    make_openai_http_client,
    score_holdout_item,
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
from .v2_reverse_kl_trainer import (
    DEFAULT_V2_REPLAY_RATIOS,
    LONGPPL_BASE_FLOOR,
    V2_DEFAULT_BETA_KL,
    V2RegressionGuard,
    V2ReverseKLResult,
    build_v2_training_spec,
    compute_v2_reverse_kl_loss,
    format_avtr_sample,
    rebalance_domain_mix,
    validate_v2_regression_guard,
)
from .wave15_colab_ablation import (
    AVTR4RouteController,
    MetamerPair,
    MetamerSplitRewardScorer,
    PlatoKeyProcrustesBridge,
    one_pass_online_reverse_kl,
    run_ablation_a1_metamer_rlvb_armc,
    run_ablation_a3_plato_key,
    run_ablation_a4_avtr_4r,
    run_wave15_colab_ablations,
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
    "ValveEvent", "ReseatingCODITValve", "NOH4LivingWorldOrganism", "evaluate_noh4_vs_noh3_vs_flat",
    "BaseModelSpec", "APACHE2_BASE_MODELS", "TIER_A_TRAIN_SOURCES",
    "adapt_colab_gpu_profile", "build_oracle_training_mix", "build_rtx4090_serving_spec",
    "evaluate_oracle_verifiable_suite", "run_rtx4090_forge",
    "eval_safe_f64_expr", "execute_f64_oracle_call", "extract_armc_tool_calls",
    "score_holdout_item", "make_openai_http_client", "make_buildc_runner", "evaluate_armc_holdout",
    "DEFAULT_V2_REPLAY_RATIOS", "LONGPPL_BASE_FLOOR", "V2_DEFAULT_BETA_KL",
    "V2ReverseKLResult", "V2RegressionGuard", "compute_v2_reverse_kl_loss",
    "rebalance_domain_mix", "validate_v2_regression_guard", "format_avtr_sample", "build_v2_training_spec",
    "MetamerPair", "MetamerSplitRewardScorer", "PlatoKeyProcrustesBridge", "AVTR4RouteController",
    "one_pass_online_reverse_kl", "run_ablation_a1_metamer_rlvb_armc", "run_ablation_a3_plato_key",
    "run_ablation_a4_avtr_4r", "run_wave15_colab_ablations",
    "FRESCOOrthogonalProjector", "KVEntry", "MoLTCrossLoopKVCache", "PlatoKeyLatentCodec",
    "fused_single_pass_loopcd", "run_ablation_a5_fresco_molt",
]
