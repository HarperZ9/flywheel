# SPDX-License-Identifier: MIT
"""Deterministic rolling entropy & capability-floor drift monitor (stdlib only).

Detects non-finite IEEE-754 telemetry corruption, silent capability regression,
entropy collapse, epigenetic effective-rank decay, and non-convergent
oscillation loops across iterative runs fail-closed.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

HONEST_SCOPE_LIMIT = (
    "Monitors finite numeric capability, entropy, and effective-rank trajectories "
    "over a fixed rolling window; it detects non-finite telemetry, statistical "
    "regressions, and sign-flip loops in reported series without re-measuring weights."
)


def _is_finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


@dataclass(frozen=True)
class StepTelemetry:
    step: int
    capability: float
    entropy_bits: float
    effective_rank: float = 2.5


@dataclass(frozen=True)
class DriftPolicy:
    window: int = 4
    min_capability_floor: float = 0.90
    max_drop_from_peak: float = 0.05
    min_entropy_bits: float = 1.50
    min_effective_rank: float = 2.0
    max_sign_flips: int = 3
    delta_eps: float = 1e-9


@dataclass(frozen=True)
class DriftAlert:
    step: int
    code: str
    detail: str


class DriftMonitor:
    """Stateful rolling-window drift, regression, and oscillation monitor."""

    def __init__(self, policy: DriftPolicy = DriftPolicy()) -> None:
        if policy.window < 2:
            raise ValueError("policy.window must be >= 2")
        self.policy = policy
        self.history: list[StepTelemetry] = []
        self.peak_capability: float | None = None
        self.alerts: list[DriftAlert] = []

    def _rolling_sign_flips(self) -> int:
        recent = self.history[-(self.policy.window + 1) :]
        if len(recent) < 3:
            return 0
        signs: list[int] = []
        for a, b in zip(recent, recent[1:], strict=False):
            if not (_is_finite_number(a.capability) and _is_finite_number(b.capability)):
                continue
            diff = float(b.capability) - float(a.capability)
            if math.isfinite(diff) and abs(diff) > self.policy.delta_eps:
                signs.append(1 if diff > 0 else -1)
        flips = 0
        for s1, s2 in zip(signs, signs[1:], strict=False):
            if s1 != s2:
                flips += 1
        return flips

    def _check_finite(self, point: StepTelemetry, alerts: list[DriftAlert]) -> tuple[bool, bool, bool]:
        cap_ok = _is_finite_number(point.capability)
        ent_ok = _is_finite_number(point.entropy_bits)
        rank_ok = _is_finite_number(point.effective_rank)
        if not cap_ok:
            alerts.append(DriftAlert(point.step, "NON_FINITE_CAPABILITY", f"capability={point.capability!r}"))
        if not ent_ok:
            alerts.append(DriftAlert(point.step, "NON_FINITE_ENTROPY_BITS", f"entropy={point.entropy_bits!r}"))
        if not rank_ok:
            alerts.append(DriftAlert(point.step, "NON_FINITE_EFFECTIVE_RANK", f"rank={point.effective_rank!r}"))
        return cap_ok, ent_ok, rank_ok

    def _check_capability(self, point: StepTelemetry, alerts: list[DriftAlert]) -> None:
        cap_val = float(point.capability)
        if self.peak_capability is None or cap_val > self.peak_capability:
            self.peak_capability = cap_val
        if cap_val < self.policy.min_capability_floor:
            alerts.append(DriftAlert(point.step, "CAPABILITY_BELOW_FLOOR", f"{cap_val:.4f} < {self.policy.min_capability_floor:.4f}"))
        drop = self.peak_capability - cap_val
        if not math.isfinite(drop) or drop > self.policy.max_drop_from_peak:
            alerts.append(DriftAlert(point.step, "SILENT_REGRESSION_FROM_PEAK", f"drop={drop:.4f} > {self.policy.max_drop_from_peak:.4f}"))

    def record(self, point: StepTelemetry) -> list[DriftAlert]:
        """Ingest one telemetry point and return any fail-closed drift alerts raised."""
        new_alerts: list[DriftAlert] = []
        if self.history and point.step <= self.history[-1].step:
            new_alerts.append(DriftAlert(point.step, "NON_MONOTONIC_STEP", "step did not increase"))
        cap_ok, _, rank_ok = self._check_finite(point, new_alerts)
        self.history.append(point)
        if cap_ok:
            self._check_capability(point, new_alerts)
        if rank_ok and float(point.effective_rank) < self.policy.min_effective_rank:
            new_alerts.append(DriftAlert(point.step, "EPIGENETIC_RANK_DRIFT", f"{float(point.effective_rank):.4f} < {self.policy.min_effective_rank:.4f}"))
        win = self.history[-self.policy.window :]
        finite_ent = [float(p.entropy_bits) for p in win if _is_finite_number(p.entropy_bits)]
        if finite_ent:
            mean_entropy = sum(finite_ent) / len(finite_ent)
            if not math.isfinite(mean_entropy) or mean_entropy < self.policy.min_entropy_bits:
                new_alerts.append(DriftAlert(point.step, "ENTROPY_COLLAPSE", f"rolling_entropy={mean_entropy:.4f} < {self.policy.min_entropy_bits:.4f}"))
        flips = self._rolling_sign_flips()
        if flips >= self.policy.max_sign_flips:
            new_alerts.append(DriftAlert(point.step, "OSCILLATION_LOOP_DETECTED", f"sign_flips={flips} >= {self.policy.max_sign_flips}"))
        self.alerts.extend(new_alerts)
        return new_alerts


def assess_series(
    series: Sequence[StepTelemetry],
    policy: DriftPolicy = DriftPolicy(),
) -> dict[str, object]:
    """Assess a complete telemetry sequence fail-closed and return a summary report."""
    if not series:
        return {
            "ok": False,
            "verdict": "FAIL",
            "alerts": [{"step": -1, "code": "EMPTY_SERIES", "detail": "no telemetry points"}],
            "honest_scope_limit": HONEST_SCOPE_LIMIT,
        }
    mon = DriftMonitor(policy)
    for point in series:
        mon.record(point)
    win = mon.history[-policy.window :]
    finite_ent = [float(p.entropy_bits) for p in win if _is_finite_number(p.entropy_bits)]
    mean_ent = round(sum(finite_ent) / len(finite_ent), 6) if finite_ent else None
    latest = mon.history[-1].capability
    ok = len(mon.alerts) == 0
    return {
        "ok": ok,
        "verdict": "PASS" if ok else "FAIL",
        "steps_checked": len(mon.history),
        "peak_capability": mon.peak_capability,
        "latest_capability": latest if _is_finite_number(latest) else None,
        "rolling_mean_entropy": mean_ent,
        "oscillation_flips": mon._rolling_sign_flips(),
        "alerts": [{"step": a.step, "code": a.code, "detail": a.detail} for a in mon.alerts],
        "honest_scope_limit": HONEST_SCOPE_LIMIT,
    }
