"""analyze_selectors.py -- deep analysis of selector comparison results.

Reads the consensus ablation artifact and produces:
1. Structural breakdown: why consensus misses what external catches
2. Feasibility ceiling: what fraction of lift is structurally reachable
3. Task-level detail on every rescue and miss
4. Actionable recommendations for the next instrument
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return (max(0, center - spread), min(1, center + spread))


def mcnemar(b: int, c: int) -> tuple[float, float]:
    if b + c == 0:
        return (0.0, 1.0)
    chi2 = (abs(b - c) - 1) ** 2 / (b + c)
    from math import erfc, sqrt
    p = erfc(sqrt(chi2 / 2))
    return (chi2, p)


def main():
    if len(sys.argv) < 2:
        print("Usage: analyze_selectors.py <artifact.json>")
        return 1

    path = Path(sys.argv[1])
    if path.suffix == ".jsonl":
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        data = {"per_task": rows, "n_tasks": len(rows)}
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data.get("per_task", [])

    n = len(rows)
    print(f"=== Selector Analysis ({n} tasks) ===\n")

    n_single = sum(1 for r in rows if r["single"])
    n_ext = sum(1 for r in rows if r["ext"])
    n_self = sum(1 for r in rows if r.get("self", False))
    n_cons = sum(1 for r in rows if r.get("cons", False))

    ext_lo, ext_hi = wilson_ci(n_ext, n)
    cons_lo, cons_hi = wilson_ci(n_cons, n)

    print("--- Pass rates (Wilson 95% CI) ---")
    print(f"  single:    {n_single}/{n} = {n_single/n:.1%}  [{wilson_ci(n_single,n)[0]:.1%}, {wilson_ci(n_single,n)[1]:.1%}]")
    print(f"  external:  {n_ext}/{n} = {n_ext/n:.1%}  [{ext_lo:.1%}, {ext_hi:.1%}]")
    print(f"  self:      {n_self}/{n} = {n_self/n:.1%}  [{wilson_ci(n_self,n)[0]:.1%}, {wilson_ci(n_self,n)[1]:.1%}]")
    print(f"  consensus: {n_cons}/{n} = {n_cons/n:.1%}  [{cons_lo:.1%}, {cons_hi:.1%}]")

    # McNemar: consensus vs single
    b_cons = sum(1 for r in rows if r.get("cons") and not r["single"])
    c_cons = sum(1 for r in rows if not r.get("cons") and r["single"])
    chi2_c, p_c = mcnemar(b_cons, c_cons)
    print(f"\n--- McNemar (consensus vs single) ---")
    print(f"  rescued by consensus: {b_cons}, lost: {c_cons}")
    print(f"  chi2={chi2_c:.3f}, p={p_c:.4f} {'SIGNIFICANT' if p_c < 0.05 else 'not significant'}")

    # McNemar: external vs consensus
    b_ec = sum(1 for r in rows if r["ext"] and not r.get("cons"))
    c_ec = sum(1 for r in rows if not r["ext"] and r.get("cons"))
    chi2_ec, p_ec = mcnemar(b_ec, c_ec)
    print(f"\n--- McNemar (external vs consensus) ---")
    print(f"  external wins: {b_ec}, consensus wins: {c_ec}")
    print(f"  chi2={chi2_ec:.3f}, p={p_ec:.4f} {'SIGNIFICANT gap' if p_ec < 0.05 else 'not significant'}")

    # Structural breakdown
    rescued_ext = [r for r in rows if r["ext"] and not r["single"]]
    n_rescued = len(rescued_ext)
    print(f"\n--- Structural breakdown of {n_rescued} external-oracle rescues ---")

    cc_dist = {}
    for r in rescued_ext:
        cc = r.get("correct_count", sum(r.get("hidden_pass", [])))
        cc_dist.setdefault(cc, []).append(r["task_id"])

    for cc in sorted(cc_dist.keys()):
        tasks = cc_dist[cc]
        reachable = "CONSENSUS-REACHABLE" if cc >= 2 else "ORACLE-ONLY"
        cons_hit = sum(1 for tid in tasks if any(r.get("cons") for r in rows if r["task_id"] == tid))
        print(f"  correct_count={cc}: {len(tasks)} tasks ({reachable}), consensus captured {cons_hit}/{len(tasks)}")
        for tid in tasks:
            r = next(rr for rr in rows if rr["task_id"] == tid)
            hp = r.get("hidden_pass", [])
            print(f"    {tid}: hidden_pass={hp} cons={'PASS' if r.get('cons') else 'FAIL'}")

    # Feasibility ceiling
    reachable = sum(1 for r in rescued_ext if r.get("correct_count", 0) >= 2)
    captured = sum(1 for r in rescued_ext if r.get("cons"))
    print(f"\n--- Oracle-free feasibility ---")
    print(f"  External rescues: {n_rescued}")
    print(f"  Consensus-reachable ceiling (>=2 correct): {reachable}/{n_rescued}")
    print(f"  Actually captured by consensus: {captured}/{reachable if reachable else 1}")
    print(f"  Fraction of external lift recovered: {(n_cons - n_single)}/{n_ext - n_single} = {(n_cons - n_single)/(n_ext - n_single):.1%}" if n_ext > n_single else "  no lift to recover")

    # Total correct_count distribution
    print(f"\n--- correct_count distribution (all {n} tasks) ---")
    all_cc = {}
    for r in rows:
        cc = r.get("correct_count", sum(r.get("hidden_pass", [])))
        all_cc[cc] = all_cc.get(cc, 0) + 1
    for cc in sorted(all_cc.keys()):
        pct = all_cc[cc] / n
        bar = "#" * int(pct * 40)
        print(f"  {cc}: {all_cc[cc]:3d} ({pct:5.1%}) {bar}")

    # Timing summary
    gen_total = sum(r.get("gen_s", 0) for r in rows)
    ver_total = sum(r.get("ver_s", 0) for r in rows)
    print(f"\n--- Compute ---")
    print(f"  Generation: {gen_total:.0f}s ({gen_total/60:.1f}m)")
    print(f"  Verification: {ver_total:.0f}s ({ver_total/60:.1f}m)")
    print(f"  Total: {(gen_total+ver_total)/60:.1f}m for {n} tasks")

    # Recommendations
    print(f"\n--- Actionable next steps ---")
    if reachable and captured < reachable:
        miss_rate = 1 - captured / reachable
        print(f"  1. IMPROVE CONSENSUS SELECTOR: {miss_rate:.0%} miss rate on reachable tasks")
        print(f"     The battery may not exercise the right input types for these tasks.")
    if n_rescued > reachable:
        oracle_only = n_rescued - reachable
        print(f"  2. INCREASE N: {oracle_only}/{n_rescued} rescues have only 1 correct candidate.")
        print(f"     At N=4, these are structurally unreachable by any oracle-free method.")
        print(f"     Run pass@N curve (N=8,16) to see if doubling candidates unlocks majority-correct.")
    print(f"  3. HYBRID SELECTOR: consensus when cc>=2, self-test fallback when cc=1.")
    print(f"     Self-test is 70% broken, but the 30% working cases might rescue a few oracle-only tasks.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
