"""Codex importer: discovery and the plan (7.6, F-14, N-18).

The client root is `CODEX_HOME` as this process sees it, else the profile's
`.codex`. Rollouts under `sessions/YYYY/MM/DD/` and `archived_sessions/` are
imported, `.jsonl.zst` ones only with a zstd module (otherwise named
UNSUPPORTED_COMPRESSION with their size). A thread with an entry under
`thread-writer-locks/` is a live writer and waits. SQLite stores
(`thread_history_1`, `state_5`, `logs_2` and the rest) are reported by name
and size and never read, and the plan says sessions migrated into them may be
missing. History, the session index, dictation and transcription history,
attachments and generated images are named and not imported. Directories
that are links are refused and never entered.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import time

from . import trace_import_core as core
from . import trace_zstd

CLIENT = "codex"
_ROLLOUT = re.compile(r"rollout-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-"
                      r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
                      r"(?:_\d+)?\.jsonl(\.zst)?\Z")
_NAMED = ("history.jsonl", "session_index.jsonl", "transcription-history.jsonl",
          "dictation-history", "attachments", "generated_images")


def client_root(environ=None) -> Path:
    from .capture_hooks.home import profile_dir
    env = os.environ if environ is None else environ
    return Path(env.get("CODEX_HOME") or (profile_dir() or Path.home()) / ".codex")


def _link(entry: os.DirEntry) -> bool:
    attrs = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
    return entry.is_symlink() or bool(attrs & 0x400)


def _walk(directory: Path, root: Path, refused: list, depth: int = 0):
    for entry in sorted(os.scandir(directory), key=lambda e: e.name) if directory.is_dir() else []:
        if _link(entry):
            refused.append({"rel": Path(entry.path).relative_to(root).as_posix(),
                            "reason": "REPARSE_REFUSED"})
        elif entry.is_dir() and depth < 6:
            yield from _walk(Path(entry.path), root, refused, depth + 1)
        elif entry.is_file():
            yield Path(entry.path)


def _source(path: Path, root: Path, archived: bool, live: set) -> dict | None:
    match = _ROLLOUT.fullmatch(path.name)
    if match is None:
        return None
    compressed, thread = bool(match.group(2)), match.group(1)
    info = path.stat()
    kind = "compressed_rollout" if compressed else (
        "archived_rollout" if archived else "rollout")
    source = {"rel": path.relative_to(root).as_posix(), "kind": kind, "session_id": thread,
              "size": info.st_size, "mtime": info.st_mtime, "path": path}
    if thread in live:
        source["forced_state"] = "LIVE_WRITER"
    elif compressed and not trace_zstd.available():
        source["forced_state"] = "UNSUPPORTED_COMPRESSION"
    return source


def _not_imported(root: Path) -> list[dict]:
    rows = [{"name": name, "reason": "NOT_IMPORTED_BY_DEFAULT", "flag": None}
            for name in _NAMED if (root / name).exists()]
    for path in sorted(root.glob("*.sqlite")):
        rows.append({"name": path.name, "reason": "SQLITE_NOT_READ",
                     "bytes": path.stat().st_size,
                     "note": "sessions migrated into this database may be missing"})
    return rows


def discover(root: Path) -> tuple[list, list]:
    locks = root / "thread-writer-locks"
    live = {p.name for p in locks.iterdir()} if locks.is_dir() else set()
    sources, refused = [], []
    for folder, archived in (("sessions", False), ("archived_sessions", True)):
        for path in _walk(root / folder, root, refused):
            found = _source(path, root, archived, live)
            if found:
                sources.append(found)
    return sources, refused


def plan_codex(home, *, root=None, environ=None, now=None, free_space=None,
               live_window_s=core.LIVE_WINDOW_S, owner_ref=None) -> dict:
    from .trace_custody_ledger import read_owner_ref
    root = Path(root) if root is not None else client_root(environ)
    owner = owner_ref or read_owner_ref(home)
    if owner is None:
        from .operation_grants import load_or_create_owner_ref
        owner = load_or_create_owner_ref(Path(home))
    sources, refused = discover(root)
    return core.build_plan(home, owner, CLIENT, sources, refused=refused,
                           not_imported=_not_imported(root), now=now or time.time(),
                           free_space=free_space, live_window_s=live_window_s)
