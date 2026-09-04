"""output_check_cli.py -- check an answer against the sources that decide it.

The command any harness can call before an answer reaches a reader. It takes a
contract, takes the answer, consults each field's authority, and reports what
is confirmed and what is not. It never edits the answer and it never supplies a
value: the report tells the next attempt where to look, and looking is the part
that has to happen for a retry to mean anything.

Usage:

    python scripts/run_output_check.py --contract task.contract.json \\
        --answer answer.json [--allow-commands] [--out report.json] [--json]

The answer may arrive as `.json`, or inside the document it was written in:
a `flywheel-answer` fence in Markdown, a `flywheelanswer` environment in LaTeX,
or the attached stream a Flywheel PDF carries. The report goes back out in any
of `.txt`, `.md`, `.tex`, `.pdf` or `.json` with `--report`, chosen by suffix.

`--lean` writes the check as a Lean 4 file: the contract's arithmetic and its
method and source mandates as obligations a kernel settles, and every value an
outside source decided as a named axiom, so `#print axioms confirmed` lists
what the answer rests on. `--verify-lean` runs `lean` on it. A kernel that
refuses an obligation the report passed is a disagreement between two readings
of one answer, and it lands on the exit code.

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

from .answer_docs import DocumentError, read_answer
from .authority_registry import build_authorities
from .contract_feedback import feedback
from .contract_terms import HOLD
from .domain_packs import PACKS, field_spec, load_pack
from .output_contract import check_answer, new_contract
from .proof_lean import lean_source
from .proof_relations import RelationError
from .proof_run import prove
from .report_docs import as_text as render
from .report_docs import write_report
from .validation_ledger import TASK, record
from .verdict import Verdict

EXIT = {Verdict.PASS.value: 0, Verdict.FAIL.value: 1, Verdict.UNVERIFIABLE.value: 3}
# Worst wins. The report and the Lean file are two readings of one answer, and
# a run is only as sound as the weaker of them.
SEVERITY = {Verdict.PASS.value: 0, Verdict.UNVERIFIABLE.value: 1, Verdict.FAIL.value: 2}


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def pack_ref(name: str, base_dir) -> str:
    """A pack declared beside the contract resolves beside the contract.

    A shipped pack is a bare name, so this changes nothing for one of those.
    It only decides what a document-declared pack path means, and the useful
    reading is relative to the contract that names it rather than to whichever
    directory the check happened to be run from.
    """
    if not base_dir or name in PACKS:
        return name
    beside = Path(base_dir) / name
    return str(beside) if beside.is_file() else name


def specs(contract_doc: dict, *, base_dir=None) -> list[dict]:
    """The field specs, with a named pack filling in what the domain decides.

    A field entry that names a `use` gets its authority kind, criticality and
    method mandate from the pack, so a task document states only the two facts
    the pack cannot know: what the field is called and which source decides it.
    """
    raw = list(contract_doc.get("fields") or [])
    name = contract_doc.get("pack", "")
    if not name:
        return raw
    pack = load_pack(pack_ref(name, base_dir))
    built = []
    for spec in raw:
        spec = dict(spec)
        use = spec.pop("use", "")
        built.append(field_spec(pack, use, **spec) if use else spec)
    return built


def check(contract_doc: dict, answer: dict, *, base_dir, allow_commands: bool) -> dict:
    contract = new_contract(specs(contract_doc, base_dir=base_dir))
    authorities = build_authorities(contract_doc.get("authorities") or {},
                                    allow_commands=allow_commands, base_dir=base_dir)
    report = check_answer(answer, contract, authorities)
    report["next"] = feedback(report)
    return report


def _proof(parser, args, contract_doc: dict, report: dict, answer: dict, *,
           base_dir=None) -> dict:
    """The Lean file, written and then checked if the caller asked for that."""
    try:
        source = lean_source(report, answer,
                             specs(contract_doc, base_dir=base_dir),
                             relations=contract_doc.get("relations") or ())
    except RelationError as exc:
        # A relation the contract states and this module will not turn into a
        # claim is an authoring error in the contract, not a finding about the
        # answer. It exits like the usage error it is.
        parser.error(f"--contract {args.contract}: {exc}")
    if args.verify_lean:
        return prove(source, args.lean, lean=args.lean_bin or None)
    args.lean.write_text(source, encoding="utf-8")
    return {"verdict": Verdict.UNVERIFIABLE.value, "checker": "", "axioms": [],
            "errors": [], "file": str(args.lean),
            "reason": "written, not checked; pass --verify-lean to run the kernel"}


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
    parser.add_argument("--out", type=Path, default=None,
                        help="write the report as JSON here.")
    parser.add_argument("--report", type=Path, default=None,
                        help="write the report in the format this path asks "
                             "for: .txt, .md, .tex, .pdf or .json. A PDF "
                             "carries the answer as an attachment, so the page "
                             "and the values it vouches for travel together.")
    parser.add_argument("--lean", type=Path, default=None,
                        help="write the check as a Lean 4 file.")
    parser.add_argument("--verify-lean", action="store_true",
                        help="run `lean` on that file. Without it the file is "
                             "written and not checked, which is unverified "
                             "rather than confirmed.")
    parser.add_argument("--lean-bin", default="",
                        help="which lean to run. Defaults to the one on PATH.")
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
    try:
        answer = read_answer(args.answer)
    except (DocumentError, ValueError) as exc:
        parser.error(f"--answer {args.answer}: {exc}")
    report = check(contract_doc, answer, base_dir=base_dir,
                   allow_commands=args.allow_commands)
    if args.lean or args.verify_lean:
        report["proof"] = _proof(parser, args, contract_doc, report, answer,
                                 base_dir=base_dir)

    if args.ledger or args.scope or args.subject:
        record(report, scope=args.scope or TASK, subject=args.subject,
               path=args.ledger)

    print(json.dumps(report, indent=2) if args.json else render(report))
    if args.out:
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.report:
        try:
            write_report(report, args.report, answer=answer)
        except ValueError as exc:
            parser.error(f"--report {args.report}: {exc}")
    if args.strict and report["release"] != "RELEASE":
        # A held or caveated answer is not a clean exit for a caller that
        # cannot carry a caveat. The verdict is unchanged; only the exit is.
        return 1 if report["release"] == HOLD else 3
    verdict = report["verdict"]
    if args.verify_lean and SEVERITY[report["proof"]["verdict"]] > SEVERITY[verdict]:
        # The kernel disagreeing with the report is the finding the second
        # reading exists to produce. It cannot make a run cleaner, only worse.
        verdict = report["proof"]["verdict"]
    return EXIT[verdict]


if __name__ == "__main__":
    raise SystemExit(main())
