"""`flywheel traces delete` and `flywheel traces verify-gone` (7.10).

`delete --trace-ref agt_... --turn-ref turn_... --import-ref imp_...
--session client:id` prints the plan: what goes per store, keys to destroy,
receipts, copies outside reach with the command that removes each, residue
to expect, and the plan digest.
`delete --apply --plan-digest <d>` runs exactly that plan after presence.
`verify-gone` reads a phrase without echo (or from standard input), never
from the command line, and reports hits per file, never text.
"""
from __future__ import annotations

import getpass
import sys

from .trace_cli_text import emit, escape


def _context():
    from .operation_grants import load_or_create_owner_ref
    from .trace_inventory_scan import resolve_roots
    roots = resolve_roots()
    return roots, load_or_create_owner_ref(roots["home"])


def _selection(args) -> dict:
    selection = {}
    if args.trace_ref:
        selection["trace_refs"] = args.trace_ref
    if args.turn_ref:
        selection["turn_refs"] = args.turn_ref
    if args.session:
        client, _, session_id = args.session.partition(":")
        selection["session"] = {"client": client, "session_id": session_id}
    for flag, key in (("import_ref", "import_refs"), ("receipt_eid", "receipt_eids"), ("note_ref", "note_refs"),
                      ("legacy_run", "legacy_runs")):
        if getattr(args, flag):
            selection[key] = getattr(args, flag)
    return selection


def _print_plan(plan: dict) -> None:
    from .trace_enc import default_provider
    encrypting = default_provider().name != "none"
    emit("Deletion plan")
    for store, count in sorted(plan["counts"].items()):
        first = ", keys destroyed first" if encrypting and store in plan["keys"] else ""
        emit(f"  {store}: {count} items{first}")
    if plan["receipts"]:
        emit(f"  store.db: {len(plan['receipts'])} turn receipts (commitments only)")
    for where, count in sorted(plan["out_of_reach"].items()):
        emit(f"  outside reach: {where} x{count}")
    for client, command in plan["remedies"].items():
        emit(f"  {client} keeps its own transcript; remove it with: {escape(command)}")
    emit(f"  residue: {plan['residue_forecast']}")
    for note in plan["notes"]:
        emit(f"  note: {note}")
    emit(f"  not covered by any deletion yet: {', '.join(plan['not_covered'])}")
    emit(f"Plan digest {plan['plan_digest']}")
    emit(f"Apply with: flywheel traces delete --apply --plan-digest {plan['plan_digest']}")


def _apply(args, roots, owner) -> int:
    from .trace_delete_apply import apply_plan
    from .trace_delete_plan import PlanError
    from .trace_presence import PresenceError, adopted_method, confirm
    from .trace_presence_verifiers import verifier_for
    state = roots["home"] / "state"
    try:
        method = adopted_method(state, owner)
        from .trace_presence_summary import describe
        ref = confirm(state, owner, "delete_apply", args.plan_digest,
                      describe(roots["home"], owner, "delete_apply", args.plan_digest),
                      verifier=verifier_for(method, interactive=True))
        report = apply_plan(roots["home"], owner, args.plan_digest, ref)
    except (PresenceError, PlanError) as exc:
        emit(f"Not deleted ({exc.code}).")
        return 1
    emit(f"{report['state']}" + (f" ({report.get('reason')})" if report.get("reason") else ""))
    emit(f"  presence: {report['presence']} {report['presence_statement']}".rstrip())
    emit(f"  residue: {report['residue']}; outside reach: {report['out_of_reach']}")
    return 0 if report["state"] == "DELETED" else 1


def delete(args) -> int:
    from .trace_delete_plan import PlanError, make_plan
    roots, owner = _context()
    if args.apply:
        return _apply(args, roots, owner)
    try:
        _print_plan(make_plan(roots["home"], owner, _selection(args)))
    except PlanError as exc:
        emit(f"No plan ({exc.code}).")
        return 1
    return 0


def verify_gone(args) -> int:
    from pathlib import Path
    from .trace_residual_scan import Needles, scan_paths
    roots, _ = _context()
    if args.text_file:
        phrase = Path(args.text_file).read_text(encoding="utf-8")
        emit(f"Read the phrase from {escape(args.text_file)}; that file is a new copy of it. "
             "Remove it when you are done.")
    elif sys.stdin.isatty():
        phrase = getpass.getpass("Phrase to look for (not shown): ")
    else:
        phrase = sys.stdin.read()
    phrase = phrase.strip()
    files = [p for base in (roots["home"], roots["run"]) if Path(base).is_dir()
             for p in Path(base).rglob("*") if p.is_file()]
    labels = {p: str(p.relative_to(roots["home"] if roots["home"] in p.parents else roots["run"]))
              for p in files}
    report = scan_paths(files, Needles.build([phrase]), labels=labels)
    for label, hits in sorted(report["per_file"].items()):
        emit(f"  {escape(label)}: {hits} hits")
    if report["structural_only"]:
        emit("The phrase is shorter than 16 bytes, so only structural checks apply.")
    skipped = report["unsearched"]
    if skipped["encrypted"]:
        emit(f"{skipped['encrypted']} encrypted custody files were not searched: they are "
             "ciphertext, so a zero count says nothing about them. A deleted item's key is "
             "destroyed; flywheel traces status shows what custody still holds.")
    if skipped["compressed"]:
        emit(f"{skipped['compressed']} compressed files could not be opened and were not "
             "searched.")
    emit(f"{report['total']} hits in the plaintext files Flywheel controls. Freed disk space, "
         "backups and copies outside Flywheel are not searched.")
    return 0 if report["total"] == 0 else 1


def register(sub) -> None:
    parser = sub.add_parser("delete", help="plan, then apply, a deletion with its closure")
    parser.add_argument("--trace-ref", action="append", default=[])
    parser.add_argument("--turn-ref", action="append", default=[])
    parser.add_argument("--session", help="client:session-id: every captured turn and "
                                          "imported transcript of that session")
    parser.add_argument("--import-ref", action="append", default=[])
    parser.add_argument("--receipt-eid", action="append", default=[])
    parser.add_argument("--note-ref", action="append", default=[])
    parser.add_argument("--legacy-run", action="append", default=[])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--plan-digest")
    parser.set_defaults(run=delete)
    gone = sub.add_parser("verify-gone", help="search custody files for a phrase you deleted")
    gone.add_argument("--text-file", help="read the phrase from a file (a new copy of it)")
    gone.set_defaults(run=verify_gone)
