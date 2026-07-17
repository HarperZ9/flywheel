"""Sweep the forge's whole grammar through the live Lean kernel.

Every enumerable conjecture is proposed exactly once (offsets advance, so
refusals are never re-judged), the kernel disposes, survivors chain into
the store, and one artifact carries the round receipts plus the sweep
totals. Usage:

  python scripts/run_conjecture_sweep.py [--batch 50] [--out artifacts/invention]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.conjecture_forge import SCHEMA, _all_statements, forge_round  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=50)
    ap.add_argument("--out", default="artifacts/invention")
    a = ap.parse_args()
    total = len(_all_statements())
    rounds = []
    t0 = time.time()
    for offset in range(0, total, a.batch):
        r = forge_round(a.batch, offset=offset)
        rounds.append({"offset": offset, "proposed": r["proposed"],
                       "accepted": len(r["accepted"]),
                       "refused": r["refused"], "declared": r["declared"]})
        print(f"offset {offset}: +{len(r['accepted'])} accepted, "
              f"{r['refused']} refused, {r['declared']} declared",
              flush=True)
        if r["declared"]:
            print("kernel DECLARED; stopping honestly", flush=True)
            break
    doc = {"schema": SCHEMA + ".sweep", "grammar_size": total,
           "batch": a.batch, "rounds": rounds,
           "accepted_total": sum(r["accepted"] for r in rounds),
           "refused_total": sum(r["refused"] for r in rounds),
           "declared_total": sum(r["declared"] for r in rounds),
           "wall_seconds": round(time.time() - t0, 1),
           "note": "every statement proposed once; acceptance decided "
                   "solely by the Lean kernel; survivors are in the store "
                   "under kind='theorem'"}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = out / f"conjecture_sweep_{stamp}.json"
    path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"sweep artifact: {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
