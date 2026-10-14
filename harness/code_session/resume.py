"""resume.py -- `--continue`, `--resume ID` and `--sessions` for flywheel code."""
from __future__ import annotations

import time

from . import store


def pick_id(args, home: str) -> "str | None":
    """The session id to resume, or None for a fresh session."""
    if args.resume:
        return args.resume
    if args.cont:
        rows = store.list_sessions(home, root=args.root)
        if not rows:
            raise store.ResumeRefused("no saved session for this folder to continue")
        return rows[0]["id"]
    return None


def restore(session, home: str, session_id: str) -> dict:
    """Load a saved session into a fresh one; raises ResumeRefused."""
    meta, ledger = store.load(home, session_id)
    session.ledger = ledger
    session.agent.history = list(meta.get("history", []))
    session.session_id = session_id
    session.turns = int(meta.get("turns", 0))
    ledger.append("resume", session_id, {"turns": session.turns})
    return meta


def render_list(home: str, root: "str | None") -> str:
    rows = store.list_sessions(home, root=root)
    if not rows:
        return "no saved sessions"
    lines = []
    for r in rows:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(r["updated"] or 0))
        lines.append(f"{r['id']}  {when}  {r['turns']} turn(s)  {r['first']}")
    return "\n".join(lines)
