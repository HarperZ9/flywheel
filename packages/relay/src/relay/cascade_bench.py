"""cascade_bench.py: measure the flaky-failure cascade on a labelled set (docs/CASCADE.md).

Items split in half by a seeded hash of their id. The threshold is the lowest confidence at which
dev-half decided accuracy reaches 0.95; all reported numbers come from the test half.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from pathlib import Path

from .cascade import FlakyClassifier

SEED = 20261003
GRID = [round(0.5 + i * 0.01, 2) for i in range(51)]


def split(items: list[dict], seed: int = SEED) -> tuple[list[dict], list[dict]]:
    dev: list[dict] = []
    test: list[dict] = []
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


def decide(probs: list[float], labels: list[bool], threshold: float) -> dict:
    kept = [(p >= 0.5, y) for p, y in zip(probs, labels) if max(p, 1 - p) >= threshold]
    right = sum(1 for guess, y in kept if guess == y)
    return {"decided": len(kept), "decided_share": round(len(kept) / len(probs), 4) if probs else 0.0,
            "decided_correct": right,
            "decided_accuracy": round(right / len(kept), 4) if kept else None,
            "decided_wilson": wilson(right, len(kept))}


def calibrate(probs: list[float], labels: list[bool], target: float = 0.95) -> float:
    for t in GRID:
        r = decide(probs, labels, t)
        if r["decided"] and r["decided_accuracy"] >= target:
            return t
    return 1.0


def run(items: list[dict], seed: int = SEED) -> dict:
    clf = FlakyClassifier()
    dev, test = split(items, seed)
    lab = lambda rows: [r["label"] == "flaky" for r in rows]  # noqa: E731
    dprob = [clf.probability(r["log"]) for r in dev]
    threshold = calibrate(dprob, lab(dev))
    tprob = [clf.probability(r["log"]) for r in test]
    result = decide(tprob, lab(test), threshold)
    shuffled = lab(test)
    random.Random(seed).shuffle(shuffled)
    control = decide(tprob, shuffled, threshold)
    hard = [i for i, r in enumerate(test) if r.get("hard")]
    hard_res = decide([tprob[i] for i in hard], [lab(test)[i] for i in hard], threshold)
    acc = result["decided_accuracy"] or 0.0
    bar = {"C1_decides_half": result["decided_share"] >= 0.5, "C2_accuracy_095": acc >= 0.95,
           "control_fails_C2": (control["decided_accuracy"] or 0.0) < 0.95}
    return {"schema": "relay.cascade-bench/1", "seed": seed, "dev": len(dev), "test": len(test),
            "threshold": threshold, "test_result": result, "hard_items": hard_res,
            "shuffled_label_control": control, "bar": bar}


def main(argv: list[str] | None = None) -> int:
    import sys
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: python -m relay.cascade_bench LABELS.json", file=sys.stderr)
        return 2
    items = json.loads(Path(args[0]).read_text(encoding="utf-8"))["items"]
    print(json.dumps(run(items), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
