"""`flywheel traces retention show | set | adopt | plan | apply` (7.4).

The default is keep until you delete. `set` writes the policy file and
adopts it with presence in one step; `adopt` adopts a file edited by hand.
`plan` prints what the adopted policy would delete now and keeps that plan
pending; `apply --plan-digest <d>` runs the pending plan after presence.
"""
from __future__ import annotations

from .trace_cli_text import emit


def _context():
    from .operation_grants import load_or_create_owner_ref
    from .trace_inventory_scan import resolve_roots
    home = resolve_roots()["home"]
    return home, load_or_create_owner_ref(home)


def _rule_text(rule: dict) -> str:
    from .trace_retention import rule_text
    return rule_text(rule)


def show(args) -> int:
    from .trace_retention import effective
    from .trace_retention_schedule import status
    home, owner = _context()
    current, state = effective(home, owner), status(home, owner)
    if current["action"] == "keep":
        emit("Retention: keep until you delete. Nothing is deleted on a timer.")
    else:
        emit(f"Retention rules (at most {current['max_share_per_run']:.0%} of a store per run "
             "without your confirmation):")
        for rule in current["rules"]:
            emit(f"  {_rule_text(rule)}")
    if current["tampered"]:
        emit("SETTINGS_TAMPERED: the adopted policy file does not match your custody ledger, "
             "so keep is in effect. Adopt the policy again with: flywheel traces retention adopt")
    if current["pending_change"]:
        emit("A change on disk is not in effect. Adopt it with: flywheel traces retention adopt")
    if state["pending_plan"]:
        plan = state["pending_plan"]
        emit(f"Pending plan {plan['plan_digest']}: {plan['items']} items ({plan['reason']}). "
             f"Apply with: flywheel traces retention apply --plan-digest {plan['plan_digest']}")
    if state["last_run"]:
        emit(f"Last run: {state['last_run']['state']} ({state['last_run']['reason']}) "
             f"at {state['last_run']['at']}")
    return 0


def _adopt(home, owner) -> int:
    from .trace_presence import PresenceError, adopted_method, confirm
    from .trace_presence_verifiers import verifier_for
    from .trace_retention import adopt, digest, read_file
    on_disk, valid = read_file(home)
    if not valid or on_disk is None:
        emit("The retention file is missing or invalid; nothing was adopted.")
        return 1
    summary = "keep until you delete" if on_disk["action"] == "keep" else "; ".join(
        _rule_text(r) for r in on_disk["rules"])
    try:
        method = adopted_method(home / "state", owner)
        ref = confirm(home / "state", owner, "retention_adopt", digest(on_disk),
                      "Adopt retention: " + summary,
                      verifier=verifier_for(method, interactive=True))
        report = adopt(home, owner, ref)
    except PresenceError as exc:
        emit(f"Not adopted ({exc.code}).")
        return 1
    emit(f"Adopted: {summary} (presence: {report['presence']}; witness: {report['witness']}).")
    if on_disk["action"] != "keep":
        emit("The first run only plans; nothing is deleted until the run after it.")
    return 0


def adopt_file(args) -> int:
    home, owner = _context()
    return _adopt(home, owner)


def set_policy(args) -> int:
    from .trace_retention import write_file
    home, owner = _context()
    rule = {k: getattr(args, k) for k in ("max_age_days", "max_items", "max_bytes")
            if getattr(args, k) is not None}
    if args.keep:
        doc = {"action": "keep", "rules": []}
    elif rule:
        doc = {"action": "rules", "rules": [{"store": args.store, "reason_code": args.reason,
                                             **rule}], "max_share_per_run": args.max_share}
    else:
        emit("Name --keep or at least one of --max-age-days, --max-items, --max-bytes.")
        return 2
    try:
        write_file(home, doc)
    except ValueError as exc:
        emit(f"Not written ({exc}).")
        return 1
    return _adopt(home, owner)


def plan(args) -> int:
    from .trace_retention_schedule import plan_now
    home, owner = _context()
    result = plan_now(home, owner)
    if result["state"] != "PLANNED":
        emit({"KEEP": "Retention is keep; there is nothing to plan.",
              "NOTHING_DUE": "No item is due under the adopted rules."}[result["state"]])
        return 0
    shares = ", ".join(f"{s} {v:.0%}" for s, v in sorted(result["share"].items()))
    emit(f"Plan {result['plan_digest']}: {result['items']} items ({shares} of each store).")
    emit(f"Apply with: flywheel traces retention apply --plan-digest {result['plan_digest']}")
    return 0


def apply(args) -> int:
    from .trace_presence import PresenceError, adopted_method, confirm
    from .trace_presence_verifiers import verifier_for
    from .trace_retention_schedule import apply_pending
    home, owner = _context()
    try:
        method = adopted_method(home / "state", owner)
        from .trace_presence_summary import describe
        ref = confirm(home / "state", owner, "retention_apply", args.plan_digest,
                      describe(home, owner, "retention_apply", args.plan_digest),
                      verifier=verifier_for(method, interactive=True))
        result = apply_pending(home, owner, args.plan_digest, ref)
    except PresenceError as exc:
        emit(f"Not applied ({exc.code}).")
        return 1
    emit(result["state"] + (f" ({result['reason']})" if result.get("reason") else ""))
    return 0 if result["state"] == "APPLIED" else 1


def register(sub) -> None:
    parser = sub.add_parser("retention", help="how long custody keeps traces")
    commands = parser.add_subparsers(dest="retention_command", required=True)
    commands.add_parser("show", help="the policy in effect, pending changes and plans"
                        ).set_defaults(run=show)
    commands.add_parser("adopt", help="adopt the policy file, with presence").set_defaults(
        run=adopt_file)
    setter = commands.add_parser("set", help="write one rule (or keep) and adopt it")
    setter.add_argument("--keep", action="store_true")
    setter.add_argument("--store", choices=("S1", "CT", "IM"), default="S1")
    setter.add_argument("--max-age-days", type=int)
    setter.add_argument("--max-items", type=int)
    setter.add_argument("--max-bytes", type=int)
    setter.add_argument("--max-share", type=float, default=0.10)
    setter.add_argument("--reason", default="owner_retention_rule")
    setter.set_defaults(run=set_policy)
    commands.add_parser("plan", help="what the policy would delete now").set_defaults(run=plan)
    applier = commands.add_parser("apply", help="apply the pending plan, with presence")
    applier.add_argument("--plan-digest", required=True)
    applier.set_defaults(run=apply)
