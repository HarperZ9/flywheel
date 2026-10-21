"""Run the ledger-quirks head-to-head: Flywheel's loop against Harness-squared as released.

Usage (POSIX; harness2 imports fcntl):

    python3.12 benchmarks/self_improve/run_headtohead.py \
        --h2-root /path/to/harness2 --out runs/si-h2h

Each cell (seed, gaming rate, mode, k) writes one JSON file under --out and is
skipped on a rerun, so an interrupted run resumes where it stopped. The
parameters below are the frozen preregistration's; changing them is a new
experiment and needs a new --out. The v1 preregistration ran seeds 0..5 with
the arms flywheel_gated and flywheel_ungated (now flywheel_v1 and
flywheel_ungated); the v2 preregistration runs seeds 200..205.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent.parent)]

from harness import self_improve_bench as bench  # noqa: E402

import flywheel_arm  # noqa: E402

CONFIGS = (("parallel", 1), ("parallel", 2), ("sequential", 2))


def splits_for(seed: int, n_stream: int, n_gate: int, n_test: int) -> dict:
    return {"stream": bench.make_split("stream", n_stream, seed),
            "gate": bench.make_split("gate", n_gate, seed),
            "test": bench.make_split("test", n_test, seed)}


def run_cell(cell: dict, args) -> dict:
    splits = splits_for(cell["seed"], args.n_stream, args.n_gate, args.n_test)
    rows, summaries = [], []
    rows += flywheel_arm.base_rows(cell, splits["stream"], "stream")
    rows += flywheel_arm.base_rows(cell, splits["test"], "test")
    for arm in args.arms:
        r, s = flywheel_arm.flywheel_rows(cell, splits, arm)
        rows += r
        summaries.append(s)
    if args.h2_root:
        import h2_arm
        for carry in args.carry:
            rows += h2_arm.h2_rows(cell, splits, carry=carry)
    controls = flywheel_arm.control_report(cell, splits, "line")
    controls_file = flywheel_arm.control_report(cell, splits, "file")
    return {"cell": cell, "rows": rows, "summaries": summaries, "controls": controls,
            "controls_file_gate": controls_file}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--h2-root", default="", help="harness2 checkout; omit to skip that arm")
    ap.add_argument("--seeds", type=int, default=6)
    ap.add_argument("--seed-offset", type=int, default=0,
                    help="v1 prereg seeds 0..5; v2 prereg seeds 200..205; smoke 300+")
    ap.add_argument("--p-game", type=float, nargs="+", default=[0.0, 0.15, 0.30])
    ap.add_argument("--carry", type=float, nargs="+", default=[0.5, 1.0])
    ap.add_argument("--n-stream", type=int, default=20)
    ap.add_argument("--n-gate", type=int, default=16)
    ap.add_argument("--n-test", type=int, default=24)
    ap.add_argument("--arms", nargs="+", default=list(flywheel_arm.ARMS),
                    choices=list(flywheel_arm.ARMS))
    args = ap.parse_args(argv)
    if args.h2_root:
        sys.path.insert(0, args.h2_root)
    args.out.mkdir(parents=True, exist_ok=True)
    for seed in range(args.seed_offset, args.seed_offset + args.seeds):
        for p in args.p_game:
            for mode, k in CONFIGS:
                cell = {"seed": seed, "p_game": p, "mode": mode, "k": k}
                path = args.out / f"s{seed}-p{p:.2f}-{mode}-k{k}.json"
                if path.is_file():
                    continue
                t0 = time.time()
                doc = run_cell(cell, args)
                doc["wall_s"] = round(time.time() - t0, 2)
                tmp = path.with_suffix(".tmp")
                tmp.write_text(json.dumps(doc, sort_keys=True), encoding="utf-8")
                tmp.replace(path)
                print(f"{path.name} {doc['wall_s']}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
