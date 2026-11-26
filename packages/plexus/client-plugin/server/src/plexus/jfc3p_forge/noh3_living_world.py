"""NOH-3 Living World Organism with Buckingham-Pi dimensionless scale normalization,
Birkhoff mHC 4-stream mixing, Model Carving, Caustic-Carved sparse tick gates,
and CODIT per-organelle fault-isolation immune organ.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Sequence

from .model_carving_arch import CarvedSublayerGate, LoomMHCRouter, validate_carving_health

ORGANELLE_NAMES: tuple[str, ...] = ("symplectic_core", "aero_drag", "contact_impulse", "fast_weight_delta")
ENV_NAMES: tuple[str, ...] = (
    "OrbitalRendezvousEnv",
    "QuadrotorDroneEnv",
    "PoweredDescent6DOFEnv",
    "BipedBalanceContactEnv",
)


@dataclass(frozen=True)
class ImmuneEvent:
    step: int
    organelle_idx: int
    organelle_name: str
    reason: str


class BuckinghamPiNormalizer:
    """Dimensionless Buckingham-Pi scale normalizer preventing raw OOD polynomial blowup."""

    def __init__(self, state_scales: Sequence[float], action_scales: Sequence[float], eps: float = 1e-6) -> None:
        if not state_scales or not action_scales:
            raise ValueError("state_scales and action_scales must be non-empty")
        self.state_scales = tuple(max(abs(float(s)), eps) for s in state_scales)
        self.action_scales = tuple(max(abs(float(s)), eps) for s in action_scales)

    def to_pi_state(self, state: Sequence[float]) -> list[float]:
        return [float(x) / s for x, s in zip(state, self.state_scales)]

    def to_pi_action(self, action: Sequence[float]) -> list[float]:
        return [float(u) / s for u, s in zip(action, self.action_scales)]

    def from_pi_state(self, pi_state: Sequence[float]) -> list[float]:
        return [float(x) * s for x, s in zip(pi_state, self.state_scales)]

    def bound_pi_delta(self, pi_delta: Sequence[float], cap: float = 2.0) -> list[float]:
        return [cap * math.tanh(float(d) / cap) for d in pi_delta]


class CausticTickGate:
    """DS-08 caustic-carved asynchronous tick gate keeping quiet organelles in a held frame."""

    def __init__(self, n_organelles: int = 4, threshold: float = 0.015) -> None:
        self.threshold = float(threshold)
        self.ticks_executed = 0
        self.ticks_held = 0
        self._cached: list[list[float] | None] = [None] * n_organelles

    def should_tick(self, idx: int, surprise_pi: float) -> bool:
        if self._cached[idx] is None or surprise_pi >= self.threshold:
            self.ticks_executed += 1
            return True
        self.ticks_held += 1
        return False

    def cache(self, idx: int, value: Sequence[float]) -> list[float]:
        copied = [float(v) for v in value]
        self._cached[idx] = copied
        return copied

    def cached_or_zero(self, idx: int, dim: int) -> list[float]:
        val = self._cached[idx]
        return list(val) if val is not None else [0.0] * dim

    @property
    def held_ratio(self) -> float:
        tot = self.ticks_executed + self.ticks_held
        return (self.ticks_held / float(tot)) if tot > 0 else 0.0


class CODITImmuneOrgan:
    """Compartmentalizes corrupted organelles (NaN, quaternion drift, residual spike) without crashing."""

    def __init__(self, max_pi_norm: float = 6.0, quat_tol: float = 0.05) -> None:
        self.max_pi_norm = float(max_pi_norm)
        self.quat_tol = float(quat_tol)
        self.quarantined: set[int] = set()
        self.events: list[ImmuneEvent] = []

    def inspect_organelle(
        self, step: int, idx: int, pi_stream: Sequence[float], *, quat: Sequence[float] | None = None,
    ) -> bool:
        if idx in self.quarantined:
            return False
        if any(not math.isfinite(v) for v in pi_stream):
            self._quarantine(step, idx, "non_finite_stream")
            return False
        norm = math.sqrt(sum(v * v for v in pi_stream))
        if norm > self.max_pi_norm:
            self._quarantine(step, idx, f"pi_norm_explosion:{norm:.2f}")
            return False
        if quat is not None and len(quat) == 4:
            qnorm = math.sqrt(sum(q * q for q in quat))
            if not math.isfinite(qnorm) or abs(qnorm - 1.0) > self.quat_tol:
                self._quarantine(step, idx, f"quaternion_norm_drift:{qnorm:.4f}")
                return False
        return True

    def _quarantine(self, step: int, idx: int, reason: str) -> None:
        self.quarantined.add(idx)
        name = ORGANELLE_NAMES[idx] if idx < len(ORGANELLE_NAMES) else f"organelle_{idx}"
        self.events.append(ImmuneEvent(step, idx, name, reason))


class NOH3LivingWorldOrganism:
    """Scale-normalized NOH-3 organism with mHC mixing, Model Carving, Caustic Ticks, and CODIT immunity."""

    def __init__(self, state_dim: int = 4, action_dim: int = 2, *, tick_threshold: float = 0.015) -> None:
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.gate = CarvedSublayerGate(
            ("mhc_0", "carve_mlp_0", "caustic_1", "carve_mlp_1", "fast_mem_2", "carve_mlp_2"),
            (120_000, 240_000, 120_000, 240_000, 120_000, 240_000),
            (0.9, 0.8, -0.5, -0.4, 0.85, 0.7),
        )
        self.router = LoomMHCRouter(
            [[1.8, 0.3, 0.2, 0.2], [0.2, 1.7, 0.3, 0.2], [0.2, 0.2, 1.8, 0.3], [0.2, 0.3, 0.2, 1.7]]
        )
        self.tick_gate = CausticTickGate(n_organelles=4, threshold=tick_threshold)
        self.immune = CODITImmuneOrgan()
        self.fast_w: list[list[float]] = [[0.0] * (state_dim + action_dim) for _ in range(state_dim)]
        self.prev_deep_latent: list[float] = [0.0] * state_dim
        self.alf_gain = 0.15
        self.step_count = 0

    def _fast_delta(self, feat: Sequence[float]) -> list[float]:
        raw = [sum(w * f for w, f in zip(row, feat)) for row in self.fast_w]
        return [r + self.alf_gain * p for r, p in zip(raw, self.prev_deep_latent)]

    def sleep_consolidate(
        self, episodes: Sequence[tuple[Sequence[float], Sequence[float], Sequence[float], Sequence[float], BuckinghamPiNormalizer]],
        *, passes: int = 2, lr: float = 0.25,
    ) -> dict[str, Any]:
        """Loop-1 Sleep offline consolidation keeping live decode strictly 1-pass."""
        losses = [self.adapt_online(s, a, n, p, nm, lr=lr) for _ in range(max(1, passes)) for s, a, n, p, nm in episodes]
        return {"passes": max(1, passes), "updates": len(losses), "final_pi_mse": round(losses[-1], 6) if losses else 0.0}

    def predict_next(
        self, state: Sequence[float], action: Sequence[float], prior_delta: Sequence[float], normalizer: BuckinghamPiNormalizer,
        *, surprise_pi: float = 0.05, fault_streams: dict[int, Sequence[float]] | None = None,
        fault_quats: dict[int, Sequence[float]] | None = None,
    ) -> tuple[list[float], dict[str, Any]]:
        self.step_count += 1
        pi_s = normalizer.to_pi_state(state)
        pi_u = normalizer.to_pi_action(action)
        pi_prior = normalizer.bound_pi_delta(normalizer.to_pi_state(prior_delta), cap=1.5)
        feat = pi_s + pi_u
        raw_streams = [
            list(pi_prior),
            [0.02 * v for v in pi_prior],
            [0.01 * (u if i < len(pi_u) else 0.0) for i, u in enumerate(pi_u + [0.0] * self.state_dim)][: self.state_dim],
            self._fast_delta(feat),
        ]
        streams: list[list[float]] = []
        for idx in range(4):
            cand = list(fault_streams[idx]) if fault_streams and idx in fault_streams else raw_streams[idx]
            quat = fault_quats.get(idx) if fault_quats else None
            if not self.immune.inspect_organelle(self.step_count, idx, cand, quat=quat):
                streams.append(list(pi_prior))
            elif idx == 3 and not self.tick_gate.should_tick(idx, surprise_pi):
                streams.append(self.tick_gate.cached_or_zero(idx, self.state_dim))
            else:
                streams.append(self.tick_gate.cache(idx, cand) if idx == 3 else cand)
        routed = self.router.route(streams, mode="mhc")
        mix_delta = [sum(routed["outputs"][k][d] for k in range(4)) / 4.0 for d in range(self.state_dim)]
        combined_pi = normalizer.bound_pi_delta([0.75 * p + 0.25 * m for p, m in zip(pi_prior, mix_delta)], cap=2.0)
        self.prev_deep_latent = [0.0] * self.state_dim if 3 in self.immune.quarantined else list(combined_pi)
        phys_delta = normalizer.from_pi_state(combined_pi)
        next_state = [float(s) + float(d) for s, d in zip(state, phys_delta)]
        return next_state, {
            "mhc_row_err": routed["max_row_sum_err"],
            "quarantined_count": len(self.immune.quarantined),
            "held_tick_ratio": round(self.tick_gate.held_ratio, 4),
            "alf_latent_norm": round(math.sqrt(sum(v * v for v in self.prev_deep_latent)), 6),
        }

    def adapt_online(
        self, state: Sequence[float], action: Sequence[float], true_next: Sequence[float],
        prior_delta: Sequence[float], normalizer: BuckinghamPiNormalizer, lr: float = 0.65,
    ) -> float:
        pred, _ = self.predict_next(state, action, prior_delta, normalizer, surprise_pi=1.0)
        pi_err = normalizer.to_pi_state([t - p for t, p in zip(true_next, pred)])
        feat = normalizer.to_pi_state(state) + normalizer.to_pi_action(action)
        denom = 1.0 + sum(f * f for f in feat)
        for d in range(self.state_dim):
            step = lr * pi_err[d] / denom
            for j, f in enumerate(feat):
                self.fast_w[d][j] = max(-2.5, min(2.5, self.fast_w[d][j] + step * f))
        return sum(e * e for e in pi_err) / float(self.state_dim)


def _env_step(env_name: str, state: list[float], action: list[float], *, ood_scale: float) -> tuple[list[float], list[float], list[float]]:
    dt = 0.1
    x, y, vx, vy = state
    ax, ay = action
    if env_name == "OrbitalRendezvousEnv":
        w = 0.35 / math.sqrt(ood_scale)
        prior = [vx * dt, vy * dt, (ax + 2.0 * w * vy) * dt, (ay - 2.0 * w * vx) * dt]
        drift = [0.0, 0.0, -0.08 * vx * dt, -0.06 * vy * dt]
    elif env_name == "QuadrotorDroneEnv":
        prior = [vx * dt, vy * dt, (ax - 0.12 * vx) * dt, (ay - 0.12 * vy) * dt]
        drift = [0.0, 0.0, 0.07 * ood_scale * dt, -0.05 * vy * dt]
    elif env_name == "PoweredDescent6DOFEnv":
        g = 3.71 * (1.0 + 0.15 * (ood_scale - 1.0))
        prior = [vx * dt, vy * dt, (ax - 0.05 * vx) * dt, (ay - g) * dt]
        drift = [0.0, 0.0, -0.04 * vx * dt, 0.06 * ay * dt]
    else:
        prior = [vx * dt, vy * dt, (ax - 0.25 * x) * dt, (ay - 0.20 * vy) * dt]
        drift = [0.0, 0.0, -0.05 * vx * dt, 0.04 * ax * dt]
    nxt = [s + p + d for s, p, d in zip(state, prior, drift)]
    scales = [max(abs(x), 1.0) * ood_scale, max(abs(y), 1.0) * ood_scale, max(abs(vx), 1.0) * ood_scale, max(abs(vy), 1.0) * ood_scale]
    return nxt, prior, scales


def _eval_single_env(env_name: str, steps: int = 16) -> dict[str, Any]:
    org = NOH3LivingWorldOrganism(state_dim=4, action_dim=2)
    flat_bias = [0.0, 0.0, 0.0, 0.0]
    in_state = [1.0, 0.5, 0.4, -0.3]
    for k in range(8):
        act = [0.3 * math.sin(k), 0.3 * math.cos(k)]
        nxt, prior, scales = _env_step(env_name, in_state, act, ood_scale=1.0)
        norm = BuckinghamPiNormalizer(scales, [1.0, 1.0])
        org.adapt_online(in_state, act, nxt, prior, norm, lr=0.45)
        flat_bias = [0.7 * b + 0.3 * (n - s) for b, n, s in zip(flat_bias, nxt, in_state)]
        in_state = nxt
    ood_scale = 4.5
    state = [1.0 * ood_scale, 0.5 * ood_scale, 0.4 * ood_scale, -0.3 * ood_scale]
    flat_sq = raw_noh3_sq = unnorm_sq = 0.0
    for k in range(steps):
        act = [0.3 * ood_scale * math.sin(k), 0.3 * ood_scale * math.cos(k)]
        nxt, prior, scales = _env_step(env_name, state, act, ood_scale=ood_scale)
        norm = BuckinghamPiNormalizer(scales, [ood_scale, ood_scale])
        pred_raw, _ = org.predict_next(state, act, prior, norm)
        flat_pred = [s + b for s, b in zip(state, flat_bias)]
        unnorm_pred = [s + p + 0.05 * (s * s) for s, p in zip(state, prior)]
        raw_noh3_sq += sum((n - p) ** 2 for n, p in zip(nxt, pred_raw)) / 4.0
        flat_sq += sum((n - p) ** 2 for n, p in zip(nxt, flat_pred)) / 4.0
        unnorm_sq += sum((n - p) ** 2 for n, p in zip(nxt, unnorm_pred)) / 4.0
        state = nxt
    adapt_sq = 0.0
    state = [1.0 * ood_scale, 0.5 * ood_scale, 0.4 * ood_scale, -0.3 * ood_scale]
    for k in range(steps):
        act = [0.3 * ood_scale * math.sin(k), 0.3 * ood_scale * math.cos(k)]
        nxt, prior, scales = _env_step(env_name, state, act, ood_scale=ood_scale)
        norm = BuckinghamPiNormalizer(scales, [ood_scale, ood_scale])
        pred_ad, _ = org.predict_next(state, act, prior, norm)
        adapt_sq += sum((n - p) ** 2 for n, p in zip(nxt, pred_ad)) / 4.0
        org.adapt_online(state, act, nxt, prior, norm, lr=0.6)
        state = nxt
    return {
        "env": env_name,
        "flat_ood_mse": round(flat_sq / steps, 6),
        "unnormalized_prior_ood_mse": round(unnorm_sq / steps, 6),
        "noh3_raw_ood_mse": round(raw_noh3_sq / steps, 6),
        "noh3_adapted_ood_mse": round(adapt_sq / steps, 6),
        "beats_flat_raw": (raw_noh3_sq / steps) < (flat_sq / steps),
        "beats_flat_adapted": (adapt_sq / steps) < (flat_sq / steps),
    }


def evaluate_noh3_suite() -> dict[str, Any]:
    """Run all 4 physics environments + CODIT planted-fault isolation controls."""
    envs = [_eval_single_env(name) for name in ENV_NAMES]
    probe = NOH3LivingWorldOrganism()
    norm = BuckinghamPiNormalizer([1.0, 1.0, 1.0, 1.0], [1.0, 1.0])
    out_nan, _ = probe.predict_next([1.0, 0.0, 0.2, 0.1], [0.1, 0.0], [0.02, 0.01, 0.0, 0.0], norm, fault_streams={1: [float("nan")] * 4})
    out_quat, _ = probe.predict_next([1.0, 0.0, 0.2, 0.1], [0.1, 0.0], [0.02, 0.01, 0.0, 0.0], norm, fault_quats={2: [1.5, 0.0, 0.0, 0.0]})
    out_boom, _ = probe.predict_next([1.0, 0.0, 0.2, 0.1], [0.1, 0.0], [0.02, 0.01, 0.0, 0.0], norm, fault_streams={3: [1e6, 0.0, 0.0, 0.0]})
    codit_ok = (
        len(probe.immune.quarantined) == 3
        and all(math.isfinite(v) for v in out_nan + out_quat + out_boom)
    )
    carving = validate_carving_health(probe.gate)
    return {
        "ok": all(e["beats_flat_raw"] and e["beats_flat_adapted"] for e in envs) and codit_ok and carving.healthy,
        "envs": envs,
        "codit_faults_quarantined": len(probe.immune.quarantined),
        "codit_events": [ev.__dict__ for ev in probe.immune.events],
        "carving_health": carving.__dict__,
    }
