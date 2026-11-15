"""pick_bench.py: measure `plexus pick` on a labelled request set.

Items split in half by a seeded hash of their id. The abstain threshold is
calibrated on the dev half; numbers come from the test half. The baseline is
the dev half's majority tool, always picked. A shuffled-label control checks
that "abstained items carry more error" is not an artifact of the arithmetic.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter
from pathlib import Path

from .mesh import discover
from .pick import pick
from .registry import builtin_manifests

SEED = 20261003


def split(items: list[dict], seed: int = SEED) -> tuple[list[dict], list[dict]]:
    dev, test = [], []
    for item in items:
        digest = hashlib.sha256(f"{seed}:{item['id']}".encode()).digest()
        (dev if digest[0] % 2 == 0 else test).append(item)
    return dev, test


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [0.0, 0.0]
    p, d = k / n, 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round((c - h) / d, 3), round((c + h) / d, 3)]


def _rate(k: int, n: int) -> float:
    return round(k / n, 4) if n else 0.0


def abstain_stats(rows: list[tuple]) -> dict:
    """rows: (top-1 tool, picked tool or None, gold). Error is top-1 vs gold."""
    dec = [r for r in rows if r[1] is not None]
    abst = [r for r in rows if r[1] is None]
    dec_rate = _rate(sum(1 for t, _, g in dec if t != g), len(dec))
    abs_rate = _rate(sum(1 for t, _, g in abst if t != g), len(abst))
    return {"decided": len(dec), "abstained": len(abst),
            "abstain_rate": _rate(len(abst), len(rows)),
            "decided_error_rate": dec_rate, "abstained_error_rate": abs_rate,
            "error_ratio": round(abs_rate / dec_rate, 3) if dec_rate else None}


def calibrate(mesh, items: list[dict], share: float = 0.10) -> float:
    """Lowest threshold whose abstain rate on ``items`` is at least ``share``."""
    tops = []
    for item in items:
        top = pick(mesh, item["text"])["candidates"][0]
        tops.append(top["probability"] if top["score"] > 0 else -1.0)
    need = math.ceil(share * len(tops))
    forced = sum(1 for t in tops if t < 0)
    if forced >= need:
        return 0.0
    ranked = sorted(t for t in tops if t >= 0)
    return min(1.0, round(ranked[need - forced - 1] + 1e-6, 6))


def run(items: list[dict], mesh=None, seed: int = SEED) -> dict:
    mesh = mesh or discover(builtin_manifests())
    dev, test = split(items, seed)
    threshold = calibrate(mesh, dev)
    rows = []
    for item in test:
        r = pick(mesh, item["text"], threshold=threshold)
        rows.append((r["candidates"][0]["tool"], r["picked"], item["gold"]))
    correct = sum(1 for t, _, g in rows if t == g)
    majority = Counter(i["gold"] for i in dev).most_common(1)[0][0]
    base = sum(1 for i in test if i["gold"] == majority)
    stats = abstain_stats(rows)
    golds = [g for _, _, g in rows]
    random.Random(seed).shuffle(golds)
    shuffled = abstain_stats([(t, p, g) for (t, p, _), g in zip(rows, golds)])
    acc, base_acc = _rate(correct, len(rows)), _rate(base, len(test))
    bar = {"P1_accuracy_baseline_plus_0_20": acc >= base_acc + 0.20,
           "P2_abstain_under_15pct": stats["abstain_rate"] < 0.15,
           "P3_error_ratio_at_least_2": (stats["error_ratio"] or 0.0) >= 2.0,
           "control_fails_P3": (shuffled["error_ratio"] or 0.0) < 2.0}
    return {"schema": "plexus.pick-bench/1", "seed": seed, "dev": len(dev),
            "test": len(test), "threshold": threshold,
            "top1_accuracy": acc, "top1_wilson": wilson(correct, len(rows)),
            "baseline": {"tool": majority, "accuracy": base_acc}, **stats,
            "shuffled_label_control": shuffled, "bar": bar}


def main(argv: list[str] | None = None) -> int:
    import sys
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: python -m plexus.pick_bench LABELS.json", file=sys.stderr)
        return 2
    items = json.loads(Path(args[0]).read_text(encoding="utf-8"))["items"]
    print(json.dumps(run(items), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
