"""effort_gate_replay.py -- measure the search effort gate on recorded runs, no model needed.

Two input shapes:
  G4 records  (schema flywheel.heldout-rerun/v1): first sample and result only;
              replays the first-pass gate.
  logged runs (schema flywheel.effort-gate-log/v1): every candidate's visible and
              held-out verdict; replays every gate exactly by truncation.

  python scripts/effort_gate_replay.py project-docs/records/1.3.0/g4-heldout-rerun/hard_v2.json
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.search_gate import replay_logged, replay_record  # noqa: E402

K = 4
BAR_RETAINED, BAR_RATIO = 0.90, 0.50


def outcomes(doc: dict, gate: str) -> list[dict]:
    """One row per problem: single, search and gated held-out pass, gated draws."""
    rows = [r for r in doc["rows"] if "excluded" not in r]
    out = []
    for r in rows:
        if doc["schema"] == "flywheel.effort-gate-log/v1":
            g = replay_logged(gate, r["visible"], r["held"])
            full = replay_logged("off", r["visible"], r["held"])
            out.append({"id": r["task_id"], "single": bool(r["single_held"]),
                        "search": full["held"], "gated": g["held"],
                        "draws": g["draws"], "k": len(r["visible"]), "consistent": True})
        else:
            g = replay_record(gate, r, K)
            out.append({"id": r["task_id"], "single": bool(r["single_held"]),
                        "search": bool(r["search_held"]), "gated": g["held"],
                        "draws": g["draws"], "k": K, "consistent": g["consistent"]})
    return out


def point(rows: list[dict]) -> dict:
    single = sum(r["single"] for r in rows)
    search = sum(r["search"] for r in rows)
    gated = sum(r["gated"] for r in rows)
    gain = search - single
    return {"n": len(rows), "single": single, "search": search, "gated": gated,
            "search_gain": gain,
            "retained": round((gated - single) / gain, 4) if gain else None,
            "draws": sum(r["draws"] for r in rows), "search_draws": sum(r["k"] for r in rows),
            "sample_ratio": round(sum(r["draws"] for r in rows) / sum(r["k"] for r in rows), 4)
            if rows else None}


def bootstrap(rows: list[dict], iters: int = 10000, seed: int = 7) -> dict:
    rng, n = random.Random(seed), len(rows)
    diffs, kept, ratios, zero = [], [], [], 0
    for _ in range(iters):
        sample = [rows[rng.randrange(n)] for _ in range(n)]
        p = point(sample)
        diffs.append((p["gated"] - p["search"]) / n)
        ratios.append(p["sample_ratio"])
        if p["retained"] is None:
            zero += 1
        else:
            kept.append(p["retained"])
    diffs.sort()
    kept.sort()
    ratios.sort()
    lo = lambda xs: round(xs[int(0.025 * len(xs))], 4) if xs else None  # noqa: E731
    hi = lambda xs: round(xs[int(0.975 * len(xs)) - 1], 4) if xs else None  # noqa: E731
    return {"gated_minus_search_95": [lo(diffs), hi(diffs)],
            "retained_95": [lo(kept), hi(kept)], "sample_ratio_95": [lo(ratios), hi(ratios)],
            "resamples_zero_gain": zero}


def halves(rows: list[dict], seed: int = 7) -> list[list[dict]]:
    ids = sorted(r["id"] for r in rows)
    random.Random(seed).shuffle(ids)
    first = set(ids[: len(ids) // 2])
    return [[r for r in rows if r["id"] in first], [r for r in rows if r["id"] not in first]]


def verdict(p: dict) -> str:
    if p["retained"] is None:
        return "UNDEFINED (search gain is zero)"
    ok = p["retained"] >= BAR_RETAINED and p["sample_ratio"] <= BAR_RATIO
    return "MEETS BAR" if ok else "MISSES BAR"


def report(doc: dict, gate: str) -> dict:
    rows = outcomes(doc, gate)
    p = point(rows)
    return {"registry": doc.get("registry"), "schema": doc["schema"], "gate": gate,
            "bar": {"retained_min": BAR_RETAINED, "sample_ratio_max": BAR_RATIO},
            "point": p, "verdict": verdict(p), "bootstrap": bootstrap(rows),
            "halves": [dict(point(h), verdict=verdict(point(h))) for h in halves(rows)],
            "inconsistent_rows": [r["id"] for r in rows if not r["consistent"]]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("records", nargs="+")
    ap.add_argument("--gate", default="first-pass", choices=("first-pass", "sequential"))
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    reports = [report(json.loads(Path(f).read_text(encoding="utf-8")), a.gate)
               for f in a.records]
    text = json.dumps(reports, indent=1)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
