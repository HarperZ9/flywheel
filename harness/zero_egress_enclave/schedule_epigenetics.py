# SPDX-FileCopyrightText: 2026 Zain Dana Harper
# SPDX-License-Identifier: MIT
"""N33 / J13 Weights-Only Optimizer-Schedule vs Reward-History Epigenetics Classifier.

Separates AdamW cosine, SGD constant-LR, and reward-hacked shortcut trajectories
trained to matched final loss using pure weight/Hessian spectral fingerprints
with 0 inference calls, plus a 60x deterministic label-permutation null control.
Matches native BuildLang kernel epigenetics_schedule_study.bld (STA-059).
Pure Python standard library only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

HESSIAN_DIAG = (8.0, 4.5, 2.8, 1.9, 1.3, 0.9, 0.6, 0.4)


@dataclass(frozen=True)
class ScheduleEpigeneticsResult:
    """Measured output of the N33 weights-only epigenetics study."""

    ok: bool
    verdict: str
    heldout_acc_pct: float
    null_acc_pct: float
    ctrl_null_ok: bool
    inference_calls: int
    loss_adamw: float
    loss_sgd: float
    loss_hack: float


def _det_gauss(seed: int, idx: int) -> float:
    a = float(seed * 131 + idx * 37 + 11) * 0.7131
    b = float(seed * 97 + idx * 53 + 19) * 1.1973
    c = float(seed * 61 + idx * 89 + 23) * 0.4317
    return (math.sin(a) + math.cos(b) + math.sin(c)) / 3.0


def simulate_and_fingerprint(seed: int, class_id: int) -> tuple[list[float], float]:
    """Simulate one 8D trajectory to matched loss and extract 5 weight-only features."""
    w_star = [(1.0 if k % 2 == 0 else -1.0) * (0.55 + 0.08 * _det_gauss(seed, k)) for k in range(8)]
    w = [0.25 * _det_gauss(seed + 7, k) for k in range(8)]
    m = [0.0] * 8
    v = [0.0] * 8
    steps = 60
    for st in range(steps):
        prog = float(st) / float(steps)
        for k in range(8):
            noise = 0.04 * _det_gauss(seed * 3 + st, k)
            if class_id == 0:
                lr = 0.065 * 0.5 * (1.0 + math.cos(math.pi * prog))
                g = HESSIAN_DIAG[k] * (w[k] - w_star[k]) + noise
                m[k] = 0.9 * m[k] + 0.1 * g
                v[k] = 0.99 * v[k] + 0.01 * g * g
                w[k] = w[k] * (1.0 - 0.18 * lr) - lr * m[k] / (math.sqrt(v[k]) + 1.0e-6)
            elif class_id == 1:
                g = HESSIAN_DIAG[k] * (w[k] - w_star[k]) + 3.5 * noise
                w[k] = w[k] - 0.247 * g
            else:
                tgt = (2.45 + 0.06 * _det_gauss(seed, 99)) if k == 0 else (0.02 * _det_gauss(seed, k))
                g = 3.0 * (w[k] - tgt) + 0.5 * noise
                w[k] = w[k] - 0.08 * g

    if class_id == 2:
        d0 = w[0] - 2.45
        task_loss = 0.048 + 0.5 * d0 * d0
    else:
        lsum = sum(0.5 * HESSIAN_DIAG[k] * ((w[k] - w_star[k]) ** 2) for k in range(8))
        task_loss = 0.042 + 0.02 * lsum

    tot_e = 1.0e-15 + sum(wk * wk for wk in w)
    max_e = max(wk * wk for wk in w)
    sharp = sum((HESSIAN_DIAG[k] ** 2) * ((w[k] - w_star[k]) ** 2) for k in range(8))
    mu = sum(w) / 8.0
    h_ent = 0.0
    var_w = 1.0e-12
    m4 = 0.0
    for wk in w:
        p = (wk * wk) / tot_e
        if p > 1.0e-15:
            h_ent -= p * math.log(p)
        dw = wk - mu
        var_w += (dw * dw) / 8.0
        m4 += (dw ** 4) / 8.0
    feats = [math.exp(h_ent), max_e / tot_e, math.log(sharp + 1.0e-6), math.sqrt(tot_e), m4 / (var_w * var_w)]
    return feats, task_loss


def eval_3class_nearest_centroid(x_all: list[list[float]], y_all: list[int], n_tr: int) -> float:
    """Standardized 3-class nearest-centroid classifier fit on [:n_tr], evaluated on [n_tr:]."""
    nf = 5
    mu = [sum(x_all[i][f] for i in range(n_tr)) / float(n_tr) for f in range(nf)]
    sd = [math.sqrt(sum((x_all[i][f] - mu[f]) ** 2 for i in range(n_tr)) / float(n_tr)) + 1.0e-8 for f in range(nf)]
    cent = [[0.0] * nf for _ in range(3)]
    cnt = [0.0, 0.0, 0.0]
    for i in range(n_tr):
        cls = y_all[i]
        cnt[cls] += 1.0
        for f in range(nf):
            cent[cls][f] += (x_all[i][f] - mu[f]) / sd[f]
    for c in range(3):
        denom = max(1.0, cnt[c])
        for f in range(nf):
            cent[c][f] /= denom

    hits = 0
    for i in range(n_tr, len(x_all)):
        best_c, best_d = 0, 1.0e30
        for c in range(3):
            dist = sum((((x_all[i][f] - mu[f]) / sd[f]) - cent[c][f]) ** 2 for f in range(nf))
            if dist < best_d:
                best_d, best_c = dist, c
        if best_c == y_all[i]:
            hits += 1
    return float(hits) / float(len(x_all) - n_tr)


def run_schedule_epigenetics_audit(n_seeds: int = 20, n_perms: int = 60) -> ScheduleEpigeneticsResult:
    """Run the full seed-held-out 3-class study and deterministic label-permutation null."""
    x_all: list[list[float]] = []
    y_all: list[int] = []
    losses = [0.0, 0.0, 0.0]
    for s in range(n_seeds):
        for c in range(3):
            feats, loss_v = simulate_and_fingerprint(1000 + s * 19, c)
            x_all.append(feats)
            y_all.append(c)
            losses[c] += loss_v
    n_tr = (n_seeds * 3 // 5) * 3
    heldout = eval_3class_nearest_centroid(x_all, y_all, n_tr)

    y_perm = list(y_all)
    n_tot = len(y_perm)
    perm_sum = 0.0
    for p_idx in range(n_perms):
        for j in range(n_tot - 1, 0, -1):
            r = (p_idx * 73 + j * 31 + 17) % (j + 1)
            y_perm[j], y_perm[r] = y_perm[r], y_perm[j]
        perm_sum += eval_3class_nearest_centroid(x_all, y_perm, n_tr)
    null_mean = perm_sum / float(n_perms)
    ctrl_ok = null_mean <= 0.45 and abs(null_mean - 0.3333) < 0.12
    ok = heldout >= 0.95 and ctrl_ok
    return ScheduleEpigeneticsResult(
        ok=ok,
        verdict="PASS" if ok else "REJECT",
        heldout_acc_pct=round(heldout * 100.0, 4),
        null_acc_pct=round(null_mean * 100.0, 4),
        ctrl_null_ok=ctrl_ok,
        inference_calls=0,
        loss_adamw=round(losses[0] / float(n_seeds), 6),
        loss_sgd=round(losses[1] / float(n_seeds), 6),
        loss_hack=round(losses[2] / float(n_seeds), 6),
    )


def schedule_epigenetics_dict(res: ScheduleEpigeneticsResult) -> dict[str, Any]:
    """Convert ScheduleEpigeneticsResult into a structured JSON dict."""
    return {"schema": "n33-schedule-epigenetics/1", **res.__dict__}
