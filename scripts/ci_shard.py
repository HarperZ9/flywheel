#!/usr/bin/env python3
"""ci_shard.py -- split the test suite across CI jobs without losing a file.

The whole-suite job exists so that no regression can hide in a file the curated
slice does not name. It then died on a hosted runner: 47 minutes and "the hosted
runner lost communication with the server", which is resource starvation rather
than any test failing. Locally the same suite takes 11 minutes, and per-test
durations showed no single culprit worth cutting: the slowest test is 21s and the
top 25 together are under a third of the total. The cost is diffuse, spread over
2516 tests, many of which spawn subprocesses.

Diffuse cost is what sharding is for. Each shard gets a fresh runner, so this cuts
wall time AND stops resource accumulation from compounding across the whole run.

The danger is that a sharding scheme quietly drops a file, which would recreate
the exact blind spot the job exists to close, while every shard reports green. So
the invariant here is coverage, checked in tests: every test file lands in exactly
one shard, for every shard count.

Balance is by test count, greedy longest-first. That is a proxy, not a
measurement: a file with one deliberately-hanging test costs more than a file
with fifty fast ones. It is good enough to keep any shard well under the runner's
limit, and being approximate is fine as long as it is COMPLETE.

Stdlib only.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TESTS = REPO / "tests"
TEST_DEF = re.compile(r"^\s*(?:async\s+)?def\s+test_", re.MULTILINE)


def test_files(tests_dir: Path = TESTS) -> list[Path]:
    """Every file pytest would collect, sorted for determinism.

    Sorted by name, not by directory walk order, so two machines shard the same
    way. A shard that depended on filesystem ordering would be reproducible only
    by accident.
    """
    return sorted(p for p in tests_dir.rglob("test_*.py")
                  if "__pycache__" not in p.parts)


def weight(path: Path) -> int:
    """Test functions in the file, floored at 1 so an empty file still moves."""
    try:
        return max(1, len(TEST_DEF.findall(path.read_text(encoding="utf-8",
                                                          errors="replace"))))
    except OSError:
        return 1


def shard(files: list[Path], count: int) -> list[list[Path]]:
    """Greedy longest-processing-time assignment into `count` buckets."""
    if count < 1:
        raise ValueError("shard count must be at least 1")
    buckets: list[list[Path]] = [[] for _ in range(count)]
    loads = [0] * count
    # Heaviest first, each to the lightest bucket. Ties break on path so the
    # result does not depend on sort stability across versions.
    for p in sorted(files, key=lambda q: (-weight(q), q.as_posix())):
        i = loads.index(min(loads))
        buckets[i].append(p)
        loads[i] += weight(p)
    return buckets


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", type=int, required=True, help="0-based shard")
    ap.add_argument("--count", type=int, required=True)
    ap.add_argument("--tests", default=str(TESTS))
    ap.add_argument("--report", action="store_true",
                    help="print the balance of every shard instead of one list")
    args = ap.parse_args()

    files = test_files(Path(args.tests))
    if not files:
        print("no test files found; refusing to report an empty shard",
              file=sys.stderr)
        return 1
    buckets = shard(files, args.count)

    if args.report:
        for i, b in enumerate(buckets):
            print(f"shard {i}: {len(b):>3} files, {sum(weight(p) for p in b):>5} tests")
        print(f"total: {len(files)} files, {sum(weight(p) for p in files)} tests")
        return 0

    if not 0 <= args.index < args.count:
        print(f"index {args.index} outside 0..{args.count - 1}", file=sys.stderr)
        return 1
    print(" ".join(p.relative_to(REPO).as_posix() for p in buckets[args.index]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
