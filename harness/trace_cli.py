"""`flywheel traces`: see where your traces are and what can be done with them.

`status` lists every store the tools keep trace-derived data in: location
(relative to FLYWHEEL_HOME or the run root), data classes, protection,
retention, declared caps, what is on disk now, and whether export and delete
exist or which package closes the gap. It also lists every entry nobody
registered and every store not yet classified. It reads and writes nothing
else: no owner identity, no directory, no ledger line is created.

Each later subcommand lives in its own module and registers here through a
literal import, so a frozen build finds it.
"""
from __future__ import annotations

import argparse
import json

from . import trace_inventory as inv
from .trace_cli_text import emit, escape


def _size(n: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024 or unit == "GiB":
            return f"{n} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"


def _protection(p: dict, encryption: dict | None = None) -> str:
    if p["kind"] == "encrypted" and encryption is not None:
        return encryption["protection"]
    if p["kind"] == "plaintext-exception":
        return f"plaintext (exception: {p['reason']}; closes in {p['package']})"
    if p["kind"] == "outside-custody":
        return f"outside Flywheel custody ({p['reason']})"
    return p["kind"].replace("-", " ")


def _operation(op: dict) -> str:
    if op["state"] == "gap":
        return f"none (gap: {op['package']}): {op['reason']}"
    return "available"


def _observed(o: dict) -> str:
    text = f"{o['files']} file{'' if o['files'] == 1 else 's'}, {_size(o['bytes'])}"
    if o["first"]:
        text += f", {o['first']} to {o['last']}"
    return text + ("" if o["complete"] else " (count stopped at its bound)")


def _store_lines(row: dict, encryption: dict | None = None) -> list[str]:
    classes = ("UNCLASSIFIED" if row["classes"] is None else
               ", ".join(f"{c} {inv.CLASS_NAMES[c]}" for c in row["classes"]))
    lines = [f"{row['id']:<5} {escape(row['name'])}",
             f"      location    {escape(row['location'])}",
             f"      classes     {classes} ({row['evidence']})",
             f"      protection  {_protection(row['protection'], encryption)}",
             f"      retention   {row['retention']}"]
    lines += [f"      cap         {c['what']}: {c['behavior']}" for c in row["caps"]]
    lines += [f"      observed    {_observed(row['observed'])}",
              f"      export      {_operation(row['operations']['export'])}",
              f"      delete      {_operation(row['operations']['delete'])}"]
    if row["note"]:
        lines.append(f"      note        {row['note']}")
    return lines


def render_status(doc: dict, roots: dict) -> list[str]:
    lines = ["Flywheel trace custody",
             f"home {escape(roots['home'])}", f"run root {escape(roots['run'])}",
             f"Retention default: {doc['retention_default']}.", ""]
    presence = doc.get("presence")
    if presence:
        lines.insert(4, f"Presence: {presence['method']}: {presence['statement']}.")
    encryption = doc.get("encryption")
    if encryption:
        floored = ", ".join(sorted(encryption["floors"])) or "none yet"
        lines.insert(4, f"Encryption: {encryption['protection']}; floor set for {floored}.")
    for row in doc["stores"]:
        lines += _store_lines(row, encryption)
    lines.append("")
    by_id = {row["id"]: row for row in doc["stores"]}
    lines += [f"UNCLASSIFIED {sid} {escape(by_id[sid]['name'])}: {by_id[sid]['note']}"
              for sid in doc["unclassified"]]
    lines += [f"UNREGISTERED {u['root']}/{escape(u['name'])} ({u['files']} files, "
              f"{_size(u['bytes'])})" for u in doc["unregistered"]]
    ledger = doc["ledger"]
    state = "chain ok" if ledger["ok"] else f"FAILED ({ledger['reason']})"
    lines.append(f"Custody ledger: {ledger.get('entries', 0)} entries, {state}; "
                 f"{ledger.get('losses', 0)} loss records")
    return lines


def _status(args) -> int:
    from .trace_inventory_scan import resolve_roots, scan
    doc = scan()
    if args.json:
        print(json.dumps(doc, indent=2, sort_keys=True))
        return 0
    for line in render_status(doc, resolve_roots()):
        emit(line)
    return 0


def _home():
    from .trace_inventory_scan import resolve_roots
    return resolve_roots()["home"]


def _doctor(args) -> int:
    from . import trace_doctor
    results = trace_doctor.run_doctor(_home(), synthetic=args.synthetic, ack=args.ack)
    if args.json:
        print(json.dumps(trace_doctor.to_json(results), indent=2, sort_keys=True))
    else:
        for line in trace_doctor.render(results):
            emit(line)
    return 1 if any(c.state == "FAIL" for c in results) else 0


def _print_mount(args) -> int:
    from .trace_doctor import print_mount
    for line in print_mount():
        emit(line)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flywheel traces",
        description="See, keep, move, prove and destroy the traces your agents leave.")
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status", help="every trace store, its protection and its gaps")
    status.add_argument("--json", action="store_true",
                        help="print the flywheel.trace-inventory/v1 document")
    status.set_defaults(run=_status)
    doctor = sub.add_parser("doctor", help="check hook mounts, the capture channel and custody")
    doctor.add_argument("--synthetic", action="store_true",
                        help="record one synthetic turn through the Flywheel hook module")
    doctor.add_argument("--ack", action="store_true", help="move reported failures aside")
    doctor.add_argument("--json", action="store_true", help="print flywheel.trace-doctor/v1")
    doctor.set_defaults(run=_doctor)
    from . import trace_cli_presence
    trace_cli_presence.register(sub)
    hooks = sub.add_parser("hooks", help="hook mount lines for Claude Code and Codex")
    hooks_sub = hooks.add_subparsers(dest="hooks_command", required=True)
    hooks_sub.add_parser("print-mount", help="print the exact mount blocks").set_defaults(
        run=_print_mount)
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
