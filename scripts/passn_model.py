"""passn_model.py -- exact pass@k and consensus-reachable@k curves from a pool.

Given a pass@N artifact where each task has n candidates with c correct (scored
by the hidden oracle), this computes the UNBIASED expected metrics for any
budget k <= n, without an iid assumption:

  pass@k          = 1 - C(n-c, k)/C(n, k)              (Chen et al. 2021)
  consensus@k     = P(>=2 of a random k-subset are correct)
                  = 1 - P(0 correct) - P(1 correct)
                  = 1 - C(n-c,k)/C(n,k) - c*C(n-c,k-1)/C(n,k)

pass@k is the perfect-external-oracle ceiling; consensus@k is the ceiling for
ANY oracle-free selector (it needs >=2 agreeing-correct to have a chance). The
gap between them is the irreducible cost of not having a ground-truth oracle.

For k > n (extrapolation past the measured pool) it falls back to a per-task
binomial with p_hat = c/n and flags the rows as EXTRAPOLATED (iid assumption,
weaker). The within-pool curve (k <= n) is exact and assumption-light.

A held-out calibration mode fits p on the first n_train candidates and predicts
the observed metrics on the full pool -- a falsifier for the binomial model.
"""
from __future__ import annotations

import argparse
import json
import sys
from math import comb, lgamma, exp
from pathlib import Path

# Jeffreys prior for the per-task success rate: Beta(0.5, 0.5). A task that
# shows 0 correct in n draws is NOT assumed to have p=0 forever (topo_sort went
# 0/8 -> 3/16); the posterior admits it might wake up at higher N.
_A0 = 0.5
_B0 = 0.5


def _log_beta(a: float, b: float) -> float:
    return lgamma(a) + lgamma(b) - lgamma(a + b)


def _betabinom_pmf(x: int, k: int, a: float, b: float) -> float:
    """Beta-Binomial P(X=x) for k trials, posterior Beta(a,b)."""
    return comb(k, x) * exp(_log_beta(x + a, k - x + b) - _log_beta(a, b))


def pass_at_k(n: int, c: int, k: int) -> float:
    """P(>=1 correct at budget k), operationally "raise N": KEEP the observed
    pool of n (c correct) and generate k-n more. Exact hypergeometric for k<=n
    (conditions on the pool); for k>n, if c>=1 we already hold a success (=1.0),
    else Beta-Binomial posterior predictive over the k-n fresh draws. Monotonic
    in k by construction -- you never lose the candidates you already have."""
    if k <= n:
        if c <= 0:
            return 0.0
        if n - c < k:
            return 1.0
        return 1.0 - comb(n - c, k) / comb(n, k)
    if c >= 1:
        return 1.0
    m = k - n
    a, b = _A0 + c, _B0 + (n - c)
    return max(0.0, 1.0 - _betabinom_pmf(0, m, a, b))


def consensus_at_k(n: int, c: int, k: int) -> float:
    """P(>=2 correct at budget k) -- the oracle-free ceiling, "raise N" framing.
    Exact hypergeometric for k<=n; for k>n, keep the c correct in hand and need
    the rest from the k-n fresh draws (Beta-Binomial posterior predictive)."""
    if k < 2:
        return 0.0
    if k <= n:
        if c < 2:
            return 0.0
        tot = comb(n, k)
        p0 = comb(n - c, k) / tot if n - c >= k else 0.0
        p1 = c * comb(n - c, k - 1) / tot if n - c >= k - 1 else 0.0
        return max(0.0, 1.0 - p0 - p1)
    if c >= 2:
        return 1.0
    m = k - n
    a, b = _A0 + c, _B0 + (n - c)
    if c == 1:                        # hold 1, need >=1 more from the fresh draws
        return max(0.0, 1.0 - _betabinom_pmf(0, m, a, b))
    # c == 0: need >=2 correct in the k-n fresh draws
    return max(0.0, 1.0 - _betabinom_pmf(0, m, a, b) - _betabinom_pmf(1, m, a, b))


