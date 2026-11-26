"""JFC-3P: Latent JEPA + Fast-Weight Delta Memory + Three-Plate Verifiable RL.

Stdlib-only CPU-verifiable research laboratory inside Flywheel combining:
- Latent JEPA with looped mHC residual core and VICReg anti-collapse monitor.
- Decoupled Fast-Weight Delta Memory (Schmidhuber FWP + Gated DeltaNet-2).
- Compression-Progress curiosity + PowerPlay curriculum gated by the
  Three-Plate Verifiable RL Oracle over DS-03 physics and DS-02 BuildLang tasks.
"""
from __future__ import annotations

from .jepa_fwp import (
    FastWeightDeltaMemory,
    LatentJEPAFastWeightModel,
    StaticMemoryBaseline,
    VICRegMonitor,
    VICRegReport,
    compute_vicreg_loss,
    cosine_similarity,
    generate_rotational_dynamics,
    sinkhorn_doubly_stochastic,
)
from .omni_modal import (
    DOMAIN_14_LANES,
    MODALITIES,
    OmniModalJEPAProjector,
    OmniModalReport,
    generate_paired_omnimodal_states,
)
from .frontier_ladder import LadderRungResult, eval_frontier_ladder, eval_rung_l0
from .quant_speculative import (
    BitNetQuantizedMatrix,
    Eagle3SpeculativeVerifier,
    Int4QuantizedMatrix,
    QuantizationMetrics,
    SpeculativeDecodeReport,
    bitnet_matvec,
    dequantize_bitnet_158,
    dequantize_int4_groupwise,
    int4_matvec,
    quantize_bitnet_158,
    quantize_int4_groupwise,
)
from .verifiable_rl import (
    CompressionProgressTracker,
    EpisodeMetrics,
    PowerPlayCurriculum,
    RLTask,
    TaskSubmission,
    ThreePlateStepVerdict,
    ThreePlateVerifiableRLEnv,
    load_ds02_buildlang_tasks,
    load_ds03_physics_tasks,
)

__all__ = [
    "BitNetQuantizedMatrix",
    "CompressionProgressTracker",
    "DOMAIN_14_LANES",
    "Eagle3SpeculativeVerifier",
    "EpisodeMetrics",
    "FastWeightDeltaMemory",
    "Int4QuantizedMatrix",
    "LadderRungResult",
    "LatentJEPAFastWeightModel",
    "MODALITIES",
    "OmniModalJEPAProjector",
    "OmniModalReport",
    "PowerPlayCurriculum",
    "QuantizationMetrics",
    "RLTask",
    "SpeculativeDecodeReport",
    "StaticMemoryBaseline",
    "TaskSubmission",
    "ThreePlateStepVerdict",
    "ThreePlateVerifiableRLEnv",
    "VICRegMonitor",
    "VICRegReport",
    "bitnet_matvec",
    "compute_vicreg_loss",
    "cosine_similarity",
    "dequantize_bitnet_158",
    "dequantize_int4_groupwise",
    "eval_frontier_ladder",
    "eval_rung_l0",
    "generate_paired_omnimodal_states",
    "generate_rotational_dynamics",
    "int4_matvec",
    "load_ds02_buildlang_tasks",
    "load_ds03_physics_tasks",
    "quantize_bitnet_158",
    "quantize_int4_groupwise",
    "sinkhorn_doubly_stochastic",
]
