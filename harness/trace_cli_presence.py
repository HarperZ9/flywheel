"""`flywheel traces presence show|set`: the owner-presence method in effect.

`set` changes the method only after the method already in effect confirms
the change, so an agent cannot quietly downgrade it; with `none` in effect
that confirmation is a typed yes, which an agent can give too, and the output
says so.
"""
from __future__ import annotations

from .trace_cli_text import emit


def _state():
    from .trace_inventory_scan import resolve_roots
    return resolve_roots()["state"]


def show(args) -> int:
    from .trace_custody_ledger import read_owner_ref
    from .trace_presence import presence_status
    state = _state()
    owner = read_owner_ref(state.parent)
    status = presence_status(state, owner) if owner else {
        "method": "none", "statement": "no owner identity yet; nothing is gated"}
    emit(f"Presence method: {status['method']}")
    emit(f"  {status['statement']}")
    return 0


def set_method(args) -> int:
    from .operation_grants import load_or_create_owner_ref
    from .trace_presence import (PresenceError, adopted_method, confirm, method_digest,
                                 set_method as adopt)
    from .trace_presence_verifiers import verifier_for
    state = _state()
    owner = load_or_create_owner_ref(state.parent)
    try:
        current = adopted_method(state, owner)
        ref = confirm(state, owner, "presence_method", method_digest(args.method),
                      f"Change the presence method from {current} to {args.method}",
                      verifier=verifier_for(current, interactive=True))
        report = adopt(state, owner, args.method, ref)
    except PresenceError as exc:
        emit(f"Not changed ({exc.code}).")
        return 1
    emit(f"Presence method is now {args.method} (confirmed by {report['presence']}; "
         f"witness: {report['witness']}).")
    return 0


def register(sub) -> None:
    parser = sub.add_parser("presence", help="the owner-presence method for custody operations")
    commands = parser.add_subparsers(dest="presence_command", required=True)
    commands.add_parser("show", help="the method in effect").set_defaults(run=show)
    change = commands.add_parser("set", help="change the method, confirmed by the current one")
    change.add_argument("method", choices=("windows-hello", "none"))
    change.set_defaults(run=set_method)
