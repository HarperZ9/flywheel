# SPDX-License-Identifier: MIT
"""Fail-closed Crucible tail-risk distributional fuzzing gate (CS-024).

Executes seed-pinned adversarial inputs against a target callable, checks
seed reproducibility, invariant preservation, NaN/Inf absence, p99/CVaR_99
ceilings, and max-excursion bounds, sealing tail_fuzz_attestation_sha256.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .boundary_fuzzer import (
    fingerprint_cases,
    generate_mixed_boundary_cases,
    is_seed_reproducible,
)
from .tail_metrics import TailRiskMetrics, compute_tail_metrics

HONEST_SCOPE_LIMIT = (
    "Evaluates a target callable over deterministic seed-pinned boundary and "
    "heavy-tail inputs, gating on seed reproducibility, invariant violations, "
    "NaN/Inf absence, p99, CVaR_99, and max excursion ratio. Does not prove "
    "absence of defects outside the generated input distribution."
)

GeneratorFn = Callable[[int, int], Sequence[object]]
TargetFn = Callable[[object], float]
InvariantFn = Callable[[object, float], bool]


@dataclass(frozen=True)
class FuzzGatePolicy:
    """Fail-closed extreme-value and invariant thresholds for tail fuzzing."""

    max_p99: float | None = None
    max_cvar_99: float | None = None
    max_excursion_ratio: float | None = None
    max_invariant_violations: int = 0
    allow_non_finite: bool = False
    require_seed_reproducibility: bool = True


@dataclass(frozen=True)
class TailFuzzReport:
    """Fail-closed attestation summary of a Crucible tail-fuzz run."""

    passed: bool
    seed: int
    cases_executed: int
    invariant_violations: int
    non_finite_count: int
    seed_reproducible: bool
    case_stream_sha256: str
    metrics: TailRiskMetrics
    reasons: tuple[str, ...]
    tail_fuzz_attestation_sha256: str

    def to_dict(self) -> dict[str, object]:
        """Serialize fuzz report into a deterministic JSON-compatible dict."""
        return {
            "passed": self.passed,
            "seed": self.seed,
            "cases_executed": self.cases_executed,
            "invariant_violations": self.invariant_violations,
            "non_finite_count": self.non_finite_count,
            "seed_reproducible": self.seed_reproducible,
            "case_stream_sha256": self.case_stream_sha256,
            "metrics": self.metrics.to_dict(),
            "reasons": list(self.reasons),
            "tail_fuzz_attestation_sha256": self.tail_fuzz_attestation_sha256,
        }


def _run_cases(
    cases: Sequence[object],
    target_fn: TargetFn,
    invariant_fn: InvariantFn | None,
) -> tuple[list[object], int]:
    outcomes: list[object] = []
    violations = 0
    for case in cases:
        try:
            val = target_fn(case)
        except Exception:
            violations += 1
            outcomes.append(float("nan"))
            continue
        outcomes.append(val)
        if invariant_fn is not None:
            try:
                ok = bool(invariant_fn(case, val))
            except Exception:
                ok = False
            if not ok:
                violations += 1
    return outcomes, violations


def _apply_policy(metrics: TailRiskMetrics, violations: int, policy: FuzzGatePolicy, reasons: list[str]) -> None:
    if violations > policy.max_invariant_violations:
        reasons.append(f"INVARIANT_VIOLATIONS:{violations}>{policy.max_invariant_violations}")
    if not policy.allow_non_finite and metrics.non_finite_count > 0:
        reasons.append(f"SILENT_NAN_OR_INF_PROPAGATION:{metrics.non_finite_count}")
    if policy.max_p99 is not None and metrics.p99 > policy.max_p99:
        reasons.append(f"P99_TAIL_BLOWUP:{metrics.p99}>{policy.max_p99}")
    if policy.max_cvar_99 is not None and metrics.cvar_99 > policy.max_cvar_99:
        reasons.append(f"CVAR_99_EXCEEDED:{metrics.cvar_99}>{policy.max_cvar_99}")
    if policy.max_excursion_ratio is not None and metrics.max_excursion_ratio > policy.max_excursion_ratio:
        reasons.append(f"MAX_EXCURSION_EXCEEDED:{metrics.max_excursion_ratio}>{policy.max_excursion_ratio}")


def run_tail_fuzz_gate(
    target_fn: TargetFn,
    generator_fn: GeneratorFn = generate_mixed_boundary_cases,
    *,
    seed: int = 42,
    count: int = 200,
    invariant_fn: InvariantFn | None = None,
    policy: FuzzGatePolicy | None = None,
) -> TailFuzzReport:
    """Execute deterministic tail-risk fuzzing and enforce policy fail-closed."""
    active_policy = policy if policy is not None else FuzzGatePolicy()
    reasons: list[str] = []
    reproducible = is_seed_reproducible(generator_fn, seed, count)
    if active_policy.require_seed_reproducibility and not reproducible:
        reasons.append("NON_DETERMINISTIC_GENERATOR")
    cases = list(generator_fn(seed, count))
    stream_sha = fingerprint_cases(cases)
    if not cases:
        reasons.append("EMPTY_FUZZ_CORPUS")
        empty = TailRiskMetrics(0, 0, 0, False, False, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        seal = _seal_report(seed, 0, 0, reproducible, stream_sha, empty, False, reasons)
        return TailFuzzReport(False, seed, 0, 0, 0, reproducible, stream_sha, empty, tuple(reasons), seal)
    outcomes, violations = _run_cases(cases, target_fn, invariant_fn)
    metrics = compute_tail_metrics(outcomes)
    _apply_policy(metrics, violations, active_policy, reasons)
    passed = not reasons
    seal = _seal_report(seed, len(cases), violations, reproducible, stream_sha, metrics, passed, reasons)
    return TailFuzzReport(
        passed, seed, len(cases), violations, metrics.non_finite_count,
        reproducible, stream_sha, metrics, tuple(reasons), seal,
    )


def _seal_report(
    seed: int,
    cases_executed: int,
    violations: int,
    reproducible: bool,
    stream_sha: str,
    metrics: TailRiskMetrics,
    passed: bool,
    reasons: Sequence[str],
) -> str:
    payload = {
        "passed": passed,
        "seed": seed,
        "cases_executed": cases_executed,
        "invariant_violations": violations,
        "seed_reproducible": reproducible,
        "case_stream_sha256": stream_sha,
        "metrics": metrics.to_dict(),
        "reasons": list(reasons),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
