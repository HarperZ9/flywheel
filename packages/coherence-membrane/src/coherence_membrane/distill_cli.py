"""CLI for distill: verified code compression."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .distill import command_guard, distill_code


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="distill", description="Verified compression of code.")
    p.add_argument("--code", action="store_true", required=True, help="Code mode (the only mode in P1).")
    p.add_argument("--original", type=Path, required=True)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--tests", default=None, help="A command that exercises the candidate; exit 0 = behavior preserved.")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    try:
        original = args.original.read_bytes().decode("utf-8")
        candidate = args.candidate.read_bytes().decode("utf-8")
    except OSError as exc:
        raise SystemExit(f"distill: cannot read input: {exc}")
    rec = distill_code(original, candidate=candidate, behavior_guard=command_guard(args.tests) if args.tests else None)
    recheck = f"python -m coherence_membrane distill --code --original {args.original} --candidate {args.candidate}"
    if args.tests:
        recheck += f' --tests "{args.tests}"'
    rec["recheck"] = recheck
    if args.json:
        print(json.dumps(rec, indent=2, sort_keys=True))
    else:
        g = rec["gain"]
        print(f"verdict={rec['verdict']}"
              + (f"  gain={g}x  readability {rec['readability_before']} -> {rec['readability_after']}" if g else ""))
        if rec["verdict"] != "ACCEPTED" and rec["short_axis"]:
            print(f"  short axis: {rec['short_axis']}")
    return {"ACCEPTED": 0, "REJECTED": 1, "UNVERIFIABLE": 2}[rec["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
