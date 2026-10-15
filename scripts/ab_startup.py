"""ab_startup.py -- accept a startup change only when the numbers say so.

Runs two builds (two site-packages folders with flywheel-verify in them, run by
the same base interpreter, the scripts/measure_footprint.py method) in ABBA
order for N pairs and measures, per run: warm time to the `flywheel>` prompt
(the primary metric), cold time to the prompt, memory at the prompt and
`flywheel --version` time. For each metric it takes a 95% bootstrap interval of
the difference of medians, B minus A.

Accept only when the primary interval lies entirely below zero and no neighbor
regresses: a neighbor regresses when its interval lies entirely above zero and
its median difference exceeds 5% of A's median. Every experiment, accepted or
refused, is appended to a hash-chained JSONL record with both builds' file
hashes, the raw numbers and the decision. A refused experiment is kept.

  python scripts/ab_startup.py --venv V --a SP_A --b SP_B --record ab.jsonl --label NAME
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import measure_footprint as mf  # noqa: E402

METRICS = ("warm_s", "cold_s", "rss_bytes", "version_s")
PRIMARY = "warm_s"
NEIGHBOR_TOLERANCE = 0.05
SCHEMA = "flywheel.ab-startup/v1"


def tree_sha256(sp: Path) -> str:
    """One hash over every .py file under harness/, by relative path and bytes."""
    h = hashlib.sha256()
    base = Path(sp) / "harness"
    for f in sorted(base.rglob("*.py")):
        h.update(f.relative_to(base).as_posix().encode() + b"\0" + f.read_bytes())
    return h.hexdigest()


def one_build(cmd: list, sp: Path, port: int, cwd: str) -> dict:
    mf.clear_bytecode(sp)
    cold = mf.time_to_prompt(cmd, port)
    mf.time_to_prompt(cmd, port)                 # warm the cache
    warm = mf.time_to_prompt(cmd, port)
    return {"cold_s": cold["seconds"], "warm_s": warm["seconds"], "rss_bytes": warm["rss_bytes"],
            "version_s": mf.version_time(cmd, cwd)}


def bootstrap_diff(a: list, b: list, *, draws: int = 2000, seed: int = 0) -> tuple:
    """95% interval of median(b) - median(a), resampling each side."""
    rng = random.Random(seed)
    diffs = sorted(statistics.median(rng.choices(b, k=len(b))) -
                   statistics.median(rng.choices(a, k=len(a))) for _ in range(draws))
    return diffs[int(0.025 * draws)], diffs[int(0.975 * draws) - 1]


def decide(runs_a: list, runs_b: list, seed: int = 0) -> dict:
    out = {}
    for m in METRICS:
        a = [r[m] for r in runs_a if r[m] is not None]
        b = [r[m] for r in runs_b if r[m] is not None]
        lo, hi = bootstrap_diff(a, b, seed=seed)
        med_a = statistics.median(a)
        out[m] = {"median_a": med_a, "median_b": statistics.median(b),
                  "diff": statistics.median(b) - med_a, "ci95": [lo, hi]}
    primary = out[PRIMARY]["ci95"][1] < 0
    regressed = [m for m in METRICS if m != PRIMARY and out[m]["ci95"][0] > 0
                 and out[m]["diff"] > NEIGHBOR_TOLERANCE * out[m]["median_a"]]
    verdict = "accept" if primary and not regressed else "refuse"
    why = ("primary faster and no neighbor regressed" if verdict == "accept" else
           "a neighbor regressed: " + ", ".join(regressed) if regressed else
           "the primary interval does not lie below zero")
    return {"verdict": verdict, "why": why, "metrics": out}


def append_record(path: Path, body: dict) -> dict:
    prev = "0" * 64
    if path.is_file():
        lines = [x for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
        if lines:
            prev = json.loads(lines[-1])["entry_sha256"]
    body = {**body, "prev_sha256": prev}
    body["entry_sha256"] = hashlib.sha256(
        json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(body, sort_keys=True) + "\n")
    return body


def verify_record(path: Path) -> bool:
    prev = "0" * 64
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        claimed = row.pop("entry_sha256")
        if row["prev_sha256"] != prev or hashlib.sha256(
                json.dumps(row, sort_keys=True).encode("utf-8")).hexdigest() != claimed:
            return False
        prev = claimed
    return True


def run(venv: Path, sp_a: Path, sp_b: Path, pairs: int = 20, seed: int = 0) -> tuple:
    py = mf.venv_python(venv)
    cmd_a, cmd_b = mf.command(py, sp_a), mf.command(py, sp_b)
    import tempfile
    cwd = tempfile.mkdtemp(prefix="fw-ab-")
    port = mf.free_port()
    stub = subprocess.Popen([sys.executable, str(mf.ROOT / "scripts" / "ci_stub_model.py"),
                             str(port), "Done."], stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    runs_a, runs_b = [], []
    try:
        time.sleep(0.5)
        for i in range(pairs):
            order = ("a", "b") if i % 2 == 0 else ("b", "a")    # ABBA across pairs
            for which in order:
                if which == "a":
                    runs_a.append(one_build(cmd_a, sp_a, port, cwd))
                else:
                    runs_b.append(one_build(cmd_b, sp_b, port, cwd))
    finally:
        stub.kill()
        stub.wait(timeout=10)
    return runs_a, runs_b


def main(argv: "list | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--venv", required=True, help="the venv whose base interpreter runs both")
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--pairs", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--record", required=True)
    ap.add_argument("--label", default="")
    args = ap.parse_args(argv)
    sp_a, sp_b = Path(args.a), Path(args.b)
    runs_a, runs_b = run(Path(args.venv), sp_a, sp_b, args.pairs, args.seed)
    decision = decide(runs_a, runs_b, args.seed)
    row = append_record(Path(args.record), {
        "schema": SCHEMA, "label": args.label, "pairs": args.pairs, "seed": args.seed,
        "a_sha256": tree_sha256(sp_a), "b_sha256": tree_sha256(sp_b),
        "runs_a": runs_a, "runs_b": runs_b, **decision})
    print(json.dumps({k: row[k] for k in ("label", "verdict", "why", "metrics")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
