#!/usr/bin/env python3
"""Run the red check for one change and print its receipt.

    python scripts/red_check.py --repo . --base origin/main --head HEAD [--test NODE ...]

Report-only: exits 0 whatever the classes are, 2 on a usage or git error. It runs
the repository's tests on the base commit, so point it at code you would run.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.red_check import red_check  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base", required=True, help="the parent commit")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--test", action="append", default=[], help="pytest node id (repeatable)")
    ap.add_argument("--runs", type=int, default=2, help="base runs (2 detects flakes)")
    ap.add_argument("--timeout", type=int, default=300, help="seconds per pytest run")
    ap.add_argument("--no-head", action="store_true", help="skip the passes-at-head control")
    args = ap.parse_args(argv)
    try:
        receipt = red_check(args.repo, args.base, args.head, args.test or None,
                            runs=args.runs, timeout=args.timeout,
                            check_head=not args.no_head)
    except (RuntimeError, OSError) as exc:
        print(f"red_check: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
