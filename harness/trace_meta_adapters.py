"""Export and delete adapters for metadata-only custody stores.

Presence challenges (store PR) hold a kind, a plan digest, times, a state and
the method that confirmed them: no content and no path. Export returns them as
they are; delete removes the tree, for a whole-custody deletion.
"""
from __future__ import annotations

import json
from pathlib import Path


def json_records(directory: Path, pattern: str = "*.json") -> list[dict]:
    out = []
    for path in sorted(directory.rglob(pattern)) if directory.is_dir() else []:
        try:
            out.append(json.loads(path.read_bytes()))
        except (OSError, ValueError):
            out.append({"schema": "unreadable", "name": path.name})
    return out


def remove_tree(root: Path) -> int:
    """Remove files bottom-up; links are removed as links, never followed."""
    removed = 0
    for path in sorted(root.rglob("*"), reverse=True) if root.exists() else []:
        if path.is_symlink() or path.is_file():
            path.unlink()
            removed += 1
        elif path.is_dir():
            path.rmdir()
    return removed


def presence_export(home) -> list[dict]:
    return json_records(Path(home) / "state" / "presence")


def presence_delete(home) -> dict:
    return {"removed": remove_tree(Path(home) / "state" / "presence")}


def tombstones_export(home) -> list[dict]:
    """The deletion ledger's entries; journals and scan sets are never exported."""
    root = Path(home) / "state" / "trace-deletions" / "v1" / "owners"
    out = []
    for owner in sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []:
        from .trace_tombstones import TombstoneLedger
        out.extend(TombstoneLedger(Path(home) / "state", owner.name).entries())
    return out


def deletions_delete(home) -> dict:
    return {"removed": remove_tree(Path(home) / "state" / "trace-deletions")}


def capture_settings_export(home) -> list[dict]:
    return json_records(Path(home) / "state" / "capture-settings")


def capture_settings_delete(home) -> dict:
    return {"removed": remove_tree(Path(home) / "state" / "capture-settings")}
