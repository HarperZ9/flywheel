"""`flywheel behavior-check A B`: replay fixed scripted sessions on two builds.

A and B are Flywheel source trees. Exit 0 on MATCH, 1 on DRIFT, 2 when the
check could not run or a scenario reached no model on either build.
"""
from __future__ import annotations

import argparse
import json
import sys

from .check import behavior_check, render, write_receipt

DESCRIPTION = ("Replay fixed scripted sessions with `flywheel code -p` on two Flywheel "
               "source trees against a scripted model, compare model requests, stream "
               "events, workspace files, exit code and ledger kinds, and report MATCH or "
               "DRIFT with the first diverging event.")


def parse_args(argv):
    ap = argparse.ArgumentParser(prog="flywheel behavior-check", description=DESCRIPTION)
    ap.add_argument("a", help="build A: a Flywheel source tree")
    ap.add_argument("b", help="build B: a Flywheel source tree")
    ap.add_argument("--scenario", action="append", default=[], metavar="NAME",
                    help="run only this scenario (repeatable)")
    ap.add_argument("--scenarios", default=None, metavar="FILE",
                    help="a scenarios file (default: the one shipped with Flywheel)")
    ap.add_argument("--jobs", type=int, default=2, help="sessions run at once (default 2)")
    ap.add_argument("--python", default=sys.executable,
                    help="interpreter that runs both builds (default: this one)")
    ap.add_argument("--work", default=None, metavar="DIR",
                    help="parent folder for the per-run folders (default: system temp)")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    ap.add_argument("--receipt", default="", metavar="PATH",
                    help="also write the report as a sealed receipt")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = behavior_check(args.a, args.b, only=args.scenario or None,
                                scenarios_file=args.scenarios, work=args.work,
                                jobs=args.jobs, python=args.python)
    except (OSError, ValueError) as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2
    if args.receipt:
        report["receipt_sha256"] = write_receipt(report, args.receipt)["receipt_sha256"]
    print(json.dumps(report, indent=1) if args.json else render(report))
    return {"MATCH": 0, "DRIFT": 1}.get(report["verdict"], 2)


if __name__ == "__main__":
    raise SystemExit(main())
