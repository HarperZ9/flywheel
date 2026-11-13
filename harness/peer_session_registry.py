"""Discover local harness transcripts and build a content-free registry.

Two harnesses write JSONL transcripts on this machine:

* Claude Code: ~/.claude/projects/<cwd-slug>/<session>.jsonl, with subagent
  transcripts under a "subagents" subtree.
* Codex: ~/.codex/sessions/YYYY/MM/DD/rollout-<stamp>-<thread-id>.jsonl.

Discovery lists paths, sizes and mtimes. Observation (one bounded head and
tail read per file) is a separate step so a caller can list thousands of
files and observe only the newest few. Nothing under ~/.codex other than the
sessions tree is touched; auth material is never read.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re

from .peer_session_claude import observe_claude_transcript
from .peer_session_codex import observe_codex_rollout
from .peer_session_io import SourceRejected, _utc, is_link
from .peer_session_types import HARNESS_CLAUDE, HARNESS_CODEX, OBSERVER_VERSION, REGISTRY_SCHEMA

CODEX_ROLLOUT = re.compile(r"rollout-.+\.jsonl\Z")
CODEX_NAME_ID = re.compile(r"rollout-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-"
                           r"(?P<id>[0-9a-fA-F-]{36})\.jsonl\Z")
CLAUDE_SESSION = re.compile(r"[0-9a-f-]{36}\.jsonl\Z")
DEFAULT_LIMIT = 24
MAX_DISCOVERED = 20_000
MAX_UNOBSERVED_LISTED = 64


def default_roots(home: str | os.PathLike[str] | None = None) -> dict[str, Path]:
    base = Path(home) if home is not None else Path.home()
    return {HARNESS_CLAUDE: base / ".claude" / "projects",
            HARNESS_CODEX: base / ".codex" / "sessions"}


def _entry(path: Path, harness: str, *, subagent: bool) -> dict | None:
    try:
        st = path.lstat()
    except OSError:
        return None
    if is_link(path) or not path.is_file():
        return None
    return {"path": str(path), "harness": harness, "size_bytes": st.st_size,
            "mtime_utc": _utc(st.st_mtime), "subagent_path": subagent}


def _walk(root: Path, *, max_depth: int):
    """Yield regular files under root, refusing to follow symlinked directories."""
    stack = [(root, 0)]
    seen = 0
    while stack:
        current, depth = stack.pop()
        try:
            entries = sorted(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if is_link(entry):
                continue
            if entry.is_dir():
                if depth < max_depth:
                    stack.append((entry, depth + 1))
            elif entry.is_file():
                seen += 1
                if seen > MAX_DISCOVERED:
                    return
                yield entry


def discover_claude(root: Path) -> list[dict]:
    out = []
    if is_link(root) or not root.is_dir():
        return out
    for path in _walk(root, max_depth=6):
        if not CLAUDE_SESSION.match(path.name):
            continue
        subagent = "subagents" in path.relative_to(root).parts
        entry = _entry(path, HARNESS_CLAUDE, subagent=subagent)
        if entry:
            entry["project_slug"] = path.relative_to(root).parts[0]
            out.append(entry)
    return out


def discover_codex(root: Path) -> list[dict]:
    out = []
    if is_link(root) or not root.is_dir():
        return out
    for path in _walk(root, max_depth=4):
        if not CODEX_ROLLOUT.match(path.name):
            continue
        entry = _entry(path, HARNESS_CODEX, subagent=False)
        if entry:
            out.append(entry)
    return out


def discover(roots: dict[str, Path] | None = None) -> list[dict]:
    """All candidate transcripts, newest first. Discovery reads no file content."""
    roots = roots if roots is not None else default_roots()
    found = []
    claude_root = roots.get(HARNESS_CLAUDE)
    codex_root = roots.get(HARNESS_CODEX)
    if claude_root is not None:
        found.extend(discover_claude(Path(claude_root)))
    if codex_root is not None:
        found.extend(discover_codex(Path(codex_root)))
    return sorted(found, key=lambda e: (e["mtime_utc"], e["path"]), reverse=True)


OBSERVERS = {HARNESS_CLAUDE: observe_claude_transcript, HARNESS_CODEX: observe_codex_rollout}


def _name_matches(path: str, record: dict) -> bool | None:
    """Does the file name carry the same id the content carries?

    None when the content names no id, so the question cannot be asked. The
    comparison is equality against the whole id the name holds: a suffix test
    would let a file named for one session claim another whose id merely ends
    the same way. A Codex name that is not shaped to carry an id answers False
    rather than None, because the name was read and it did not agree.
    """
    name = Path(path).name
    if record["harness"] == HARNESS_CLAUDE:
        ident = record.get("session_id") or {}
        inner = ident.get("value")
        outer = name[:-len(".jsonl")] if name.endswith(".jsonl") else None
    else:
        inner = record.get("thread_id")
        match = CODEX_NAME_ID.match(name)
        outer = match["id"] if match else None
    if inner is None:
        return None
    return outer is not None and outer == inner


def observe_entry(entry: dict, *, observed_at: str, head_bytes=None, tail_bytes=None) -> dict:
    """Observe one discovered entry. A rejected source becomes a recorded failure."""
    observer = OBSERVERS[entry["harness"]]
    kwargs = {"observed_at": observed_at}
    if head_bytes is not None:
        kwargs["head_bytes"] = head_bytes
    if tail_bytes is not None:
        kwargs["tail_bytes"] = tail_bytes
    try:
        record = observer(entry["path"], **kwargs)
    except (SourceRejected, OSError, ValueError) as exc:
        return {"path": entry["path"], "harness": entry["harness"], "observed": False,
                "error": type(exc).__name__, "subagent_path": entry.get("subagent_path", False)}
    record["observed"] = True
    record["subagent_path"] = entry.get("subagent_path", False)
    record["name_ref_consistent"] = _name_matches(entry["path"], record)
    if "project_slug" in entry:
        record["project_slug"] = entry["project_slug"]
    return record


def build_registry(entries: list[dict], *, observed_at: str, limit: int = DEFAULT_LIMIT,
                   observe=observe_entry, head_bytes=None, tail_bytes=None) -> dict:
    """Observe the newest `limit` entries. The rest are counted in full and listed
    by path only up to MAX_UNOBSERVED_LISTED, so the registry stays bounded."""
    if type(limit) is not int or limit < 0:
        raise ValueError("limit must be a non-negative int")
    ordered = sorted(entries, key=lambda e: (e["mtime_utc"], e["path"]), reverse=True)
    observed = [observe(e, observed_at=observed_at, head_bytes=head_bytes, tail_bytes=tail_bytes)
                for e in ordered[:limit]]
    rest = ordered[limit:]
    unobserved = [{"path": e["path"], "harness": e["harness"], "size_bytes": e["size_bytes"],
                   "mtime_utc": e["mtime_utc"]} for e in rest[:MAX_UNOBSERVED_LISTED]]
    counts = {h: sum(1 for e in ordered if e["harness"] == h) for h in sorted(OBSERVERS)}
    body = {"schema": REGISTRY_SCHEMA, "observer_version": OBSERVER_VERSION,
            "observed_at": observed_at, "discovered": len(ordered), "discovered_by_harness": counts,
            "observed_count": sum(1 for r in observed if r.get("observed")),
            "observe_failures": sum(1 for r in observed if not r.get("observed")),
            "limit": limit, "sessions": observed, "unobserved": unobserved,
            "unobserved_count": len(rest), "unobserved_listed": len(unobserved),
            "scope": ("Covers transcript files present at discovery time. Whether any session "
                      "is running, which harness wrote the files and whether their content is "
                      "complete are unverified.")}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    body["registry_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return body


__all__ = ["DEFAULT_LIMIT", "MAX_UNOBSERVED_LISTED", "build_registry", "default_roots",
           "discover", "discover_claude", "discover_codex", "observe_entry"]
