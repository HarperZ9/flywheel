"""Independent synthetic system and witness generator (no BootLoops code).

Builds a random sparse system over F_p whose row span contains reduction rows
I_t = sum_m c[m] I_m for every non-master column t, then recovers the
multipliers lam by Gauss-Jordan elimination with a tracked transform. The
output is RECEIPT v1.0 JSON written from the spec, used for scale and Lean tests.
"""
from __future__ import annotations

import json
import os
import random


def _axpy(dst: dict, src: dict, a: int, p: int) -> None:
    for k, v in src.items():
        x = (dst.get(k, 0) + a * v) % p
        if x:
            dst[k] = x
        else:
            dst.pop(k, None)


def make_system(seed: int, p: int, n_int: int, n_master: int, density: int = 3,
                n_extra: int = 0):
    """Return (rows, masters, truth) with truth[t] = {m: c} for non-masters."""
    rng = random.Random(seed)
    masters = list(range(n_int - n_master, n_int))
    truth = {}
    base = []
    for t in range(n_int - n_master):
        ms = rng.sample(masters, min(density, len(masters)))
        c = {m: rng.randrange(1, p) for m in ms}
        truth[t] = c
        row = {t: 1}
        for m, cm in c.items():
            row[m] = (-cm) % p
        base.append(row)
    # Mix: each published row = base row + random multiples of other base rows.
    rows = []
    for i, b in enumerate(base):
        r = dict(b)
        for j in rng.sample(range(len(base)), min(2, len(base))):
            if j != i:
                _axpy(r, base[j], rng.randrange(1, p), p)
        rows.append(r)
    for _ in range(n_extra):  # redundant rows (consequences), as real IBP systems have
        r: dict = {}
        for j in rng.sample(range(len(base)), min(3, len(base))):
            _axpy(r, rows[j], rng.randrange(1, p), p)
        rows.append(r)
    rng.shuffle(rows)
    return rows, masters, truth


def solve_witnesses(rows, masters, p):
    """Gauss-Jordan on non-master columns; return {t: (c, lam)}."""
    master_set = set(masters)
    work = [(dict(r), {i: 1}) for i, r in enumerate(rows)]
    pivots = {}  # col -> (row, transform)
    for r, tr in work:
        for col, (prow, ptr) in pivots.items():
            if col in r:
                a = (-r[col]) % p
                _axpy(r, prow, a, p)
                _axpy(tr, ptr, a, p)
        cand = sorted(k for k in r if k not in master_set)
        if not cand:
            continue
        col = cand[0]
        inv = pow(r[col], -1, p)
        r = {k: v * inv % p for k, v in r.items()}
        tr = {k: v * inv % p for k, v in tr.items()}
        for c2, (prow, ptr) in list(pivots.items()):
            if col in prow:
                a = (-prow[col]) % p
                _axpy(prow, r, a, p)
                _axpy(ptr, tr, a, p)
        pivots[col] = (r, tr)
    out = {}
    for col, (r, tr) in pivots.items():
        if any(k not in master_set and k != col for k in r):
            continue
        c = {m: (-v) % p for m, v in r.items() if m != col}
        out[col] = (c, tr)
    return out


def witness_json(p, t, c, lam, n_rows, point=None):
    idx = sorted(lam)
    return {"receipt_version": "1.0", "kind": "lambda-witness",
            "identity": "sum_i lam[i]*R_i == e_target - sum_m c[m]*e_m (mod p)",
            "p": p, "point": point or {}, "family": "synthetic",
            "target": {"col": t}, "c": {str(m): v for m, v in sorted(c.items())},
            "lam": {"n_rows": n_rows, "idx": idx, "val": [lam[i] for i in idx]},
            "system": {"n_rows": n_rows, "source": "second_checker.synth"}}


def write_family(out_dir, seed, p, n_int, n_master, n_extra=0):
    os.makedirs(out_dir, exist_ok=True)
    rows, masters, truth = make_system(seed, p, n_int, n_master, n_extra=n_extra)
    with open(os.path.join(out_dir, "system.jsonl"), "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps({str(k): v for k, v in sorted(r.items())}) + "\n")
    wits = solve_witnesses(rows, masters, p)
    wdir = os.path.join(out_dir, "wits")
    os.makedirs(wdir, exist_ok=True)
    table = {}
    for t, (c, lam) in sorted(wits.items()):
        table[str(t)] = {str(m): v for m, v in sorted(c.items())}
        with open(os.path.join(wdir, f"w_synthetic_{p}_{t}.json"), "w", encoding="utf-8") as fh:
            json.dump(witness_json(p, t, c, lam, len(rows)), fh)
    with open(os.path.join(out_dir, "table.json"), "w", encoding="utf-8") as fh:
        json.dump(table, fh, sort_keys=True)
    agree = all({m: v for m, v in wits[t][0].items()} == truth[t] for t in wits if t in truth)
    return {"n_rows": len(rows), "n_witnesses": len(wits), "matches_truth": agree}
