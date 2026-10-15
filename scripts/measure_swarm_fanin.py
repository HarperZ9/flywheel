"""measure_swarm_fanin.py -- seal and recheck cost of a swarm fan-in at 8, 64, 512 children.

Synthetic children only (no child process runs): receipts in the shape
harness/subagents.py writes, a random chain head each, every third child not
accepted. Each run seals with finalize_swarm (empty hook registry) into a
temporary run root, loads the saved receipt and rechecks it offline. Sizes are
interleaved; the median and 10th to 90th percentile range are reported.

  python scripts/measure_swarm_fanin.py --runs 15 --out result.json
"""
from __future__ import annotations

import argparse
import json
import secrets
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.subagent_fanin import finalize_swarm, recheck_swarm_receipt  # noqa: E402
from harness.subagent_roles import RUN_SCHEMA  # noqa: E402
from harness.subagent_store import load_swarm_receipt, swarm_dir  # noqa: E402


class FakeRunner:
    def __init__(self, root: Path):
        self.root, self._lock = root, threading.Lock()

    def _clock(self) -> str:
        return "2026-10-15T00:00:00Z"


def synthetic_rec(n: int, policy: str = "majority") -> dict:
    swarm_id = "swarm-" + secrets.token_hex(4)
    children = []
    for i in range(n):
        accepted = i % 3 != 2
        children.append({"receipt": {
            "schema": RUN_SCHEMA, "swarm_id": swarm_id, "child_id": f"c{i:04d}",
            "role": "explore", "endpoint": "", "spec_sha256": secrets.token_hex(32),
            "exit_code": 0, "output_sha256": secrets.token_hex(32), "duration_ms": 10,
            "timed_out": False, "result_ok": True, "status": "completed",
            "accepted": accepted, "verdict_chain_head": secrets.token_hex(32)}})
    return {"swarm_id": swarm_id, "goal": "synthetic fan-in", "endpoint": "",
            "quorum_policy": policy, "children": children, "created_at": "2026-10-15T00:00:00Z"}


def one_run(n: int, root: Path) -> tuple:
    runner, rec = FakeRunner(root), synthetic_rec(n)
    t0 = time.perf_counter()
    finalize_swarm(runner, rec)
    t1 = time.perf_counter()
    saved = load_swarm_receipt(swarm_dir(root, rec["swarm_id"]) / "swarm.json")
    result = recheck_swarm_receipt(saved)
    t2 = time.perf_counter()
    if result["verdict"] != "MATCH":
        raise AssertionError(f"recheck of a fresh seal did not match: {result}")
    return t1 - t0, t2 - t1


def _stats(xs: list) -> dict:
    qs = statistics.quantiles(xs, n=10)
    return {"median_s": round(statistics.median(xs), 6), "p10_s": round(qs[0], 6),
            "p90_s": round(qs[-1], 6)}


def measure(sizes=(8, 64, 512), runs: int = 15) -> dict:
    seal = {n: [] for n in sizes}
    recheck = {n: [] for n in sizes}
    with tempfile.TemporaryDirectory() as tmp:
        for r in range(runs):
            for n in (sizes if r % 2 == 0 else tuple(reversed(sizes))):
                s, c = one_run(n, Path(tmp))
                seal[n].append(s)
                recheck[n].append(c)
    out = {"runs": runs, "sizes": list(sizes),
           "seal": {str(n): _stats(seal[n]) for n in sizes},
           "recheck": {str(n): _stats(recheck[n]) for n in sizes}}
    if 64 in sizes and 512 in sizes:
        out["recheck_ratio_512_over_64"] = round(
            statistics.median(recheck[512]) / statistics.median(recheck[64]), 2)
    return out


def main(argv: "list | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", type=int, default=15)
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    result = measure(runs=args.runs)
    text = json.dumps(result, indent=1)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
