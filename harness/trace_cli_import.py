"""`flywheel traces import claude-code [--apply] [--json]` (7.6).

Without `--apply` it only plans: counts and bytes per state, free space
against need, transcripts at risk from the client's sweep, files refused
(links) and files it will not import, each named. With `--apply` it imports
the planned sources. Every name taken from the client's folder is printed
with control characters escaped.
"""
from __future__ import annotations

import json

from .trace_cli_text import emit, escape


def _home():
    from .trace_inventory_scan import resolve_roots
    return resolve_roots()["home"]


def _summary(plan: dict) -> list[str]:
    counts: dict[str, list[int]] = {}
    for item in plan["items"]:
        row = counts.setdefault(item["state"], [0, 0])
        row[0] += 1
        row[1] += item["size"]
    lines = [f"{plan['client']} import plan: {plan['state']}"]
    lines += [f"  {state}: {n} files, {size} bytes" for state, (n, size) in sorted(counts.items())]
    if "need" in plan:
        lines.append(f"  needs {plan['need']} bytes; {plan['free']} free on the custody volume")
    sweep = plan.get("sweep") or {}
    if sweep:
        lines.append(f"  sweep risk: {sweep['at_risk']} transcripts within 7 days of Claude "
                     f"Code's {sweep['cleanup_period_days']}-day cleanup ({sweep['source']})")
    for row in plan["refused"]:
        lines.append(f"  refused {escape(row['rel'])}: {row['reason']}")
    for row in plan["not_imported"]:
        extra = f" ({row['flag']})" if row.get("flag") else ""
        count = f", {row['count']} files" if row.get("count") else (
            f", {row['bytes']} bytes, {row['note']}" if row.get("note") else "")
        lines.append(f"  not imported {escape(row['name'])}: {row['reason']}{count}{extra}")
    return lines


def run(args) -> int:
    if args.pending:
        return pending(args)
    if args.client is None:
        emit("Name a client (claude-code or codex) or pass --pending.")
        return 2
    from .trace_import_claude import plan_claude
    from .trace_import_codex import plan_codex
    from .trace_import_core import run_import
    home = _home()
    plan = (plan_codex if args.client == "codex" else plan_claude)(home)
    if args.json:
        print(json.dumps({k: v for k, v in plan.items() if k != "owner_ref"}, indent=2,
                         sort_keys=True, default=str))
    else:
        for line in _summary(plan):
            emit(line)
    if not args.apply:
        if not args.json:
            emit("Nothing was imported. Run again with --apply to import.")
        return 0 if plan["state"] == "OK" else 1
    result = run_import(home, plan)
    emit(f"Imported {result['imported']} files ({result['bytes']} bytes); skipped "
         f"{sum(result['skipped'].values())}, refused {sum(result['refused'].values())}.")
    for code, n in sorted({**result["skipped"], **result["refused"]}.items()):
        emit(f"  {code}: {n}")
    return 0 if result["state"] == "OK" else 1


def pending(args) -> int:
    """Import the sessions whose SessionEnd archive could not reach the gateway."""
    from .capture_hooks import spool
    from .operation_grants import load_or_create_owner_ref
    from .trace_import_session import SessionRefused, import_session
    from .trace_capture_settings import effective
    home = _home()
    owner = load_or_create_owner_ref(home)
    if effective(home, owner)["archive_transcripts"] != "on":
        emit("The transcript archive is off, so nothing was imported. A hook spools a "
             "session end whenever the gateway is down, whatever the setting; turn the "
             "archive on (flywheel traces capture archive on) to import them, or clear "
             "them with flywheel traces doctor --ack.")
        return 0
    directory, done, empty = spool.spool_dir(home), 0, 0
    for path in sorted(directory.glob("f-*.json")) if directory.is_dir() else []:
        record = json.loads(path.read_bytes())
        if record.get("event") != "session-end" or not record.get("session_id"):
            continue
        try:
            result = import_session(home, owner, record["client"], record["session_id"])
        except SessionRefused as refused:
            emit(f"  {escape(record['session_id'])}: {refused.code}")
            continue
        if result["imported"] or result["skipped"]:
            (directory / "acknowledged").mkdir(exist_ok=True)
            path.replace(directory / "acknowledged" / path.name)
            done, empty = (done + 1, empty) if result["imported"] else (done, empty + 1)
    tail = f", {empty} had nothing new to import" if empty else ""
    emit(f"{done} pending session{'' if done == 1 else 's'} imported{tail}.")
    return 0


def register(sub) -> None:
    parser = sub.add_parser("import", help="copy client transcripts into custody (encrypted where an OS key store "
                             "is available)")
    parser.add_argument("client", nargs="?", choices=("claude-code", "codex"))
    parser.add_argument("--pending", action="store_true",
                        help="import sessions the SessionEnd archive spooled")
    parser.add_argument("--apply", action="store_true", help="import; without it, plan only")
    parser.add_argument("--json", action="store_true", help="print the plan as JSON")
    parser.set_defaults(run=run)
