"""Harness dynamics: maintainability debt gate, strong-inference experiment selector,
and Lyapunov / isometric score-centering stability primitives.

Stdlib-only deterministic kernels designed to close three gaps in task-level
agentic workflows:
1. MaintainabilityDebtGate: catches task-level RLVR debt (comment bloat,
   trivial tests, oversized files/functions) at the harness layer.
2. select_highest_ig_experiment: picks the smallest experiment that maximizes
   expected Shannon information gain per unit time (bits/sec).
3. LyapunovStabilityTracker + center_and_clip_scores: tracks finite-time
   Lyapunov exponent across trajectory perturbations (self-stabilizing vs
   diverging) and applies baseline-centered isometric step normalization.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


def _sha256_json(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


# ---------------------------------------------------------------------------
# 1. Maintainability Debt Gate (Harness-Layer Counterweight to Task-Level RLVR)
# ---------------------------------------------------------------------------


def evaluate_maintainability_debt(
    modules: Mapping[str, str],
    *,
    max_file_lines: int = 300,
    max_function_lines: int = 50,
    max_comment_ratio: float = 0.45,
) -> dict[str, Any]:
    """Score Python source modules for task-level agentic maintainability debt."""
    violations: list[dict[str, Any]] = []
    for name in sorted(modules):
        src = modules[name]
        lines = src.splitlines()
        line_count = len(lines)
        if line_count > max_file_lines:
            violations.append(
                {
                    "module": name,
                    "rule": "file_line_cap",
                    "value": line_count,
                    "limit": max_file_lines,
                }
            )
        non_empty = [ln.strip() for ln in lines if ln.strip()]
        comment_lines = sum(1 for ln in non_empty if ln.startswith("#"))
        comment_ratio = (comment_lines / len(non_empty)) if non_empty else 0.0
        if len(non_empty) >= 10 and comment_ratio > max_comment_ratio:
            violations.append(
                {
                    "module": name,
                    "rule": "comment_bloat",
                    "value": round(comment_ratio, 4),
                    "limit": max_comment_ratio,
                }
            )
        try:
            tree = ast.parse(src, filename=name)
        except SyntaxError as exc:
            violations.append(
                {
                    "module": name,
                    "rule": "syntax_error",
                    "value": exc.lineno or 0,
                    "limit": 0,
                }
            )
            continue

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                end = getattr(node, "end_lineno", node.lineno)
                span = end - node.lineno + 1
                if span > max_function_lines:
                    violations.append(
                        {
                            "module": name,
                            "rule": "function_line_cap",
                            "symbol": node.name,
                            "value": span,
                            "limit": max_function_lines,
                        }
                    )
                if node.name.startswith("test_"):
                    asserts = [n for n in ast.walk(node) if isinstance(n, ast.Assert)]
                    trivial = [
                        a
                        for a in asserts
                        if isinstance(a.test, ast.Constant) and bool(a.test.value) is True
                    ]
                    if not asserts or len(trivial) == len(asserts):
                        violations.append(
                            {
                                "module": name,
                                "rule": "trivial_test",
                                "symbol": node.name,
                                "value": len(asserts),
                                "limit": 1,
                            }
                        )

    verdict = "ACCEPT" if not violations else "REJECT"
    result: dict[str, Any] = {
        "verdict": verdict,
        "modules_checked": len(modules),
        "violation_count": len(violations),
        "violations": violations,
    }
    result["digest"] = _sha256_json(result)
    return result


# ---------------------------------------------------------------------------
# 2. Strong-Inference Experiment Selector (Bits / Second)
# ---------------------------------------------------------------------------


def _entropy_bits(probs: Sequence[float]) -> float:
    total = sum(p for p in probs if p > 0)
    if total <= 0:
        return 0.0
    h = 0.0
    for p in probs:
        if p > 0:
            q = p / total
            h -= q * math.log2(q)
    return h


@dataclass(frozen=True)
class ExperimentCandidate:
    experiment_id: str
    cost_seconds: float
    # Outcome likelihoods P(outcome | hypothesis_i) for each hypothesis i.
    # Each inner sequence is one possible outcome row of length len(priors).
    outcome_likelihoods: tuple[tuple[float, ...], ...]


def select_highest_ig_experiment(
    priors: Sequence[float],
    candidates: Sequence[ExperimentCandidate],
) -> dict[str, Any]:
    """Rank experiments by expected Shannon information gain per second."""
    if not priors or sum(priors) <= 0:
        raise ValueError("priors must be non-empty with positive sum")
    if not candidates:
        raise ValueError("candidates must be non-empty")

    total_prior = sum(priors)
    norm_priors = [p / total_prior for p in priors]
    prior_h = _entropy_bits(norm_priors)

    ranked: list[dict[str, Any]] = []
    for cand in candidates:
        if cand.cost_seconds <= 0:
            raise ValueError(f"{cand.experiment_id}: cost_seconds must be positive")
        expected_post_h = 0.0
        for row in cand.outcome_likelihoods:
            if len(row) != len(norm_priors):
                raise ValueError(f"{cand.experiment_id}: likelihood row length mismatch")
            joint = [norm_priors[i] * max(0.0, float(row[i])) for i in range(len(norm_priors))]
            p_outcome = sum(joint)
            if p_outcome > 0:
                expected_post_h += p_outcome * _entropy_bits(joint)
        ig_bits = max(0.0, prior_h - expected_post_h)
        ig_per_sec = ig_bits / cand.cost_seconds
        ranked.append(
            {
                "experiment_id": cand.experiment_id,
                "cost_seconds": round(cand.cost_seconds, 6),
                "expected_ig_bits": round(ig_bits, 6),
                "ig_bits_per_second": round(ig_per_sec, 6),
            }
        )

    ranked.sort(key=lambda r: (-r["ig_bits_per_second"], -r["expected_ig_bits"], r["experiment_id"]))
    result: dict[str, Any] = {
        "prior_entropy_bits": round(prior_h, 6),
        "selected": ranked[0]["experiment_id"],
        "ranking": ranked,
    }
    result["digest"] = _sha256_json(result)
    return result


# ---------------------------------------------------------------------------
# 3. Lyapunov Trajectory Stability & Isometric Score Centering
# ---------------------------------------------------------------------------


def lyapunov_trajectory_stability(
    perturbation_norms: Sequence[float],
    *,
    eps: float = 1e-12,
) -> dict[str, Any]:
    """Compute finite-time Lyapunov exponent from successive perturbation norms."""
    if len(perturbation_norms) < 2:
        raise ValueError("need at least 2 perturbation norms")
    logs: list[float] = []
    for i in range(len(perturbation_norms) - 1):
        a = max(eps, float(perturbation_norms[i]))
        b = max(eps, float(perturbation_norms[i + 1]))
        logs.append(math.log(b / a))
    exponent = sum(logs) / len(logs)
    if exponent < -0.02:
        regime = "SELF_STABILIZING"
    elif exponent > 0.02:
        regime = "DIVERGING"
    else:
        regime = "NEUTRAL"
    result: dict[str, Any] = {
        "steps": len(logs),
        "lyapunov_exponent": round(exponent, 6),
        "regime": regime,
        "initial_norm": round(float(perturbation_norms[0]), 6),
        "final_norm": round(float(perturbation_norms[-1]), 6),
    }
    result["digest"] = _sha256_json(result)
    return result


def center_and_clip_scores(
    scores: Sequence[float],
    *,
    max_norm: float = 1.0,
) -> dict[str, Any]:
    """Mean-center candidate scores and project onto an isometric norm ball."""
    if not scores:
        raise ValueError("scores must be non-empty")
    if max_norm <= 0:
        raise ValueError("max_norm must be positive")
    vals = [float(s) for s in scores]
    mean = sum(vals) / len(vals)
    centered = [v - mean for v in vals]
    norm = math.sqrt(sum(c * c for c in centered))
    scale = (max_norm / norm) if norm > max_norm else 1.0
    projected = [round(c * scale, 6) for c in centered]
    result: dict[str, Any] = {
        "baseline_mean": round(mean, 6),
        "raw_l2_norm": round(norm, 6),
        "clipped": norm > max_norm,
        "advantages": projected,
    }
    result["digest"] = _sha256_json(result)
    return result
