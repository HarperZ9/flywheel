"""Latent JEPA Predictor + VICReg Anti-Collapse Monitor with exact looped backprop.

Pure stdlib Python, CPU-only, <= 240 lines, every function <= 50 lines.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Sequence

from .memory import (
    FastWeightDeltaMemory,
    Mat,
    StaticMemoryBaseline,
    Vec,
    cosine_similarity,
    matvec,
    rand_mat,
    sinkhorn_doubly_stochastic,
    zeros,
    zeros_mat,
)

__all__ = [
    "FastWeightDeltaMemory",
    "LatentJEPAFastWeightModel",
    "StaticMemoryBaseline",
    "VICRegMonitor",
    "VICRegReport",
    "compute_vicreg_loss",
    "cosine_similarity",
    "generate_rotational_dynamics",
    "sinkhorn_doubly_stochastic",
]


@dataclass(frozen=True)
class VICRegReport:
    invariance_loss: float
    variance_loss: float
    covariance_loss: float
    total_loss: float
    min_dim_std: float
    mean_dim_std: float
    collapsed: bool
    verdict: str


def compute_vicreg_loss(
    preds: Sequence[Vec],
    targets: Sequence[Vec],
    *,
    gamma: float = 0.5,
    sim_weight: float = 25.0,
    var_weight: float = 25.0,
    cov_weight: float = 1.0,
    eps: float = 1e-6,
) -> VICRegReport:
    """Compute Variance-Invariance-Covariance loss and collapse diagnostic."""
    n = len(preds)
    d = len(preds[0]) if n else 0
    if n < 2 or d == 0:
        raise ValueError("need at least 2 non-empty latent vectors")
    inv = sum((p[j] - t[j]) ** 2 for p, t in zip(preds, targets) for j in range(d)) / (n * d)
    means = [sum(p[j] for p in preds) / n for j in range(d)]
    centered = [[p[j] - means[j] for j in range(d)] for p in preds]
    stds = [math.sqrt(sum(c[j] * c[j] for c in centered) / n + eps) for j in range(d)]
    var_loss = sum(max(0.0, gamma - s) for s in stds) / d
    cov_sum = 0.0
    for j in range(d):
        for k in range(d):
            if j != k:
                c_jk = sum(c[j] * c[k] for c in centered) / (n - 1)
                cov_sum += c_jk * c_jk
    cov_loss = cov_sum / d
    total = sim_weight * inv + var_weight * var_loss + cov_weight * cov_loss
    min_std, mean_std = min(stds), sum(stds) / d
    collapsed = (min_std < 0.1 * gamma) or (mean_std < 0.25 * gamma)
    return VICRegReport(inv, var_loss, cov_loss, total, min_std, mean_std, collapsed,
                        "REJECT" if collapsed else "HEALTHY")


class VICRegMonitor:
    """Gate that rejects collapsed constant or rank-deficient latent encoders."""

    def __init__(self, *, gamma: float = 0.5, min_std_floor: float = 0.08) -> None:
        self.gamma = gamma
        self.min_std_floor = min_std_floor

    def inspect(self, preds: Sequence[Vec], targets: Sequence[Vec]) -> VICRegReport:
        rep = compute_vicreg_loss(preds, targets, gamma=self.gamma)
        is_collapsed = rep.collapsed or (rep.min_dim_std < self.min_std_floor)
        return VICRegReport(
            rep.invariance_loss, rep.variance_loss, rep.covariance_loss, rep.total_loss,
            rep.min_dim_std, rep.mean_dim_std, is_collapsed,
            "REJECT" if is_collapsed else "HEALTHY",
        )


class LatentJEPAFastWeightModel:
    """Latent JEPA with Inkling-2 looped mHC predictor and fast-weight context."""

    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        latent_dim: int = 6,
        *,
        loop_steps: int = 2,
        ema_momentum: float = 0.96,
        seed: int = 42,
    ) -> None:
        rng = random.Random(seed)
        self.obs_dim, self.action_dim, self.latent_dim = obs_dim, action_dim, latent_dim
        self.loop_steps = loop_steps
        self.ema_momentum = ema_momentum
        self.step_scale = 0.5
        self.w_enc = rand_mat(latent_dim, obs_dim, 1.0 / math.sqrt(obs_dim), rng)
        self.w_tgt = [row[:] for row in self.w_enc]
        s_pred = 0.25 / math.sqrt(latent_dim)
        self.w_state = rand_mat(latent_dim, latent_dim, s_pred, rng)
        self.w_act = rand_mat(latent_dim, action_dim, s_pred, rng)
        self.b_pred = zeros(latent_dim)
        self.mhc_mix = sinkhorn_doubly_stochastic([[2.5, 0.0], [0.0, 2.5]])
        self.fast_memory = FastWeightDeltaMemory(latent_dim, latent_dim, erase_rate=0.5, write_rate=0.5, decay=0.1)

    def encode_online(self, obs: Sequence[float]) -> Vec:
        return [math.tanh(v) for v in matvec(self.w_enc, obs)]

    def encode_target(self, obs: Sequence[float]) -> Vec:
        return [math.tanh(v) for v in matvec(self.w_tgt, obs)]

    def _forward_trace(self, z_t: Sequence[float], action: Sequence[float]) -> tuple[Vec, list[tuple[Vec, Vec]]]:
        cur = list(z_t)
        mem = self.fast_memory.read(z_t)
        a_proj = matvec(self.w_act, action)
        w_self, w_mem = self.mhc_mix[0][0], self.mhc_mix[0][1]
        trace: list[tuple[Vec, Vec]] = []
        for _ in range(self.loop_steps):
            s_proj = matvec(self.w_state, cur)
            h = [math.tanh(s_proj[i] + a_proj[i] + self.b_pred[i]) for i in range(self.latent_dim)]
            trace.append((cur[:], h))
            cur = [w_self * cur[i] + w_mem * mem[i] + self.step_scale * h[i] for i in range(self.latent_dim)]
        return cur, trace

    def predict_next_latent(self, z_t: Sequence[float], action: Sequence[float]) -> Vec:
        pred, _ = self._forward_trace(z_t, action)
        return pred

    def train_step(
        self,
        batch: Sequence[tuple[Vec, Vec, Vec]],
        *,
        lr: float = 0.35,
        var_weight: float = 0.08,
        gamma: float = 0.45,
    ) -> VICRegReport:
        """Exact analytical backprop through looped JEPA predictor + variance guard."""
        preds, targets = [], []
        g_ws = zeros_mat(self.latent_dim, self.latent_dim)
        g_wa = zeros_mat(self.latent_dim, self.action_dim)
        g_bp = zeros(self.latent_dim)
        n = len(batch)
        w_self = self.mhc_mix[0][0]
        for obs_t, act_t, obs_next in batch:
            z_t, z_tgt = self.encode_online(obs_t), self.encode_target(obs_next)
            z_hat, trace = self._forward_trace(z_t, act_t)
            preds.append(z_hat)
            targets.append(z_tgt)
            grad = [2.0 * (z_hat[i] - z_tgt[i]) / (n * self.latent_dim) for i in range(self.latent_dim)]
            for cur_in, h in reversed(trace):
                d_pre = [grad[i] * self.step_scale * (1.0 - h[i] * h[i]) for i in range(self.latent_dim)]
                for i in range(self.latent_dim):
                    g_bp[i] += d_pre[i]
                    for j in range(self.latent_dim):
                        g_ws[i][j] += d_pre[i] * cur_in[j]
                    for k in range(self.action_dim):
                        g_wa[i][k] += d_pre[i] * act_t[k]
                grad = [
                    w_self * grad[j] + sum(self.w_state[i][j] * d_pre[i] for i in range(self.latent_dim))
                    for j in range(self.latent_dim)
                ]
        self._apply_updates(g_ws, g_wa, g_bp, preds, lr, var_weight, gamma)
        return compute_vicreg_loss(preds, targets, gamma=gamma)

    def _apply_updates(
        self, g_ws: Mat, g_wa: Mat, g_bp: Vec, preds: Sequence[Vec],
        lr: float, var_weight: float, gamma: float,
    ) -> None:
        for i in range(self.latent_dim):
            self.b_pred[i] -= lr * g_bp[i]
            for j in range(self.latent_dim):
                self.w_state[i][j] -= lr * g_ws[i][j]
            for k in range(self.action_dim):
                self.w_act[i][k] -= lr * g_wa[i][k]
        n = len(preds)
        for i in range(self.latent_dim):
            mean_i = sum(p[i] for p in preds) / n
            std_i = math.sqrt(sum((p[i] - mean_i) ** 2 for p in preds) / n + 1e-6)
            if std_i < gamma:
                scale = 1.0 + lr * var_weight * (gamma - std_i)
                self.w_enc[i] = [w * scale for w in self.w_enc[i]]
        m = self.ema_momentum
        for i in range(self.latent_dim):
            for j in range(self.obs_dim):
                self.w_tgt[i][j] = m * self.w_tgt[i][j] + (1.0 - m) * self.w_enc[i][j]


def generate_rotational_dynamics(
    n_samples: int = 48, *, obs_dim: int = 4, seed: int = 123,
) -> list[tuple[Vec, Vec, Vec]]:
    """Deterministic action-conditioned rotational + affine dynamical transitions."""
    rng = random.Random(seed)
    data: list[tuple[Vec, Vec, Vec]] = []
    for _ in range(n_samples):
        x = [rng.uniform(-1.0, 1.0) for _ in range(obs_dim)]
        act = [rng.uniform(-0.6, 0.6), rng.uniform(-0.6, 0.6)]
        ang = 0.35 + 0.25 * act[0]
        ca, sa = math.cos(ang), math.sin(ang)
        nxt = [
            ca * x[0] - sa * x[1] + 0.15 * act[1],
            sa * x[0] + ca * x[1] - 0.10 * act[0],
            0.85 * x[2] + 0.20 * x[0] + 0.12 * act[1],
            0.85 * x[3] - 0.20 * x[1] + 0.12 * act[0],
        ]
        data.append((x, act, nxt[:obs_dim]))
    return data
