"""store.py -- save a session after each turn, and resume it later.

A saved session is a folder under FLYWHEEL_HOME/sessions/<id>/ with the
hash-chained ledger (ledger.jsonl) and meta.json (folder, mode, backend, the
model conversation, timestamps). Each save first appends a `save` entry to the
ledger carrying the sha256 of the conversation it saved, so the conversation is
bound into the chain. Resume refuses a session whose chain does not verify,
whose head differs from the one meta.json recorded, or whose conversation no
longer matches the hash in its last `save` entry.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import time
from pathlib import Path

from harness.local_session import SessionLedger

SCHEMA = "flywheel.code-session/v1"
_ID = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{6}$")


class ResumeRefused(ValueError):
    """The saved session is missing, malformed or does not verify."""


def sessions_dir(home: str) -> Path:
    return Path(home) / "sessions"


def new_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)


def history_digest(history: list) -> str:
    raw = json.dumps(history, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def save(session, home: str) -> Path:
    """Write the session's folder; returns it."""
    if not session.session_id:
        session.session_id = new_id()
    folder = sessions_dir(home) / session.session_id
    folder.mkdir(parents=True, exist_ok=True)
    digest = history_digest(session.agent.history)
    session.ledger.append("save", digest, {"history_sha256": digest})
    meta = {"schema": SCHEMA, "id": session.session_id, "root": session.root,
            "mode": session.executor.mode, "turns": session.turns,
            "updated": time.time(), "ledger_head": session.ledger.checkpoint(),
            "history": session.agent.history}
    tmp = folder / "meta.json.tmp"
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    session.ledger.save(str(folder / "ledger.jsonl"))
    os.replace(tmp, folder / "meta.json")
    return folder


def list_sessions(home: str, root: "str | None" = None) -> list[dict]:
    """Saved sessions, newest first; only those for `root` when given."""
    base = sessions_dir(home)
    rows = []
    if not base.is_dir():
        return rows
    want = os.path.normcase(os.path.abspath(root)) if root else None
    for folder in base.iterdir():
        try:
            meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if want and os.path.normcase(os.path.abspath(meta.get("root", ""))) != want:
            continue
        rows.append({"id": meta.get("id"), "root": meta.get("root"),
                     "turns": meta.get("turns"), "updated": meta.get("updated", 0),
                     "first": _first_request(meta.get("history", []))})
    return sorted(rows, key=lambda r: r["updated"], reverse=True)


def _first_request(history: list) -> str:
    for m in history:
        if m.get("role") == "user":
            return str(m.get("content", "")).splitlines()[0][:80] if m.get("content") else ""
    return ""


def load(home: str, session_id: str) -> "tuple[dict, SessionLedger]":
    """meta and ledger for a saved session, or ResumeRefused with the reason."""
    if not _ID.match(session_id or ""):
        raise ResumeRefused(f"not a session id: {session_id!r}")
    folder = sessions_dir(home) / session_id
    try:
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        ledger = SessionLedger.load(str(folder / "ledger.jsonl"))
    except (OSError, ValueError, TypeError) as e:
        raise ResumeRefused(f"session {session_id} could not be read: {e}") from e
    if not ledger.verify():
        raise ResumeRefused(f"session {session_id}: the ledger chain does not verify")
    if meta.get("ledger_head") != ledger.checkpoint():
        raise ResumeRefused(f"session {session_id}: ledger head differs from meta.json")
    saves = [e for e in ledger.entries if e.kind == "save"]
    if not saves or saves[-1].content != history_digest(meta.get("history", [])):
        raise ResumeRefused(f"session {session_id}: the conversation does not match "
                            "the hash its ledger recorded")
    return meta, ledger
