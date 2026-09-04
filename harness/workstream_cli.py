"""workstream_cli.py -- settle a dependency graph of obligations from the shell.

    flywheel workstream example > dose.json     a declaration to start from
    flywheel workstream run dose.json           run the wired checkers, settle
    flywheel workstream settle dose.json        recompose results decided elsewhere
    flywheel workstream run dose.json --json    the receipt, for a harness

A declaration is a goal and a list of obligations. Each obligation carries the
exact statement that gets checked, which kind of checker decides it, the pinned
environment it is decided in, and what it rests on:

    {"goal": "label",
     "obligations": [
       {"id": "conversion", "check": "dimensional", "environment": "flywheel.units/v1",
        "statement": "{\\"value\\": 500, \\"from\\": \\"mg\\", \\"to\\": \\"g\\", \\"expected\\": 0.5}"},
       {"id": "label", "check": "arithmetic", "environment": "flywheel.units/v1",
        "depends_on": ["conversion"], "statement": "..."}]}

`run` calls the checkers. `settle` calls none and reads a "result" field off each
obligation instead, which is the path for a stack whose proofs were checked on a
build farm and are being recomposed here.

The standing of the goal is derived, never asserted. An obligation resting on
something refuted, pending, or unverifiable reports blocked, so a green top over
a hole is not reachable from this command.

Exits 0 when the goal is established, 1 when something under it was refused, and
2 when nothing decided it yet, which is also what a malformed declaration
returns. A build gating on the code cannot read an unfinished stack as a pass.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .workstream import WorkstreamError, settle
from .workstream_receipt import workstream_receipt
from .workstream_run import load_workstream, run_workstream

EXAMPLE = {
    "goal": "label",
    "obligations": [
        {"id": "statute", "check": "assumed", "environment": "cfr:2026-title21",
         "statement": "21 CFR 201.57(c)(3) requires the strength per dosage unit"},
        {"id": "conversion", "check": "dimensional", "environment": "flywheel.units/v1",
         "statement": '{"value": 500, "from": "mg", "to": "g", "expected": 0.5}'},
        {"id": "assay", "check": "arithmetic", "environment": "hplc-2/cal-2026-08-30",
         "depends_on": ["conversion"],
         "statement": '{"value": 0.5, "interval": [0.49, 0.51]}'},
        {"id": "label", "check": "arithmetic", "environment": "flywheel.units/v1",
         "depends_on": ["assay", "statute"],
         "statement": '{"value": 0.5, "interval": [0.45, 0.55]}'},
    ],
}


def _render(receipt: dict) -> str:
    """The receipt as something a person reads without a JSON viewer."""
    lines = [f"goal {receipt['goal']} is {receipt['goal_standing'].upper()}",
             f"  {receipt['goal_reason']}",
             f"  workstream {receipt['workstream_id'][:16]}",
             ""]
    reached = set(receipt["reached_from_goal"])
    for node_id, record in receipt["obligations"].items():
        mark = " " if node_id in reached else "."
        lines.append(f" {mark} {record['standing']:<13}{node_id:<22}"
                     f"{record['check']:<13}{record['environment']}")
        detail = record.get("detail") or ""
        if detail and record["standing"] != "verified":
            lines.append(f"     {detail[:96]}")
    run = receipt.get("run")
    if run:
        lines += ["", f"checked {run['checked']}, skipped {run['skipped']} "
                      f"(a skip means a dependency was not satisfied)"]
    if receipt["assumption_footprint"]:
        lines += ["", "carried, not checked:"]
        lines += [f"  {name}" for name in receipt["assumption_footprint"]]
    lines += ["", "environments under the goal:"]
    lines += [f"  {name}" for name in receipt["environment_footprint"]]
    lines += ["", "does not prove:"]
    lines += [f"  - {line}" for line in receipt["does_not_prove"]]
    lines.append("")
    lines.append("A dot marks an obligation the goal does not rest on.")
    return "\n".join(lines)


def _load(path: str) -> tuple:
    source = Path(path)
    if not source.is_file():
        raise WorkstreamError(f"no declaration at {path}")
    return load_workstream(source.read_text(encoding="utf-8"))


def _exit_code(receipt: dict) -> int:
    """0 established, 1 something was refused, 2 nothing decided it yet.

    Blocked is not one answer, so it does not map to one code. A goal blocked
    under a refuted lemma is a failure to act on; a goal blocked under a lemma
    nobody has proved yet is unfinished work. Collapsing those would turn a
    build that has not run into a build that failed, or the reverse.
    """
    if receipt["goal_standing"] in ("verified", "assumed"):
        return 0
    refused = any(receipt["obligations"][node]["standing"] == "refuted"
                  for node in receipt["reached_from_goal"])
    return 1 if refused else 2


def _emit(receipt: dict, as_json: bool) -> int:
    print(json.dumps(receipt, indent=2) if as_json else _render(receipt))
    return _exit_code(receipt)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="flywheel workstream",
                                     description=__doc__.splitlines()[0],
                                     allow_abbrev=False)
    parser.add_argument("action", choices=("run", "settle", "example"))
    parser.add_argument("declaration", nargs="?", default="")
    parser.add_argument("--json", action="store_true",
                        help="emit the receipt instead of the rendering")
    args = parser.parse_args(argv)
    if args.action == "example":
        print(json.dumps(EXAMPLE, indent=2))
        return 0
    if not args.declaration:
        parser.error(f"{args.action} needs a declaration file")
    try:
        workstream, recorded = _load(args.declaration)
        if args.action == "run":
            if recorded:
                print("note: results in the declaration are ignored by run; "
                      "use settle to recompose them", file=sys.stderr)
            receipt = run_workstream(workstream)
        else:
            settle(workstream, recorded)  # refuses a malformed result first
            receipt = workstream_receipt(workstream, recorded)
    except (WorkstreamError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return _emit(receipt, args.json)


if __name__ == "__main__":
    raise SystemExit(main())
