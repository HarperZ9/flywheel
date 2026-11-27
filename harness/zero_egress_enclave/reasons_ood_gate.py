# SPDX-FileCopyrightText: 2026 Zain Dana Harper
# SPDX-License-Identifier: MIT
"""N39 Reasons-in-Training-Data Two-Arm OOD Spurious-Flip Generalization Gate.

Contrasts Arm A (label-only supervision that grabs a high-SNR spurious cue and
collapses on OOD sign-flip) against Arm B (causal-reason supervision retaining
>= 90% OOD accuracy), plus a planted spurious-leakage control catching leaked
shortcut features inside the reason mask fail-closed.
Matches native BuildLang kernel reasons_generalization.bld (STA-060).
Pure Python standard library only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReasonsOodResult:
    """Outcome of the two-arm N39 OOD spurious-flip generalization audit."""

    ok: bool
    verdict: str
    arm_a_train_acc: float
    arm_a_ood_acc: float
    arm_b_train_acc: float
    arm_b_ood_acc: float
    leaked_mask_ood_acc: float
    ctrl_leak_caught: bool


def _det_val(seed: int, idx: int) -> float:
    a = float(seed * 137 + idx * 43 + 11) * 0.6713
    b = float(seed * 89 + idx * 61 + 17) * 1.1329
    return (math.sin(a) + math.cos(b)) * 0.7


def _sigmoid(z: float) -> float:
    if z > 20.0:
        return 1.0
    if z < -20.0:
        return 0.0
    return 1.0 / (1.0 + math.exp(-z))


def make_spurious_dataset(seed: int, n: int, spur_sign: float) -> tuple[list[list[float]], list[float]]:
    """Generate n 6D points with causal rule on dims 0..2 and spurious cue on dim 3."""
    xs: list[list[float]] = []
    ys: list[float] = []
    for i in range(n):
        x0 = _det_val(seed, i * 6)
        x1 = _det_val(seed, i * 6 + 1)
        x2 = _det_val(seed, i * 6 + 2)
        x4 = _det_val(seed, i * 6 + 4)
        x5 = _det_val(seed, i * 6 + 5)
        y = 1.0 if (1.2 * x0 - 1.1 * x1 + 0.9 * x2) >= 0.0 else 0.0
        y_pm = 2.0 * y - 1.0
        x3 = spur_sign * 2.8 * y_pm + 0.25 * _det_val(seed, i * 6 + 3)
        xs.append([x0, x1, x2, x3, x4, x5])
        ys.append(y)
    return xs, ys


def train_logistic_arm(
    x_tr: list[list[float]],
    y_tr: list[float],
    use_reasons: bool,
    reason_mask: tuple[float, ...],
    steps: int = 180,
) -> list[float]:
    """Train 6D logistic classifier with optional causal-reason mask penalty."""
    w = [0.0] * 6
    inv_n = 1.0 / float(len(x_tr))
    for _ in range(steps):
        grad = [0.0] * 6
        for xi, yi in zip(x_tr, y_tr):
            z = sum(w[j] * xi[j] for j in range(6))
            diff = _sigmoid(z) - yi
            for j in range(6):
                grad[j] += diff * xi[j]
        for j in range(6):
            reg = 4.0 if (use_reasons and reason_mask[j] < 0.5) else 0.02
            w[j] -= 0.18 * (grad[j] * inv_n + reg * w[j])
    return w


def eval_accuracy(xs: list[list[float]], ys: list[float], w: list[float]) -> float:
    """Compute binary classification accuracy of weights w on (xs, ys)."""
    hits = sum(1 for xi, yi in zip(xs, ys) if (1.0 if sum(w[j] * xi[j] for j in range(6)) >= 0.0 else 0.0) == yi)
    return float(hits) / float(len(xs))


def evaluate_reason_mask_invariance(
    reason_mask: tuple[float, ...],
    n_samples: int = 240,
    min_ood_acc: float = 0.90,
) -> tuple[bool, float, float]:
    """Audit a supplied causal-reason mask fail-closed against OOD spurious flip."""
    if len(reason_mask) != 6 or sum(reason_mask) <= 0.0:
        return False, 0.0, 0.0
    x_tr, y_tr = make_spurious_dataset(3901, n_samples, 1.0)
    x_ood, y_ood = make_spurious_dataset(3999, n_samples, -1.0)
    w = train_logistic_arm(x_tr, y_tr, use_reasons=True, reason_mask=reason_mask)
    tr_acc = eval_accuracy(x_tr, y_tr, w)
    ood_acc = eval_accuracy(x_ood, y_ood, w)
    return (tr_acc >= min_ood_acc and ood_acc >= min_ood_acc), round(tr_acc, 6), round(ood_acc, 6)


def run_reasons_ood_gate(n_samples: int = 240) -> ReasonsOodResult:
    """Run Arm A (label-only), Arm B (causal reasons), and planted spurious-leak control."""
    x_tr, y_tr = make_spurious_dataset(3901, n_samples, 1.0)
    x_ood, y_ood = make_spurious_dataset(3999, n_samples, -1.0)
    mask_clean = (1.0, 1.0, 1.0, 0.0, 0.0, 0.0)
    mask_leaked = (1.0, 1.0, 1.0, 1.0, 0.0, 0.0)

    w_a = train_logistic_arm(x_tr, y_tr, use_reasons=False, reason_mask=mask_clean)
    a_tr = eval_accuracy(x_tr, y_tr, w_a)
    a_ood = eval_accuracy(x_ood, y_ood, w_a)

    w_b = train_logistic_arm(x_tr, y_tr, use_reasons=True, reason_mask=mask_clean)
    b_tr = eval_accuracy(x_tr, y_tr, w_b)
    b_ood = eval_accuracy(x_ood, y_ood, w_b)

    w_leak = train_logistic_arm(x_tr, y_tr, use_reasons=True, reason_mask=mask_leaked)
    leak_ood = eval_accuracy(x_ood, y_ood, w_leak)
    ctrl_caught = leak_ood < 0.40

    ok = a_tr >= 0.90 and a_ood < 0.40 and b_tr >= 0.90 and b_ood >= 0.90 and ctrl_caught
    return ReasonsOodResult(
        ok=ok,
        verdict="PASS" if ok else "REJECT",
        arm_a_train_acc=round(a_tr, 6),
        arm_a_ood_acc=round(a_ood, 6),
        arm_b_train_acc=round(b_tr, 6),
        arm_b_ood_acc=round(b_ood, 6),
        leaked_mask_ood_acc=round(leak_ood, 6),
        ctrl_leak_caught=ctrl_caught,
    )


def reasons_ood_dict(res: ReasonsOodResult) -> dict[str, Any]:
    """Serialize ReasonsOodResult into a plain JSON-safe dictionary."""
    return {"schema": "n39-reasons-ood-gate/1", **res.__dict__}
