"""output_check_cli.py -- check an answer against the sources that decide it.

The command any harness can call before an answer reaches a reader. It takes a
contract, takes the answer, consults each field's authority, and reports what
is confirmed and what is not. It never edits the answer and it never supplies a
value: the report tells the next attempt where to look, and looking is the part
that has to happen for a retry to mean anything.

Usage:

    python scripts/run_output_check.py --contract task.contract.json \\
        --answer answer.json [--allow-commands] [--out report.json] [--json]

A contract is one document holding both halves, so a task can ship its own
checks:

    {"fields": [{"name": "tax", "authority": "TABLE",
                 "source": "irs-2025-tax-table-single"}],
     "authorities": {"irs-2025-tax-table-single":
                     {"kind": "command", "argv": ["python", "tools/tax.py"]}}}

An answer states a value and where it came from, per field:

    {"tax": {"value": 4169, "source": "irs-2025-tax-table-single"}}

Exit codes, because a harness branches on them:

    0   every field agrees with its authority and says so
    1   a field disagrees with the authority that decides it
    3   nothing confirmed at least one field, so it is unchecked, not wrong

Two is skipped because argparse already uses it for a usage error, and a
harness that read a bad flag as an unverified answer would retry forever.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .authority_registry import build_authorities
from .output_contract import check_answer, feedback, new_contract
from .verdict import Verdict

EXIT = {Verdict.PASS.value: 0, Verdict.FAIL.value: 1, Verdict.UNVERIFIABLE.value: 3}


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def check(contract_doc: dict, answer: dict, *, base_dir, allow_commands: bool) -> dict:
    contract = new_contract(list(contract_doc.get("fields") or []))
    authorities = build_authorities(contract_doc.get("authorities") or {},
                                    allow_commands=allow_commands, base_dir=base_dir)
    report = check_answer(answer, contract, authorities)
    report["next"] = feedback(report)
    return report


def render(report: dict) -> str:
    """The report as a person reads it.

    Ordered worst first. A reader who stops after one line should have stopped
    on the field that decides the run, not on whichever one came first in the
    contract.
    """
    rank = {Verdict.FAIL.value: 0, Verdict.UNVERIFIABLE.value: 1, Verdict.PASS.value: 2}
    lines = [f"{report['verdict']}  {report['passed']} of {report['checked']} "
             f"fields confirmed"]
    for row in sorted(report["fields"], key=lambda r: rank[r["verdict"]]):
        lines.append(f"  {row['verdict']:<13} {row['field']}: {row['reason']}")
    for item in report["next"]["fields"]:
        lines.append(f"  next: {item['field']}: {item['do']}")
    return "\n".join(lines)


def main(argv=None) -> int:
    # No abbreviation. Argparse accepts any unambiguous prefix by default,
    # which made `--allow-command` silently turn on command execution. A
    # near-miss of a flag that grants a capability has to be a usage error.
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                     allow_abbrev=False)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--answer", required=True, type=Path)
    parser.add_argument("--allow-commands", action="store_true",
                        help="let command authorities run. Without it they are "
                             "unchecked rather than confirmed, which is the "
                             "safe direction and not a passing one.")
    parser.add_argument("--base-dir", type=Path, default=None,
                        help="where relative authority paths resolve from. "
                             "Defaults to the contract's own directory, so a "
                             "task and its checkers travel together.")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    contract_doc = load(args.contract)
    base_dir = args.base_dir or args.contract.resolve().parent
    report = check(contract_doc, load(args.answer), base_dir=base_dir,
                   allow_commands=args.allow_commands)

    text = json.dumps(report, indent=2) if args.json else render(report)
    print(text)
    if args.out:
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return EXIT[report["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
