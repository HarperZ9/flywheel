"""cli.py -- `flywheel monitor ...`: the owner's command line.

coverage prints every path and its PRE / POST / NONE state; pending lists open
holds; approve and reject decide one hold, and both need a real terminal and
the typed confirmation code, so an agent's shell cannot drive them; verify
re-walks a store and exits 1 on DRIFT; install prints or writes the hook
settings block. owner, witness, import-ocsf and sandbox live in cli_extra.py;
outcome and overrides live in cli_overrides.py. approve and reject take an
optional --reason-code from a fixed list and an optional --reason text.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import cli_extra, cli_overrides, coverage
from .overrides import REASON_CODES
from .owner import OwnerConfigError
from .escalate import Escalator
from .install import importable, settings_block
from .verify import verify_store


def _clock():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _decide(args, decision, stdout, stderr, stdin, isatty) -> int:
    if not isatty():
        stderr.write("approve and reject need a real terminal; run them yourself\n")
        return 2
    esc = Escalator(args.home, _clock)
    try:
        pending = esc.read_pending(args.hold_id)
    except KeyError:
        stderr.write(f"no open hold {args.hold_id}\n")
        return 2
    stdout.write(f"{decision} {pending['proposed_action']['tool']} "
                 f"{json.dumps(pending['proposed_action']['args'])[:300]}\n")
    stdout.write(f"type the code to confirm: {pending['confirm_code']}\n")
    typed = stdin.readline().strip()
    if typed != pending["confirm_code"]:
        stderr.write("code did not match; no decision made\n")
        return 1
    try:
        esc.decide(args.hold_id, decision, decider="owner:cli",
                   reason=args.reason, reason_code=args.reason_code)
    except ValueError as exc:
        stderr.write(f"{exc}\n")
        return 1
    stdout.write(f"{decision}\n")
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="flywheel monitor")
    sub = p.add_subparsers(dest="cmd", required=True)
    pc = sub.add_parser("coverage"); pc.add_argument("--home", required=True); pc.add_argument("--json", action="store_true")
    pp = sub.add_parser("pending"); pp.add_argument("--home", required=True); pp.add_argument("--json", action="store_true")
    for name in ("approve", "reject"):
        sp = sub.add_parser(name); sp.add_argument("hold_id"); sp.add_argument("--home", required=True)
        sp.add_argument("--reason-code", dest="reason_code", default="", choices=("",) + REASON_CODES)
        sp.add_argument("--reason", default="")
    pv = sub.add_parser("verify"); pv.add_argument("home")
    pi = sub.add_parser("install"); pi.add_argument("client", choices=("claude-code", "codex"))
    pi.add_argument("--home", required=True); pi.add_argument("--print", dest="do_print", action="store_true")
    pi.add_argument("--python", default=sys.executable)
    pi.add_argument("--owner-config", dest="owner_config", default="")
    cli_extra.register(sub)
    cli_overrides.register(sub)
    return p


def _dispatch_split(args, stdout, stderr, stdin, isatty) -> int:
    """Commands that live in cli_overrides.py and cli_extra.py."""
    if args.cmd in cli_overrides.COMMANDS:
        return cli_overrides.dispatch(args, stdout, stderr, stdin, isatty)
    try:
        return cli_extra.dispatch(args, stdout, stderr)
    except OwnerConfigError as exc:
        stderr.write(f"{exc}\n")
        return 2


def main(argv=None, *, stdout=None, stderr=None, stdin=None, isatty=None) -> int:
    stdout = stdout if stdout is not None else sys.stdout
    stderr = stderr if stderr is not None else sys.stderr
    stdin = stdin if stdin is not None else sys.stdin
    isatty = isatty or (lambda: sys.stdin.isatty() and sys.stdout.isatty())
    p = _parser()
    try:
        args = p.parse_args([a for a in (argv if argv is not None else sys.argv[1:])])
    except SystemExit as exc:
        return int(exc.code or 2)

    if args.cmd in cli_overrides.COMMANDS + cli_extra.COMMANDS:
        return _dispatch_split(args, stdout, stderr, stdin, isatty)
    if args.cmd == "coverage":
        rows = coverage.rows()
        if args.json:
            stdout.write(json.dumps(rows))
        else:
            for r in rows:
                stdout.write(f"{r['path_id']:4} {r['state']:7} {r['domain']:7} "
                             f"{r['description']} [{r['boundary']}]\n")
        return 0
    if args.cmd == "pending":
        items = Escalator(args.home, _clock).pending()
        if args.json:
            stdout.write(json.dumps(items))
        else:
            for it in items:
                stdout.write(f"{it['hold_id']}  {it['verdict']}  {it['proposed_action']['tool']}\n")
        return 0
    if args.cmd in ("approve", "reject"):
        decision = "APPROVED_ONCE" if args.cmd == "approve" else "REJECTED"
        return _decide(args, decision, stdout, stderr, stdin, isatty)
    if args.cmd == "verify":
        report = verify_store(args.home)
        stdout.write(json.dumps(report) + "\n")
        return 0 if report["verdict"] == "MATCH" else 1
    if args.cmd == "install":
        ok, detail = importable(args.python)
        if not ok:
            stderr.write(f"{args.python} cannot import the hook with -P -E ({detail}); a hook "
                         "that cannot import exits 1, which the harness treats as allow. "
                         "Install flywheel into that interpreter first.\n")
            return 1
        block = settings_block(args.client, python=args.python, home=args.home,
                               owner_config=args.owner_config)
        stdout.write(json.dumps(block))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
