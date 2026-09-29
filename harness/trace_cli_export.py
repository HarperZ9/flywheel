"""`flywheel traces export --out <dir>` and `flywheel traces verify-export` (7.5).

`export` prints what would leave custody (items and bytes per store, their
data classes and the redaction mode), asks for a typed yes unless `--yes`,
then asks presence for the exact destination and options, and writes the
export. `--grant` instead writes a one-use grant naming the destination for
the gateway's export route and prints the digest to confirm. `verify-export`
runs the standard-library verifier on an export folder or zip.
"""
from __future__ import annotations

from .trace_cli_text import emit, escape

_CLASSES = {"S1": "content, tool I/O, metadata, hashes", "CT": "content, metadata, hashes",
            "IM": "content, tool I/O, reasoning, metadata, credentials, personal data"}


def _context():
    from .operation_grants import load_or_create_owner_ref
    from .trace_inventory_scan import resolve_roots
    home = resolve_roots()["home"]
    return home, load_or_create_owner_ref(home)


def _options(args) -> dict:
    return {"redact": not args.no_redact, "redact_personal": args.redact_personal,
            "stable_tags": args.stable_tags, "zip": args.zip,
            "allow_sync_root": args.allow_sync_root}


def _preview(home, owner, options: dict) -> None:
    from .trace_retention_items import all_items
    listed = all_items(home, owner)
    for store in ("S1", "CT", "IM"):
        mine = [i for i in listed if i["store"] == store]
        emit(f"  {store}: {len(mine)} items, {sum(i['bytes'] for i in mine)} bytes stored "
             f"({_CLASSES[store]})")
    emit("  plus capture snapshots cited by turns and the deletion tombstones")
    emit("  redaction: " + ("none; credentials leave custody as stored" if not options["redact"]
                            else "credentials" + (" and personal data" if
                                                  options["redact_personal"] else "")))


def _confirm_text(args) -> bool:
    if args.yes:
        return True
    try:
        return input("Write this plaintext copy outside custody? Type yes: ").strip() == "yes"
    except EOFError:
        return False


def _run(home, owner, args, options) -> int:
    from .trace_export import export, export_digest
    from .trace_presence import adopted_method, confirm
    from .trace_presence_summary import export_summary
    from .trace_presence_verifiers import verifier_for
    state, digest = home / "state", export_digest(args.out, options)
    verifier = verifier_for(adopted_method(state, owner), interactive=True)
    summary = export_summary(args.out, options)
    ref = confirm(state, owner, "export", digest, summary, verifier=verifier)
    sync_ref = confirm(state, owner, "export_allow_sync_root", digest,
                       "Allow a destination under a sync folder. " + summary,
                       verifier=verifier) if args.allow_sync_root else None
    report = export(home, owner, args.out, ref, sync_presence_ref=sync_ref, **options)
    if report["state"] != "EXPORTED":
        emit(f"Not finished ({report['reason']}); the partial folder is "
             f"{escape(report['path'])}.")
        return 1
    emit(f"Exported {report['items']} items, {report['bytes']} bytes to "
         f"{escape(report['path'])} (verify: {report['verify']}).")
    emit(f"Check it any time with: python {escape(report['path'])}/verify.py "
         f"{escape(report['path'])}")
    return 0


def _grant_presence(home, owner: str) -> str:
    """What confirms a granted export under the presence method in effect."""
    from .trace_presence import PresenceError, adopted_method
    try:
        method = adopted_method(home / "state", owner)
    except PresenceError as exc:
        return f"The export route refuses it until presence is set again ({exc.code})."
    if method == "none":
        return ("The export route runs it; with presence method none, nothing is asked and "
                "any process holding the gateway token can run it.")
    return "The export route runs it after Windows Hello confirms on this machine."


def export_command(args) -> int:
    from .trace_export_dest import ExportError, create_grant
    from .trace_presence import PresenceError
    home, owner = _context()
    options = _options(args)
    try:
        if args.grant:
            grant = create_grant(home, owner, args.out, options)
            emit(f"Grant {grant['grant_ref']} for {escape(grant['destination'])}, export "
                 f"digest {grant['export_digest']}. {_grant_presence(home, owner)}")
            return 0
        emit("This export would write:")
        _preview(home, owner, options)
        if not _confirm_text(args):
            emit("Nothing was written.")
            return 1
        return _run(home, owner, args, options)
    except (ExportError, PresenceError) as exc:
        emit(f"Not exported ({exc.code}).")
        return 1


def verify_command(args) -> int:
    from .trace_export_verify import main
    return main([args.path])


def register(sub) -> None:
    parser = sub.add_parser("export", help="write a verifiable plaintext copy of your traces")
    parser.add_argument("--out", required=True, help="a new folder outside custody (it must not exist yet)")
    parser.add_argument("--no-redact", action="store_true",
                        help="keep credentials as stored (they are redacted by default)")
    parser.add_argument("--redact-personal", action="store_true",
                        help="also redact personal data")
    parser.add_argument("--stable-tags", action="store_true",
                        help="placeholder tags that match across exports")
    parser.add_argument("--zip", action="store_true", help="write one .zip instead of a folder")
    parser.add_argument("--allow-sync-root", action="store_true",
                        help="allow a destination under a sync folder (asks presence)")
    parser.add_argument("--yes", action="store_true", help="skip the typed confirmation")
    parser.add_argument("--grant", action="store_true",
                        help="write a one-use grant for the gateway's export route")
    parser.set_defaults(run=export_command)
    verify = sub.add_parser("verify-export", help="verify an export folder or zip")
    verify.add_argument("path")
    verify.set_defaults(run=verify_command)
