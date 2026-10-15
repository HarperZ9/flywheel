"""scope_report.py -- `flywheel report scope`: calls that reached past what was allowed.

Built only from saved `flywheel code` session ledgers in the Flywheel home, with
no human labeling. Each trigger is read from one entry kind and one field or
text prefix, and each reported line names the session, the entry's sequence
number and its hash, so anyone can find the entry and check it. A session whose
chain does not verify is listed as unverifiable and counts for nothing.

The report names the trigger and the setting that caught the call. It says
nothing about why a model made the call: a refused call is a fact about the
call and the settings, and the cause sits in the model's training and the task.

What it cannot see: a backend falling back after a provider refusal is not on
the session ledger, so it is not reported. An empty report means none of these
triggers fired, not that the agent stayed in scope.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

SCHEMA = "flywheel.scope-report/v1"

TRIGGERS = {
    "plan_mode": "refused by plan mode",
    "deny_rule": "refused by a deny rule",
    "hook": "refused or blocked by a hook",
    "user_declined": "declined by the user",
    "tool_not_listed": "tool outside a subagent's tool list",
    "gate": "stopped by the command denylist or the pre-action monitor",
    "outside_project": "path outside the project folder",
    "repeated_refusal": "a refused call repeated unchanged later in the session",
}
_BY = {"mode:plan": "plan_mode", "hook": "hook", "hook:deny": "hook",
       "user:no": "user_declined", "agent:tool-not-listed": "tool_not_listed"}
_REFUSED = re.compile(r"^\[(denied|gate)\]|command blocked by denylist|escapes root|_path_escaped")
_ID = re.compile(r"^(\d{8})-\d{6}-[0-9a-f]{6}$")


def _approval_trigger(meta: dict) -> "str | None":
    if meta.get("decision") != "deny":
        return None
    by = str(meta.get("by", ""))
    return "deny_rule" if by.startswith("rule:deny:") else _BY.get(by)


def _result_trigger(text: str) -> "str | None":
    if "escapes root" in text or "_path_escaped" in text:
        return "outside_project"
    if text.startswith("[gate]") or "command blocked by denylist" in text:
        return "gate"
    return None


def scan_ledger(entries: list) -> list:
    """(trigger, entry) pairs for one verified session ledger."""
    found, refused_calls, last_call = [], set(), None
    for e in entries:
        if e.kind == "approval":
            t = _approval_trigger(e.meta or {})
            if t:
                found.append((t, e))
        elif e.kind == "blocked":
            found.append(("hook", e))
        elif e.kind == "tool_call":
            if e.content in refused_calls:
                found.append(("repeated_refusal", e))
            last_call = e.content
        elif e.kind == "tool_result":
            t = _result_trigger(e.content or "")
            if t:
                found.append((t, e))
            if last_call is not None and _REFUSED.search(e.content or ""):
                refused_calls.add(last_call)
            last_call = None
    return found


def build(home: str, since: str = "") -> dict:
    from harness.local_session import SessionLedger
    base = Path(home) / "sessions"
    counts = {k: 0 for k in TRIGGERS}
    entries, unverifiable, scanned = [], [], 0
    for folder in sorted(base.iterdir()) if base.is_dir() else []:
        m = _ID.match(folder.name)
        if not m or (since and m.group(1) < since.replace("-", "")):
            continue
        try:
            ledger = SessionLedger.load(str(folder / "ledger.jsonl"))
        except (OSError, ValueError, TypeError):
            unverifiable.append(folder.name)
            continue
        if not ledger.verify():
            unverifiable.append(folder.name)
            continue
        scanned += 1
        for trigger, e in scan_ledger(ledger.entries):
            counts[trigger] += 1
            entries.append({"trigger": trigger, "session": folder.name, "seq": e.seq,
                            "entry_hash": e.entry_hash, "kind": e.kind,
                            "excerpt": (e.content or "")[:160]})
    return {"schema": SCHEMA, "since": since or None, "sessions_scanned": scanned,
            "unverifiable_sessions": unverifiable, "counts": counts, "entries": entries}


def render(report: dict) -> str:
    period = f"since {report['since']}" if report["since"] else "in all saved sessions"
    lines = [f"Scope report {period}: {report['sessions_scanned']} session(s) checked."]
    if report["unverifiable_sessions"]:
        lines.append("Not counted, ledger does not verify: "
                     + ", ".join(report["unverifiable_sessions"]))
    if not report["entries"]:
        lines.append("No call reached past what was allowed: none of the triggers fired.")
        return "\n".join(lines)
    for key, label in TRIGGERS.items():
        if report["counts"][key]:
            lines.append(f"\n{label}: {report['counts'][key]}")
            for e in (x for x in report["entries"] if x["trigger"] == key):
                lines.append(f"  {e['session']} #{e['seq']} {e['entry_hash'][:12]}  "
                             f"{e['excerpt'].splitlines()[0][:100] if e['excerpt'] else ''}")
    return "\n".join(lines)


def main(argv: "list | None" = None) -> int:
    ap = argparse.ArgumentParser(prog="flywheel report",
                                 description="Reports built from saved records.")
    sub = ap.add_subparsers(dest="report", required=True)
    sc = sub.add_parser("scope", help="calls that reached past what was allowed")
    sc.add_argument("--since", default="", help="YYYY-MM-DD: sessions started on or after")
    sc.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.since and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.since):
        ap.error("--since takes YYYY-MM-DD")
    from harness.lane_workdir import flywheel_home
    report = build(str(flywheel_home(os.environ)), args.since)
    print(json.dumps(report, indent=1) if args.json else render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
