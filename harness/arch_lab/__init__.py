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
    "CompressionProgressTracker",
    "DOMAIN_14_LANES",
    "EpisodeMetrics",
    "FastWeightDeltaMemory",
    "LatentJEPAFastWeightModel",
    "MODALITIES",
    "OmniModalJEPAProjector",
    "OmniModalReport",
    "PowerPlayCurriculum",
    "RLTask",
    "StaticMemoryBaseline",
    "TaskSubmission",
    "ThreePlateStepVerdict",
    "ThreePlateVerifiableRLEnv",
    "VICRegMonitor",
    "VICRegReport",
    "compute_vicreg_loss",
    "cosine_similarity",
    "generate_paired_omnimodal_states",
    "generate_rotational_dynamics",
    "load_ds02_buildlang_tasks",
    "load_ds03_physics_tasks",
    "sinkhorn_doubly_stochastic",
]
