"""sensorimotor_loop.py -- closed-loop sensorimotor perception and action contract.

Connects deterministic rendered environments (raw-native, Superframe, Estuary,
robotics/physics sims) directly to Flywheel's surprise-scaled compute loop
(stress_rest_loop), symmetry-manifold memory (manifold_memory), and shared
negative cache (negative_cache).

Every step pairs multi-medium sensory observation (visual, acoustic, haptic,
topological Betti invariants) with an action and a deterministic physics oracle,
turning rendered worlds into provenance-verified training and evaluation loops.

Zero third-party dependencies (stdlib only).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from .evidence_json import canonical_sha256
from .manifold_memory import ManifoldRecord, compile_memory_capsule
from .negative_cache import NegativeRecord, build_negative_cache
from .stress_rest_loop import allocate_loop_depth

EPISODE_SCHEMA = "flywheel.sensorimotor-episode/v1"


@dataclass(frozen=True)
class SensoryObservation:
    step: int
    position: tuple[float, float, float]
    phase_rad: float
    visual_energy: float
    acoustic_energy: float
    haptic_force: float
    betti0: int = 1
    betti1: int = 0

    def vector(self) -> tuple[float, ...]:
        return (
            *self.position,
            self.phase_rad,
            self.visual_energy,
            self.acoustic_energy,
            self.haptic_force,
        )

    def digest(self) -> str:
        return canonical_sha256({
            "step": self.step,
            "position": list(self.position),
            "phase_rad": round(self.phase_rad, 6),
            "visual_energy": round(self.visual_energy, 6),
            "acoustic_energy": round(self.acoustic_energy, 6),
            "haptic_force": round(self.haptic_force, 6),
            "betti0": self.betti0,
            "betti1": self.betti1,
        })


def prediction_surprise(predicted: SensoryObservation, observed: SensoryObservation) -> float:
    """Normalized L2 prediction error in [0, 1] across sensory channels."""
    diffs = [a - b for a, b in zip(predicted.vector(), observed.vector())]
    rms = math.sqrt(sum(d * d for d in diffs) / max(1, len(diffs)))
    return round(min(1.0, rms / (1.0 + rms)), 6)


def run_sensorimotor_episode(
    *,
    episode_id: str,
    domain: str,
    initial_obs: SensoryObservation,
    steps: int,
    policy_fn: Callable[[SensoryObservation, int], tuple[dict[str, Any], SensoryObservation]],
    env_step_fn: Callable[[SensoryObservation, dict[str, Any]], tuple[SensoryObservation, str | None]],
    compute_budget: int = 64,
    capsule_slots: int = 16,
) -> dict[str, Any]:
    """Run a closed-loop sensorimotor episode and emit a sealed receipt bundle.

    `policy_fn(obs, loop_depth) -> (action, predicted_next_obs)`
    `env_step_fn(obs, action) -> (actual_next_obs, physics_violation_or_none)`
    """
    if steps <= 0:
        raise ValueError("steps must be positive")
    obs = initial_obs
    budget_left = max(1, int(compute_budget))
    last_surprise = 0.0
    trace: list[dict[str, Any]] = []
    memories: list[ManifoldRecord] = []
    negatives: list[NegativeRecord] = []

    for idx in range(steps):
        alloc = allocate_loop_depth(last_surprise, min_depth=1, max_depth=8, budget_remaining=budget_left)
        depth = alloc["allocated_depth"]
        budget_left = alloc["budget_after"]
        action, predicted = policy_fn(obs, depth)
        next_obs, violation = env_step_fn(obs, action)
        surprise = prediction_surprise(predicted, next_obs)
        obs_sha = next_obs.digest()

        trace.append({
            "step": idx,
            "loop_depth": depth,
            "surprise": surprise,
            "action": dict(action),
            "obs_sha256": obs_sha,
            "violation": violation,
        })
        memories.append(
            ManifoldRecord(
                record_id=f"{episode_id}:s{idx}",
                manifold="linear",
                coords=next_obs.position,
                summary=f"step {idx} surprise={surprise:.3f} b0={next_obs.betti0} b1={next_obs.betti1}",
                source_sha256=obs_sha,
                weight=round(0.25 + 0.75 * surprise, 4),
            )
        )
        if violation:
            negatives.append(
                NegativeRecord(
                    record_id=f"{episode_id}:neg{idx}",
                    domain=domain,
                    hypothesis=f"action {action} at step {idx} stays within physical bounds",
                    failure_mode=violation,
                    parameters={"step": idx, **action},
                    measurement_sha256=obs_sha,
                )
            )
        obs = next_obs
        last_surprise = surprise

    capsule = compile_memory_capsule(
        memories,
        query_manifold="linear",
        query_coords=obs.position,
        budget_slots=capsule_slots,
    )
    neg_cache = build_negative_cache(negatives)
    mean_surprise = round(sum(t["surprise"] for t in trace) / len(trace), 6)
    result = {
        "schema": EPISODE_SCHEMA,
        "episode_id": episode_id,
        "domain": domain.strip().lower(),
        "steps": len(trace),
        "mean_surprise": mean_surprise,
        "violation_count": len(negatives),
        "compute_spent": int(compute_budget) - budget_left,
        "capsule": capsule,
        "negative_cache": neg_cache,
        "trace": trace,
    }
    result["episode_sha256"] = canonical_sha256(result)
    return result
