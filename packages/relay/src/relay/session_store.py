"""session_store.py -- list and open saved relay sessions, so a session follows you.

A relay run saves its witnessed ledger to a JSONL file (SessionLedger.save). This
lists the ledgers in a directory as sessions the same user on another device can
reopen, and hands back one session's transcript. Each is re-verified, so a tampered
saved session reads as unverified here instead of being trusted silently, and
run_agent resumes from a loaded ledger by continuing its hash chain. Pure over a
directory of ledger files; zero dependencies.

The store is RELAY_SESSION_DIR, or a per-user data folder when that is unset,
never the folder the server was started in. A session id is a bare name: it
cannot name a path, and a file whose real path leaves the store (a symlink out)
is neither opened nor listed.
"""
from __future__ import annotations

import os
import re
import sys

from .local_session import SessionLedger

SESSION_DIR_ENV = "RELAY_SESSION_DIR"
_SESSION_ID = re.compile(r"[A-Za-z0-9._-]{1,128}")
# What a file that is not a relay ledger raises on load: bad JSON or bytes
# (ValueError), a record of the wrong shape (TypeError, KeyError, AttributeError).
_UNREADABLE = (OSError, ValueError, TypeError, KeyError, AttributeError)


def user_data_dir(env=None) -> str:
    """The per-user data folder for relay's own state."""
    env = os.environ if env is None else env
    home = os.path.expanduser("~")
    if os.name == "nt":
        base = env.get("LOCALAPPDATA") or os.path.join(env.get("USERPROFILE") or home,
                                                       "AppData", "Local")
    elif sys.platform == "darwin":
        base = os.path.join(env.get("HOME") or home, "Library", "Application Support")
    else:
        base = env.get("XDG_DATA_HOME") or os.path.join(env.get("HOME") or home,
                                                        ".local", "share")
    return os.path.join(base, "relay")


def default_session_dir(env=None) -> str:
    return os.path.join(user_data_dir(env), "sessions")


def session_dir(env=None) -> str:
    """RELAY_SESSION_DIR, or the per-user default."""
    env = os.environ if env is None else env
    return env.get(SESSION_DIR_ENV) or default_session_dir(env)


def valid_session_id(session_id) -> bool:
    return (isinstance(session_id, str) and session_id not in (".", "..")
            and _SESSION_ID.fullmatch(session_id) is not None)


def _inside(directory: str, path: str) -> bool:
    """True when `path`, links followed, is a file directly inside `directory`."""
    base = os.path.normcase(os.path.realpath(directory))
    real = os.path.normcase(os.path.realpath(path))
    return os.path.dirname(real) == base


def _mtime(path: str) -> float:
    """Sort key; a dangling link or a file removed mid-listing sorts last."""
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def _first_goal(ledger) -> str:
    for e in ledger.entries:
        if e.kind == "user":
            return e.content[:200]
    return ""


def session_summary(ledger, session_id: str) -> dict:
    return {
        "id": session_id,
        "goal": _first_goal(ledger),
        "entries": len(ledger.entries),
        "checkpoint": ledger.checkpoint(),
        "verified": ledger.verify(),   # a tampered saved session reads False, not hidden
    }


def list_sessions(directory: str) -> dict:
    """Every saved ledger in `directory` as a reopenable session, newest file first.
    A file that will not parse, or whose real path leaves the store, is skipped
    and counted rather than crashing the listing."""
    if not os.path.isdir(directory):
        return {"sessions": [], "count": 0, "skipped": 0}
    found = [n for n in os.listdir(directory) if n.endswith(".jsonl")]
    names = [n for n in found if valid_session_id(n[:-6])]  # the rest cannot be opened by id
    names.sort(key=lambda n: _mtime(os.path.join(directory, n)), reverse=True)
    rows, skipped = [], len(found) - len(names)
    for name in names:
        path = os.path.join(directory, name)
        try:
            if not (_inside(directory, path) and os.path.isfile(path)):
                raise OSError("outside the store")
            rows.append(session_summary(SessionLedger.load(path, verify=False), name[:-6]))
        except _UNREADABLE:
            skipped += 1
    return {"sessions": rows, "count": len(rows), "skipped": skipped}


def get_session(directory: str, session_id: str) -> dict:
    """One session's transcript plus its verification, or an error if it is missing
    or unreadable. Loads without raising so a tampered file is reported, not trusted.
    The caller checks `session_id` with valid_session_id first."""
    if not valid_session_id(session_id):
        return {"error": "a session id is a bare name of letters, digits, '.', '_' or '-'",
                "code": "INVALID_ARGUMENT"}
    path = os.path.join(directory, f"{session_id}.jsonl")
    if not (os.path.isfile(path) and _inside(directory, path)):
        return {"error": f"unknown session {session_id!r}", "code": "NOT_FOUND"}
    try:
        led = SessionLedger.load(path, verify=False)
        return {**session_summary(led, session_id), "transcript": led.transcript()}
    except _UNREADABLE as e:
        return {"error": f"cannot read session {session_id!r}: {type(e).__name__}",
                "code": "UNREADABLE"}
