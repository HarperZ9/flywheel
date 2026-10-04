"""Recompute a Shapley placebo verdict from its recorded model outputs.

Level 2 (recomputation) for the claim on docs/features/shapley-placebo.md:
the recorded outputs, scored with the preregistered module, give the recorded
values, trials, counts and verdict. No model and no GPU are needed.

    python scripts/shapley_placebo_recompute.py --root <checkout> \
        --run project-docs/records/2026-10-04-shapley-placebo/run-qwen2.5-7b.json

``--root`` is a checkout at the run's commit. The scoring module is imported
from that checkout, so the recompute uses the preregistered code, not the
code beside this script. That also bounds what it shows: it confirms the
arithmetic, not an independent implementation, and it reaches the outputs the
run recorded, not whether a rerun of the model would give them.

Exit codes: 0 MATCH, 1 DRIFT, 2 UNVERIFIABLE.
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

ITEMS = "project-docs/records/2026-10-04-shapley-placebo/items-v1.json"


def recompute(root: Path, run_rel: str, items_rel: str = ITEMS) -> tuple[str, list[str]]:
    sys.path.insert(0, str(root))
    sf = importlib.import_module("harness.shapley_far")
    items = json.loads((root / items_rel).read_text(encoding="utf-8"))
    run = json.loads((root / run_rel).read_text(encoding="utf-8"))
    problems: list[str] = []
    trials = []
    for item, row in zip(items["items"], run["runs"]):
        values = [sf.answer_value(o, item["accepted"]) for o in row["outputs"]]
        if values != row.get("values", values):
            problems.append(f"{item['item_id']}: recorded values differ from rescored outputs")
        trials += sf.item_trials(item, values)
    analysis = sf.analyze(trials, sf.manifest("recheck", run["witness"]))
    got, want = analysis["false_attribution"], run["analysis"]["false_attribution"]
    print(f"recomputed: {analysis['verdict']}, false attribution {got['k']} of {got['n']}, "
          f"interval {got['lower']} to {got['upper']}")
    print(f"recorded:   {run['analysis']['verdict']}, false attribution {want['k']} of {want['n']}")
    if analysis["verdict"] != run["analysis"]["verdict"]:
        problems.append("verdict differs")
    for key in ("k", "n", "lower", "upper"):
        if got[key] != want[key]:
            problems.append(f"false_attribution.{key} differs")
    return ("MATCH" if not problems else "DRIFT"), problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--run", required=True, help="run record, relative to --root")
    ap.add_argument("--items", default=ITEMS, help="item set, relative to --root")
    a = ap.parse_args(argv)
    try:
        verdict, problems = recompute(a.root.resolve(), a.run, a.items)
    except (OSError, KeyError, ValueError, ImportError) as exc:
        print(f"UNVERIFIABLE: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    for p in problems:
        print(f"  problem: {p}")
    print(f"verdict: {verdict}")
    return 0 if verdict == "MATCH" else 1


if __name__ == "__main__":
    raise SystemExit(main())
