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


def vectors_from_uplift(doc: dict) -> list:
    """Reconstruct exact candidate sequences from an uplift artifact's
    censored per-task records. The wrapped arm samples until first pass or
    budget, so outcome+attempts determines the sequence exactly: a pass at
    attempt m is m-1 real failures then one success; a fail at attempt m is
    m real failures. Only the wrapped arm is used (one sampling policy)."""
    rows = []
    for arm in doc.get("rows", []):
        if arm.get("arm") != "wrapped":
            continue
        for t in arm.get("tasks", []):
            m = int(t.get("attempts", 0))
            if m < 1:
                continue
            outcome = t.get("outcome")
            if outcome not in ("pass", "fail"):
                # the bench's oracle refused to dispose this task; dropping it
                # matches the bench's own exclusion. Recoding it as m failures
                # would seal a fabricated outcome into the forecast.
                continue
            c = 1 if outcome == "pass" else 0
            rows.append({"task_id": t["task_id"], "n": m, "c": c})
    return rows


def _fresh_q(n: int, c: int, k: int) -> float:
    """P(>=1 success in k FRESH draws) under the Jeffreys posterior --
    the forecast framing for a run that has not happened, as opposed to
    pass_at_k's keep-the-pool framing."""
    a, b = _A0 + c, _B0 + (n - c)
    return max(0.0, 1.0 - _betabinom_pmf(0, k, a, b))


def forecast_fresh_run(rows: list, k: int, *, source: str = "") -> dict:
    """Seal a forecast for a fresh best-of-k run over these tasks, before
    any such run exists. Per task q_i marginalizes the posterior, so
    Var(X_i) = q_i(1-q_i) exactly; tasks are treated independent (stated).
    The iid pooled baseline rides inside the same sealed artifact, so
    adjudication compares two pre-registered models instead of letting the
    survivor pick its rival after the fact."""
    import hashlib
    per = [{"task_id": r["task_id"], "n": r["n"], "c": r["c"],
            "q": round(_fresh_q(r["n"], r["c"], k), 6)} for r in rows]
    T = len(per)
    mean = sum(t["q"] for t in per) / T
    sd = (sum(t["q"] * (1 - t["q"]) for t in per)) ** 0.5 / T
    pooled_n = sum(r["n"] for r in rows)
    pooled_c = sum(r["c"] for r in rows)
    pooled_p = pooled_c / pooled_n if pooled_n else 0.0
    doc = {"schema": "flywheel.passk-forecast/v1", "k": k,
           "source_artifact": source, "n_tasks": T,
           "expected_pass_rate": round(mean, 4),
           "interval_95": [round(max(0.0, mean - 1.96 * sd), 4),
                           round(min(1.0, mean + 1.96 * sd), 4)],
           "per_task": per,
           "iid_baseline": {
               "pooled_p": pooled_p,
               "expected_pass_rate": round(1.0 - (1.0 - pooled_p) ** k, 4)},
           "note": "sealed before any such run exists; fresh-draw framing "
                   "(not keep-the-pool); tasks independent by assumption; "
                   "adjudicate BOTH this and the iid baseline against the "
                   "real run -- whichever errs more is the falsified one"}
    doc["seal"] = hashlib.sha256(
        json.dumps(doc, sort_keys=True).encode()).hexdigest()
    return doc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--curve", default="", help="pass@N artifact JSON")
    ap.add_argument("--out", default="", help="write the expected-curve JSON")
    ap.add_argument("--ks", default="", help="comma list of k to report (default 1,2,4,8,16,32,64)")
    ap.add_argument("--calibrate", type=int, default=0,
                    help="fit p on first N_train candidates, test on full pool")
    ap.add_argument("--forecast-uplift", default="",
                    help="uplift artifact: seal a fresh best-of-k forecast")
    ap.add_argument("--forecast-k", type=int, default=5)
    args = ap.parse_args()

    if args.forecast_uplift:
        src = Path(args.forecast_uplift)
        rows = vectors_from_uplift(json.loads(src.read_text(encoding="utf-8")))
        if not rows:
            print("no wrapped-arm task records in the artifact")
            return 2
        f = forecast_fresh_run(rows, args.forecast_k, source=src.name)
        outdir = Path("artifacts/forecasts")
        outdir.mkdir(parents=True, exist_ok=True)
        path = outdir / f"forecast_k{args.forecast_k}_{src.stem}.json"
        path.write_text(json.dumps(f, indent=1), encoding="utf-8")
        print(f"sealed forecast: expected {f['expected_pass_rate']:.1%} "
              f"[{f['interval_95'][0]:.1%}, {f['interval_95'][1]:.1%}] "
              f"at k={args.forecast_k} over {f['n_tasks']} tasks")
        print(f"iid baseline:    {f['iid_baseline']['expected_pass_rate']:.1%}")
        print(f"seal {f['seal']}")
        print(f"wrote {path}")
        return 0

    if not args.curve:
        print("provide --curve or --forecast-uplift")
        return 2
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
