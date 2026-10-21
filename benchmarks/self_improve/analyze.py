"""Analyze a ledger-quirks head-to-head run against its frozen preregistration.

    python benchmarks/self_improve/analyze.py --run runs/si-h2h --out results.json

Primary endpoint: test-phase accuracy, flywheel_gated minus harness2_c0.50,
paired by (seed, test task), 95% interval from a cluster bootstrap that
resamples seeds and then tasks within a seed (harness.statistics). The decision
rule is applied mechanically and printed beside the numbers.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness.statistics import cluster_bootstrap  # noqa: E402

PRIMARY = ("flywheel_gated", "harness2_c0.50")
CONTRASTS = (PRIMARY, ("flywheel_gated", "harness2_c1.00"),
             ("flywheel_gated", "flywheel_ungated"), ("flywheel_gated", "base"),
             ("harness2_c0.50", "base"), ("flywheel_gated_incumbent", "harness2_c0.50"))


def load(run: Path) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(run.glob("s*.json"))]


def _key(cell: dict) -> tuple:
    return (cell["p_game"], cell["mode"], cell["k"])


def delta(docs: list[dict], a: str, b: str, phase: str) -> dict:
    clusters: dict[str, list[float]] = defaultdict(list)
    for doc in docs:
        rows = {(r["arm"], r["task_id"]): r for r in doc["rows"] if r["phase"] == phase}
        for (arm, tid), r in rows.items():
            if arm == a and (b, tid) in rows:
                clusters[str(doc["cell"]["seed"])].append(r["score"] - rows[(b, tid)]["score"])
    if len(clusters) < 2:
        return {"a": a, "b": b, "n": sum(map(len, clusters.values())), "point": None}
    boot = cluster_bootstrap(clusters, lambda u: sum(u) / len(u), draws=4000, seed=7,
                             alpha=0.05)
    return {"a": a, "b": b, "n": sum(map(len, clusters.values())),
            "seeds": len(clusters), "point": boot["point"], "ci95": boot["interval"]}


def arm_means(docs: list[dict], phase: str) -> dict:
    acc: dict[str, list] = defaultdict(list)
    for doc in docs:
        for r in doc["rows"]:
            if r["phase"] == phase:
                acc[r["arm"]].append(r)
    return {arm: {"accuracy": round(sum(r["score"] for r in rs) / len(rs), 4),
                  "poisoned": round(sum(r["poisoned"] for r in rs) / len(rs), 4),
                  "executions_per_task": round(sum(r["executions"] for r in rs) / len(rs), 2),
                  "n": len(rs)} for arm, rs in sorted(acc.items())}


def decide(table: dict) -> dict:
    """The preregistered rule, applied to the primary contrast."""
    verdict = {}
    for p in sorted({key[0] for key in table}):
        lows = [table[key]["test"]["contrasts"][0]["ci95"][0]
                for key in table if key[0] == p]
        if p == 0.0:
            verdict[p] = "NON-INFERIOR" if all(lo > -0.05 for lo in lows) else "INFERIOR"
        else:
            verdict[p] = "WIN" if sum(lo > 0 for lo in lows) >= 2 else "NO WIN"
    overall = (verdict.get(0.0) == "NON-INFERIOR"
               and all(v == "WIN" for p, v in verdict.items() if p > 0))
    return {"by_rate": verdict, "flywheel_better_on_this_benchmark": overall}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)
    docs = load(args.run)
    by: dict[tuple, list] = defaultdict(list)
    for doc in docs:
        by[_key(doc["cell"])].append(doc)
    table = {key: {phase: {"arms": arm_means(ds, phase),
                           "contrasts": [delta(ds, a, b, phase) for a, b in CONTRASTS]}
                   for phase in ("stream", "test")} for key, ds in sorted(by.items())}
    controls = [d["controls"] for d in docs]
    result = {"cells": len(docs),
              "table": {f"p={k[0]:.2f} {k[1]} k={k[2]}": v for k, v in table.items()},
              "controls_fit": sum(c["verdict"] == "FIT" for c in controls),
              "controls_total": len(controls),
              "controls_false_accepts": sorted({n for c in controls for n in c["false_accepts"]}),
              "controls_false_rejects": sorted({n for c in controls for n in c["false_rejects"]}),
              "decision": decide(table)}
    args.out.write_text(json.dumps(result, indent=1, sort_keys=True), encoding="utf-8")
    print(json.dumps(result["decision"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