def load_rows(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("per_task", [])
    out = []
    for r in rows:
        passes = r.get("passes")
        if passes is None and "hidden_pass" in r:
            passes = r["hidden_pass"]
        if passes is None:
            continue
        out.append({"task_id": r["task_id"], "n": len(passes), "c": sum(bool(x) for x in passes)})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--curve", required=True, help="pass@N artifact JSON")
    ap.add_argument("--out", default="", help="write the expected-curve JSON")
    ap.add_argument("--ks", default="", help="comma list of k to report (default 1,2,4,8,16,32,64)")
    ap.add_argument("--calibrate", type=int, default=0,
                    help="fit p on first N_train candidates, test on full pool")
    args = ap.parse_args()

    rows = load_rows(Path(args.curve))
    if not rows:
        print("no per-task rows with candidate passes found")
        return 1
    n_min = min(r["n"] for r in rows)
    T = len(rows)

    ks = [int(x) for x in args.ks.split(",")] if args.ks else [1, 2, 4, 8, 16, 32, 64]

    print(f"=== Exact pass@k / consensus@k curve ({T} tasks, pool size {n_min}) ===\n")
    print(f"  {'k':>3}  {'pass@k (oracle ceiling)':>26}  {'consensus@k (oracle-free)':>26}  {'gap':>6}")
    curve = {}
    for k in ks:
        exact = k <= n_min
        pass_exp = sum(pass_at_k(r["n"], r["c"], k) for r in rows) / T
        cons_exp = sum(consensus_at_k(r["n"], r["c"], k) for r in rows) / T
        gap = pass_exp - cons_exp
        tag = "" if exact else " (posterior-predictive, Jeffreys)"
        curve[str(k)] = {
            "pass_at_k_expected": round(pass_exp, 4),
            "consensus_at_k_expected": round(cons_exp, 4),
            "gap": round(gap, 4),
            "exact": exact,
        }
        print(f"  {k:>3}  {pass_exp:>24.1%}  {cons_exp:>24.1%}  {gap:>5.1%}{tag}")

    # Where does consensus-reachable plateau? Report the marginal gain per doubling.
    print(f"\n=== Marginal consensus-reachable gain per doubling ===")
    prev = None
    for k in [1, 2, 4, 8, 16, 32]:
        if k > n_min:
            break
        cons = sum(consensus_at_k(r["n"], r["c"], k) for r in rows) / T
        if prev is not None:
            print(f"  {prev[0]:>2} -> {k:>2}:  {cons - prev[1]:+.1%}  (now {cons:.1%})")
        prev = (k, cons)

    if args.calibrate and 2 * args.calibrate <= n_min:
        nt = args.calibrate
        print(f"\n=== Held-out falsifier: train on first {nt}, predict held-out next {nt} (fresh draws) ===")
        # A proper train/test split: fit the Jeffreys posterior on candidates
        # [0:nt], predict P(>=1) and P(>=2) over a FRESH budget of nt, and score
        # against the ACTUAL held-out block [nt:2nt] (independent fresh draws --
        # different temp/seed pairs). This is non-trivial (unlike predicting the
        # pool that CONTAINS the training block) and is the pre-registered test
        # of whether the model's k>n extrapolation can be trusted.
        data = json.loads(Path(args.curve).read_text(encoding="utf-8"))
        pred_pass = pred_cons = obs_pass = obs_cons = 0.0
        Tn = 0
        for r in data["per_task"]:
            passes = r.get("passes") or r.get("hidden_pass")
            if not passes or len(passes) < 2 * nt:
                continue
            Tn += 1
            train = [bool(x) for x in passes[:nt]]
            test = [bool(x) for x in passes[nt:2 * nt]]
            c_train = sum(train)
            a, b = _A0 + c_train, _B0 + (nt - c_train)
            pred_pass += 1.0 - _betabinom_pmf(0, nt, a, b)
            pred_cons += max(0.0, 1.0 - _betabinom_pmf(0, nt, a, b) - _betabinom_pmf(1, nt, a, b))
            obs_pass += 1.0 if sum(test) >= 1 else 0.0
            obs_cons += 1.0 if sum(test) >= 2 else 0.0
        if Tn == 0:
            print("  (no tasks with >= 2*nt candidates)")
        else:
            e_pass = abs(pred_pass - obs_pass) / Tn
            e_cons = abs(pred_cons - obs_cons) / Tn
            print(f"  pass@{nt}:      predicted {pred_pass/Tn:.1%}  observed {obs_pass/Tn:.1%}  err {e_pass:.1%}")
            print(f"  consensus@{nt}: predicted {pred_cons/Tn:.1%}  observed {obs_cons/Tn:.1%}  err {e_cons:.1%}")
            print(f"  VERDICT: model {'CALIBRATED' if e_cons < 0.05 else 'MISCALIBRATED'} "
                  f"on consensus (5% tolerance); {'CALIBRATED' if e_pass < 0.05 else 'MISCALIBRATED'} on pass "
                  f"(N={Tn} tasks)")

    if args.out:
        report = {
            "schema": "flywheel.passn_model/v1",
            "n_tasks": T, "pool_size": n_min,
            "curve": curve,
            "note": "pass@k and consensus@k are expected values over tasks under the 'keep the pool, generate k-n more' framing; k<=pool are exact hypergeometric, k>pool are Jeffreys Beta-Binomial posterior predictive over the fresh tail",
        }
        Path(args.out).write_text(json.dumps(report, indent=1), encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
