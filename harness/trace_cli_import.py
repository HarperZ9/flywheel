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
    lines = [f"Claude Code import plan: {plan['state']}"]
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
        count = f", {row['count']} files" if row.get("count") else ""
        lines.append(f"  not imported {escape(row['name'])}: {row['reason']}{count}{extra}")
    return lines


def run(args) -> int:
    from .trace_import_claude import plan_claude
    from .trace_import_core import run_import
    home = _home()
    plan = plan_claude(home)
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


def register(sub) -> None:
    parser = sub.add_parser("import", help="copy client transcripts into encrypted custody")
    parser.add_argument("client", choices=("claude-code",))
    parser.add_argument("--apply", action="store_true", help="import; without it, plan only")
    parser.add_argument("--json", action="store_true", help="print the plan as JSON")
    parser.set_defaults(run=run)
