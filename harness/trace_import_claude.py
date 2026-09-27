"""Claude Code importer: discovery and the plan (7.6, F-14, N-19).

The client root is `CLAUDE_CONFIG_DIR` as this process sees it, else the
profile's `.claude`; it is never taken from a request. Under `projects/`
every file is classified: `<session>.jsonl` transcripts, `subagents/`
transcripts, spilled `tool-results/` (binary allowed), other files next to a
transcript as variants, and anything else in a session folder as
undocumented (kept as bytes). A directory entry that is a reparse point
(a junction or symbolic link) is listed as REPARSE_REFUSED and never entered.
`history.jsonl`, `file-history/`, `paste-cache/`, `plans/`, `tasks/` and
`shell-snapshots/` are named in every plan and not imported. The entry
format is internal to Claude Code and changes between versions, so bytes are
kept exactly and views are derived separately.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import time

from . import trace_import_core as core

CLIENT = "claude-code"
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")
_NAMED = ("history.jsonl", "file-history", "paste-cache", "plans", "tasks", "shell-snapshots")
_REPARSE = 0x400


def client_root(environ=None) -> Path:
    from .capture_hooks.home import profile_dir
    env = os.environ if environ is None else environ
    return Path(env.get("CLAUDE_CONFIG_DIR") or (profile_dir() or Path.home()) / ".claude")


def _is_link(entry: os.DirEntry) -> bool:
    try:
        attrs = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
        return entry.is_symlink() or bool(attrs & _REPARSE)
    except OSError:
        return True


class _Walk:
    def __init__(self, root: Path) -> None:
        self.root, self.sources, self.refused, self.over = root, [], [], []

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def add(self, path: Path, kind: str, session: str | None) -> None:
        info = path.stat()
        self.sources.append({"rel": self.rel(path), "kind": kind, "session_id": session,
                             "size": info.st_size, "mtime": info.st_mtime, "path": path})

    def entries(self, directory: Path) -> list:
        try:
            listed = sorted(os.scandir(directory), key=lambda e: e.name)
        except OSError:
            return []
        keep = []
        for entry in listed:
            if _is_link(entry):
                self.refused.append({"rel": self.rel(Path(entry.path)), "reason": "REPARSE_REFUSED"})
            else:
                keep.append(entry)
        return keep

    def files(self, directory: Path, kind: str, session: str, depth: int = 0) -> None:
        found = self.entries(directory)
        if len([e for e in found if e.is_file()]) > core.FILES_PER_DIRECTORY:
            extra = len([e for e in found if e.is_file()]) - core.FILES_PER_DIRECTORY
            self.over.append({"name": self.rel(directory), "reason": "INPUT_BOUND:files",
                              "count": extra})
        taken = 0
        for entry in found:
            if entry.is_dir() and depth < 8:
                self.files(Path(entry.path), kind, session, depth + 1)
            elif entry.is_file() and taken < core.FILES_PER_DIRECTORY:
                self.add(Path(entry.path), kind, session)
                taken += 1

    def session_dir(self, directory: Path) -> None:
        session = directory.name if _UUID.fullmatch(directory.name) else None
        for entry in self.entries(directory):
            path = Path(entry.path)
            kinds = {"subagents": "subagent", "tool-results": "tool_result"}
            if entry.is_dir():
                self.files(path, kinds.get(entry.name, "undocumented"), session)
            else:
                self.add(path, "undocumented", session)

    def project(self, directory: Path) -> None:
        for entry in self.entries(directory):
            path = Path(entry.path)
            if entry.is_dir():
                self.session_dir(path)
                continue
            stem = entry.name.split(".")[0]
            session = stem if _UUID.fullmatch(stem) else None
            exact = entry.name.endswith(".jsonl") and _UUID.fullmatch(entry.name[:-6])
            self.add(path, "transcript" if exact else "variant", session)


def discover(root: Path) -> _Walk:
    walk = _Walk(root)
    for project in walk.entries(root / "projects") if (root / "projects").is_dir() else []:
        if project.is_dir():
            walk.project(Path(project.path))
    return walk


def _named(root: Path) -> list[dict]:
    return [{"name": name, "reason": "NOT_IMPORTED"}
            for name in _NAMED if (root / name).exists()]


def sweep_risk(root: Path, items: list[dict], now: float) -> dict:
    days, source = 30, "default"
    try:
        value = json.loads((root / "settings.json").read_bytes()).get("cleanupPeriodDays")
        if type(value) is int and value >= 1:
            days, source = value, "user settings"
    except (OSError, ValueError, AttributeError):
        pass
    cutoff = now - max(days - 7, 0) * 86400
    risky = [i for i in items if i["kind"] == "transcript" and i["mtime"] < cutoff
             and i["state"] not in ("already", "PREVIOUSLY_DELETED")]
    return {"cleanup_period_days": days, "source": source, "at_risk": len(risky)}


def plan_claude(home, *, root=None, environ=None, now=None, free_space=None,
                live_window_s=core.LIVE_WINDOW_S, owner_ref=None) -> dict:
    from .trace_custody_ledger import read_owner_ref
    root = Path(root) if root is not None else client_root(environ)
    now = now or time.time()
    owner = owner_ref or read_owner_ref(home)
    if owner is None:
        from .operation_grants import load_or_create_owner_ref
        owner = load_or_create_owner_ref(Path(home))
    walk = discover(root)
    plan = core.build_plan(home, owner, CLIENT, walk.sources, refused=walk.refused,
                           not_imported=_named(root) + walk.over, now=now,
                           free_space=free_space, live_window_s=live_window_s, root=root)
    plan["sweep"] = sweep_risk(root, plan["items"], now)
    return plan
