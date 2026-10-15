"""attach.py -- start a session's hooks and MCP servers, asking first for a project's."""
from __future__ import annotations

import os
import sys

from .store import ResumeRefused


def ask_project_hooks(entries) -> bool:
    shown = "; ".join(f"{e.event}: {e.command[:60]}" for e in entries[:5])
    try:
        raw = input(f"  run this project's hooks ({shown})? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return raw in ("y", "yes")


def attach_hooks(session, root: str, home: str, *, interactive: bool, trust: bool) -> None:
    from .hooks import Hooks, load
    entries, errors, _ = load(root, home, trust_project=trust,
                              ask=ask_project_hooks if interactive else None)
    if errors:
        raise ResumeRefused("hooks could not be read, so none are trusted: " + "; ".join(errors))
    if entries:
        session.set_hooks(Hooks(entries=entries, cwd=root))


def ask_project_server(spec) -> bool:
    shown = spec.url or " ".join(spec.command)
    try:
        raw = input(f"  start project MCP server {spec.name!r} ({shown[:120]}) "
                    f"from {os.path.basename(spec.source)}? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return raw in ("y", "yes")


def attach_mcp(session, root: str, home: str, *, interactive: bool, trust: bool) -> None:
    from .mcp_config import attach, load_specs
    specs, errors = load_specs(root, home)
    for err in errors:
        print(f"[mcp] {err}", file=sys.stderr)
    if not specs:
        return
    rows = attach(session, specs, ask=ask_project_server if interactive else None,
                  trust_project=trust, home=home)
    for row in rows:
        started = row["status"] == "started"
        detail = f"{len(row.get('tools', []))} tool(s)" if started else row.get("reason", "")
        print(f"[mcp] {row['name']}: {row['status']} {detail}", file=sys.stderr)
