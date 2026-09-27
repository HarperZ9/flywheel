"""Import one ended session by id, for the SessionEnd archive (7.6, SP-05).

The route takes a client and a session id, never a path. The id must match
the client's pattern (a UUID); anything with `..`, a separator, a colon or
another character is refused. The gateway resolves the file under its own
client root, walking project folders without entering links, then refuses
UNC paths, `\\\\?\\` and `\\\\.\\` prefixes, alternate data streams and reserved
device names before any open. The read itself opens by handle, refuses a
reparse point and proves the file unchanged; the final path of the open
handle must lie inside the client root (OUTSIDE_ROOT otherwise), checked on
the handle itself after the open, not on the path before it. One import per
session id per minute. An ended session skips the live-writer rule. Only
Claude Code sessions are archived; a Codex SessionEnd is not mounted.
"""
from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath
import re
import threading
import time

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")
_RESERVED = re.compile(r"(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?\Z", re.I)
_LAST: dict[str, float] = {}
_LOCK = threading.Lock()
RATE_S = 60


class SessionRefused(Exception):
    def __init__(self, code: str, status: int = 422) -> None:
        super().__init__(code)
        self.code, self.status = code, status


def validate(client: str, session_id) -> None:
    if client not in ("claude-code",):
        raise SessionRefused("UNSUPPORTED_CLIENT")
    if type(session_id) is not str or not _UUID.fullmatch(session_id):
        raise SessionRefused("INVALID_SESSION_ID")


def check_target(target) -> None:
    """Refuse a path shape that could reach another host or device. Nothing
    here opens the path."""
    text = str(target)
    if text.startswith(("\\\\", "//")):
        raise SessionRefused("UNSAFE_TARGET")
    drive = PureWindowsPath(text).drive
    rest = text[len(drive):]
    if ":" in rest:
        raise SessionRefused("UNSAFE_TARGET")
    if any(_RESERVED.fullmatch(part) for part in PureWindowsPath(text).parts[1:]):
        raise SessionRefused("UNSAFE_TARGET")


def _is_link(entry: os.DirEntry) -> bool:
    attrs = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
    return entry.is_symlink() or bool(attrs & 0x400)


def resolve(root: Path, session_id: str) -> Path:
    projects = Path(root) / "projects"
    found = []
    for entry in os.scandir(projects) if projects.is_dir() else []:
        if _is_link(entry) or not entry.is_dir(follow_symlinks=False):
            continue
        candidate = Path(entry.path) / f"{session_id}.jsonl"
        if candidate.is_file() and not candidate.is_symlink():
            found.append(candidate)
    if len(found) != 1:
        raise SessionRefused("NOT_FOUND", 404)
    check_target(found[0])
    return found[0]


def _final_inside(path: Path, root: Path) -> None:
    real, base = os.path.realpath(path), os.path.realpath(root)
    if os.path.normcase(os.path.commonpath([real, base])) != os.path.normcase(base):
        raise SessionRefused("OUTSIDE_ROOT")


def _rate(session_id: str, now: float) -> None:
    with _LOCK:
        if now - _LAST.get(session_id, -1e18) < RATE_S:
            raise SessionRefused("RATE_LIMITED", 429)
        _LAST[session_id] = now


def prepare(client: str, session_id, *, root=None, now=None) -> tuple[Path, Path]:
    """Validate, rate-limit and resolve; nothing is read yet."""
    from .trace_import_claude import client_root
    validate(client, session_id)
    _rate(session_id, now or time.time())
    root = Path(root) if root is not None else client_root()
    path = resolve(root, session_id)
    _final_inside(path, root)
    return root, path


def run(home, owner_ref: str, client: str, session_id, root: Path, path: Path) -> dict:
    from . import trace_import_core as core
    info = path.stat()
    source = {"rel": path.relative_to(root).as_posix(), "kind": "transcript",
              "session_id": session_id, "size": info.st_size, "mtime": info.st_mtime,
              "path": path}
    plan = core.build_plan(home, owner_ref, client, [source], live_window_s=0, root=root)
    result = core.run_import(home, plan)
    return {"imported": result["imported"], "state": result["state"],
            "skipped": result["skipped"], "refused": result["refused"]}


def import_session(home, owner_ref: str, client: str, session_id, *, root=None,
                   now=None) -> dict:
    root, path = prepare(client, session_id, root=root, now=now)
    return run(home, owner_ref, client, session_id, root, path)


def queue(home, owner_ref: str, client: str, session_id, root: Path, path: Path):
    """Import in the background, so the hook's one-second budget holds; a
    failure leaves a spool record naming client and session id."""
    def work():
        from .capture_hooks import spool
        try:
            result = run(home, owner_ref, client, session_id, root, path)
            codes = list(result["refused"]) + ([result["state"]] if result["state"] != "OK"
                                               else [])
        except Exception as exc:  # recorded for `flywheel traces import --pending`
            codes = [f"IMPORT_FAILED_{type(exc).__name__.upper()}"[:40]]
        for code in codes:
            spool.write_failure(Path(home), client, "session-end", session_id, None, code)
    thread = threading.Thread(target=work, name="flywheel-session-import", daemon=True)
    thread.start()
    return thread
