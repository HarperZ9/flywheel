"""`flywheel traces capture show | content on|off | confirm` (7.2).

Settings take effect only when adopted, and adoption needs presence bound to
the new settings' digest, so an agent that edits the file changes nothing
until the owner confirms. Switching content capture on says, once, what gets
stored where.
"""
from __future__ import annotations

from .trace_cli_text import emit


def _context():
    from .operation_grants import load_or_create_owner_ref
    from .trace_inventory_scan import resolve_roots
    home = resolve_roots()["home"]
    return home, load_or_create_owner_ref(home)


def show(args) -> int:
    from .trace_capture_settings import data_flow, effective
    home, owner = _context()
    current = effective(home, owner)
    for line in data_flow(current):
        emit(line)
    emit(f"Unanswered prompts become unpaired turns after {current['pending_ttl_hours']} hours.")
    if current.get("tampered"):
        emit("SETTINGS_TAMPERED: the adopted settings file does not match your custody ledger, "
             "so everything is off. Confirm the settings again with: "
             "flywheel traces capture confirm")
    elif current["pending_change"]:
        emit("A change on disk is not in effect. Confirm with: flywheel traces capture confirm")
    return 0


def _adopt(home, owner) -> int:
    from .trace_capture_settings import adopt, data_flow, digest, read_file
    from .trace_presence import PresenceError, adopted_method, confirm
    from .trace_presence_verifiers import verifier_for
    on_disk, valid = read_file(home)
    if not valid or on_disk is None:
        emit("The settings file is missing or invalid; nothing was adopted.")
        return 1
    try:
        method = adopted_method(home / "state", owner)
        ref = confirm(home / "state", owner, "capture_settings", digest(on_disk),
                      "Adopt capture settings: " + " ".join(data_flow(on_disk)),
                      verifier=verifier_for(method, interactive=True))
        report = adopt(home, owner, ref)
    except PresenceError as exc:
        emit(f"Not adopted ({exc.code}).")
        return 1
    for line in data_flow(on_disk):
        emit(line)
    emit(f"Adopted (presence: {report['presence']}; witness: {report['witness']}).")
    return 0


def confirm_file(args) -> int:
    home, owner = _context()
    return _adopt(home, owner)


def _first_on(switch: str) -> str:
    from .trace_capture_settings import kept
    how = kept()
    return {
        "content": "Content capture keeps a second copy of each prompt and final answer in "
                   f"your Flywheel home, {how}, beside the copy your client already keeps.",
        "archive_transcripts": "The transcript archive copies each ended Claude Code "
                               f"session's transcript into custody, {how}, when the "
                               "SessionEnd hook is mounted. Codex sessions are not archived.",
        "freeze_urls": "URL freezing sends the URLs each prompt names to the local gateway, "
                       f"which fetches them; the pages are {how}. Links that carry "
                       "credentials are refused and never fetched. The URLs and their sha256 "
                       "digests go into the model context, so to the model provider.",
    }[switch]


def set_switch(args) -> int:
    from .trace_capture_settings import write_file
    home, owner = _context()
    write_file(home, {args.switch: args.value})
    if args.value == "on":
        emit(_first_on(args.switch))
    return _adopt(home, owner)


def register(sub) -> None:
    parser = sub.add_parser("capture", help="what the capture hooks send and keep")
    commands = parser.add_subparsers(dest="capture_command", required=True)
    commands.add_parser("show", help="settings in effect and any pending change").set_defaults(
        run=show)
    commands.add_parser("confirm", help="adopt the settings file, with presence").set_defaults(
        run=confirm_file)
    for name, switch, text in (("content", "content", "keep prompt and answer text"),
                               ("archive", "archive_transcripts",
                                "import each ended Claude Code session's transcript"),
                               ("freeze", "freeze_urls", "fetch and keep the URLs prompts name")):
        command = commands.add_parser(name, help=text)
        command.add_argument("value", choices=("on", "off"))
        command.set_defaults(run=set_switch, switch=switch)
