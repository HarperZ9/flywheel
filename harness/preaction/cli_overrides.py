"""cli_overrides.py -- `flywheel monitor outcome` and `flywheel monitor overrides`.

outcome     record, once the result is known, whether an owner decision held up.
            Needs a real terminal and the first six characters of the decision
            seal typed back, so an agent's shell cannot write outcomes.
overrides   per-rule override rates, reason codes and outcome checks for a store.
"""
from __future__ import annotations

import json

from .overrides import EVIDENCE, NOT_DETERMINABLE, record_outcome
from .overrides_report import report

COMMANDS = ("outcome", "overrides")
_EVIDENCE = sorted({e for codes in EVIDENCE.values() for e in codes} | {NOT_DETERMINABLE})


def register(sub) -> None:
    po = sub.add_parser("outcome")
    po.add_argument("decision_sha256")
    po.add_argument("--home", required=True)
    po.add_argument("--evidence", required=True, choices=_EVIDENCE)
    po.add_argument("--checked-by", dest="checked_by", default="owner:cli")
    po.add_argument("--note", default="")
    pv = sub.add_parser("overrides")
    pv.add_argument("--home", required=True)
    pv.add_argument("--json", action="store_true")


def _clock():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _outcome(args, stdout, stderr, stdin, isatty) -> int:
    if not isatty():
        stderr.write("outcome needs a real terminal; run it yourself\n")
        return 2
    stdout.write(f"outcome {args.evidence} for decision {args.decision_sha256[:12]}\n"
                 "type the first six characters of the decision seal to confirm:\n")
    if stdin.readline().strip() != args.decision_sha256[:6]:
        stderr.write("confirmation did not match; nothing recorded\n")
        return 1
    try:
        rec = record_outcome(args.home, _clock, args.decision_sha256, args.evidence,
                             checked_by=args.checked_by, note=args.note)
    except ValueError as exc:
        stderr.write(f"{exc}\n")
        return 1
    stdout.write(json.dumps({"verdict_on_decision": rec["verdict_on_decision"],
                             "self_check": rec["self_check"]}) + "\n")
    return 0


def _overrides(args, stdout) -> int:
    rep = report(args.home)
    if args.json:
        stdout.write(json.dumps(rep) + "\n")
        return 0
    stdout.write(f"owner decisions {rep['owner_decisions']}  reason codes {rep['reason_codes']}\n")
    for rule, row in rep["by_rule"].items():
        rate = "-" if row["override_rate"] is None else f"{row['override_rate']:.2f}"
        stdout.write(f"{rule:40} holds {row['holds']:4}  override rate {rate:>5}  "
                     f"outcomes {row['outcomes']}\n")
    if rep["other_alarm"]:
        stdout.write("alarm: more than one decision in ten is coded 'other'; the list is missing a reason\n")
    if rep["uncoded_alarm"]:
        stdout.write("alarm: some owner decisions carry no reason code\n")
    stdout.write(rep["does_not_prove"] + "\n")
    return 0


def dispatch(args, stdout, stderr, stdin, isatty) -> int:
    if args.cmd == "outcome":
        return _outcome(args, stdout, stderr, stdin, isatty)
    return _overrides(args, stdout)
