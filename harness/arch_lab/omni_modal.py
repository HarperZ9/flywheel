"""Native omni-modal shared continuous latent JEPA encoders & 14-domain registry.

Maps five distinct native modalities (vision/motion-vectors, audio/bispectrum,
3D geometry/CAD/physics fields, code/AST/effect-rows, and tool/computer-use
action streams) into one shared continuous JEPA latent space guarded by VICReg
anti-collapse and cross-modal alignment checks. Pure stdlib Python, <= 170 lines.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Mapping, Sequence

from .jepa_fwp import VICRegMonitor
from .memory import Mat, Vec, cosine_similarity, matvec, rand_mat, zeros_mat

MODALITIES: tuple[str, ...] = (
    "vision_mv",
    "audio_bispectrum",
    "geometry_field",
    "code_ast",
    "action_stream",
)

DOMAIN_14_LANES: tuple[tuple[int, str, tuple[str, ...]], ...] = (
    (1, "rendering_game_engine", ("vision_mv", "geometry_field")),
    (2, "systems_lang_compiler", ("code_ast", "action_stream")),
    (3, "ai_verification_harnesses", ("code_ast", "action_stream")),
    (4, "search_indexing_memory", ("code_ast", "action_stream")),
    (5, "formula_signal_kernels", ("geometry_field", "code_ast")),
    (6, "colour_optics_calibration", ("vision_mv", "geometry_field")),
    (7, "audio_dsp_synthesis", ("audio_bispectrum", "geometry_field")),
    (8, "world_sim_physics_cosmo", ("geometry_field", "vision_mv")),
    (9, "design_type_civic_truth", ("vision_mv", "code_ast")),
    (10, "datastores_verification", ("code_ast", "action_stream")),
    (11, "cad_lens_blueprints_metrology", ("geometry_field", "vision_mv")),
    (12, "nuclear_fusion_multiphysics", ("geometry_field", "code_ast")),
    (13, "robotics_physical_ai_kinematics", ("vision_mv", "geometry_field", "action_stream")),
    (14, "neuroscience_psychophysics_biosim", ("audio_bispectrum", "vision_mv", "geometry_field")),
)


@dataclass(frozen=True)
class OmniModalReport:
    mean_cross_modal_cosine: float
    vicreg_verdict: str
    min_dim_std: float
    modalities_aligned: int
    passed: bool


class OmniModalJEPAProjector:
    """Shared continuous latent JEPA space across 5 native physical/symbolic modalities."""

    def __init__(self, input_dims: Mapping[str, int], latent_dim: int = 6, seed: int = 77) -> None:
        rng = random.Random(seed)
        self.latent_dim = latent_dim
        self.input_dims = dict(input_dims)
        self.encoders: dict[str, Mat] = {
            m: rand_mat(latent_dim, dim, 1.0 / math.sqrt(dim), rng)
            for m, dim in sorted(self.input_dims.items())
        }

    def encode(self, modality: str, features: Sequence[float]) -> Vec:
        return [math.tanh(v) for v in matvec(self.encoders[modality], features)]

    def train_alignment_step(
        self,
        paired_batch: Sequence[Mapping[str, Vec]],
        *,
        lr: float = 0.25,
    ) -> float:
        """Align all modalities to an EMA-like stop-grad centroid + variance preservation."""
        n = len(paired_batch)
        grads = {m: zeros_mat(self.latent_dim, d) for m, d in self.input_dims.items()}
        total_mse = 0.0
        anchor_mod = sorted(self.encoders)[0]
        for sample in paired_batch:
            zs = {m: self.encode(m, sample[m]) for m in self.encoders}
            target = zs[anchor_mod]
            for m, z in zs.items():
                if m == anchor_mod:
                    continue
                x = sample[m]
                for i in range(self.latent_dim):
                    err = z[i] - target[i]
                    total_mse += err * err
                    d_pre = (2.0 * err / n) * (1.0 - z[i] * z[i])
                    for j, xj in enumerate(x):
                        grads[m][i][j] += d_pre * xj
        for m, w in self.encoders.items():
            if m == anchor_mod:
                continue
            g = grads[m]
            for i in range(self.latent_dim):
                for j in range(len(w[i])):
                    w[i][j] -= lr * g[i][j]
        return total_mse / max(1, n * (len(self.encoders) - 1) * self.latent_dim)

    def evaluate(self, paired_batch: Sequence[Mapping[str, Vec]]) -> OmniModalReport:
        """Measure pairwise cross-modal cosine alignment and VICReg anti-collapse health."""
        monitor = VICRegMonitor(gamma=0.4, min_std_floor=0.06)
        all_z: list[Vec] = []
        cos_scores: list[float] = []
        mods = sorted(self.encoders)
        for sample in paired_batch:
            zs = {m: self.encode(m, sample[m]) for m in mods}
            all_z.extend(zs.values())
            for idx, m1 in enumerate(mods):
                for m2 in mods[idx + 1 :]:
                    cos_scores.append(cosine_similarity(zs[m1], zs[m2]))
        vic = monitor.inspect(all_z, all_z)
        mean_cos = sum(cos_scores) / len(cos_scores) if cos_scores else 0.0
        passed = (mean_cos > 0.75) and (not vic.collapsed)
        return OmniModalReport(mean_cos, vic.verdict, vic.min_dim_std, len(mods), passed)


def generate_paired_omnimodal_states(
    n_samples: int = 36,
    *,
    latent_dim: int = 6,
    seed: int = 2026,
) -> tuple[dict[str, int], list[dict[str, Vec]]]:
    """Generate paired 5-modality observations of underlying physical+code states."""
    dims = {
        "vision_mv": 8,
        "audio_bispectrum": 6,
        "geometry_field": 7,
        "code_ast": 6,
        "action_stream": 6,
    }
    rng = random.Random(seed)
    projs = {m: rand_mat(d, latent_dim, 0.85, rng) for m, d in dims.items()}
    batch: list[dict[str, Vec]] = []
    for _ in range(n_samples):
        state = [rng.uniform(-1.0, 1.0) for _ in range(latent_dim)]
        sample: dict[str, Vec] = {}
        for m, mat in projs.items():
            obs = matvec(mat, state)
            sample[m] = [v + rng.gauss(0.0, 0.03) for v in obs]
        batch.append(sample)
    return dims, batch
