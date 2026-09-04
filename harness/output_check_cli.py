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

A contract may name a domain pack instead of spelling out what the domain
already decides. The pack supplies the authority kind, the criticality and the
method mandate; the document supplies the name and the source:

    {"pack": "medicine",
     "fields": [{"use": "dose", "name": "dose", "source": "formulary:2026-03"}]}

Run `flywheel packs` to see what a pack declares and what it refuses to decide.

Exit codes, because a harness branches on them:

    0   every field agrees with its authority and says so
    1   a field disagrees with the authority that decides it
    3   nothing confirmed at least one field, so it is unchecked, not wrong

Two is skipped because argparse already uses it for a usage error, and a
harness that read a bad flag as an unverified answer would retry forever.

The verdict answers whether the values are confirmed. The release answers
whether the answer may leave the building, which is narrower: a critical field
short of PASS holds it even where the verdict is only UNVERIFIABLE. `--strict`
puts that on the exit code for a caller that cannot carry a caveat.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .authority_registry import build_authorities
from .contract_feedback import feedback
from .contract_terms import HOLD
from .domain_packs import field_spec, load_pack
from .output_contract import check_answer, new_contract
from .validation_ledger import TASK, record
from .verdict import Verdict

EXIT = {Verdict.PASS.value: 0, Verdict.FAIL.value: 1, Verdict.UNVERIFIABLE.value: 3}


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def specs(contract_doc: dict) -> list[dict]:
    """The field specs, with a named pack filling in what the domain decides.

    A field entry that names a `use` gets its authority kind, criticality and
    method mandate from the pack, so a task document states only the two facts
    the pack cannot know: what the field is called and which source decides it.
    """
    raw = list(contract_doc.get("fields") or [])
    name = contract_doc.get("pack", "")
    if not name:
        return raw
    pack = load_pack(name)
    built = []
    for spec in raw:
        spec = dict(spec)
        use = spec.pop("use", "")
        built.append(field_spec(pack, use, **spec) if use else spec)
    return built


def check(contract_doc: dict, answer: dict, *, base_dir, allow_commands: bool) -> dict:
    contract = new_contract(specs(contract_doc))
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
             f"fields confirmed",
             f"{report['release']}" + (f"  blocked by: {', '.join(report['blocking'])}"
                                        if report["blocking"] else "")]
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
    parser.add_argument("--ledger", type=Path, default=None,
                        help="append this check to a validation ledger, so the "
                             "goal and session scopes can read it later. "
                             "Defaults to the shared ledger under FLYWHEEL_HOME "
                             "when --scope or --subject is given.")
    parser.add_argument("--scope", default="", choices=["", "task", "goal", "session"],
                        help="which scope this check belongs to.")
    parser.add_argument("--subject", default="",
                        help="what was checked: a task id, a goal, a session.")
    parser.add_argument("--strict", action="store_true",
                        help="exit non-zero on any release short of RELEASE, "
                             "so a caveat stops a pipeline that cannot carry one.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    contract_doc = load(args.contract)
    base_dir = args.base_dir or args.contract.resolve().parent
    report = check(contract_doc, load(args.answer), base_dir=base_dir,
                   allow_commands=args.allow_commands)

    if args.ledger or args.scope or args.subject:
        record(report, scope=args.scope or TASK, subject=args.subject,
               path=args.ledger)

    text = json.dumps(report, indent=2) if args.json else render(report)
    print(text)
    if args.out:
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.strict and report["release"] != "RELEASE":
        # A held or caveated answer is not a clean exit for a caller that
        # cannot carry a caveat. The verdict is unchanged; only the exit is.
        return 1 if report["release"] == HOLD else 3
    return EXIT[report["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
