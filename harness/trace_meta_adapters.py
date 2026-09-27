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
    """Remove the tree at `root` by handle (private_artifact_remove): a
    junction or symbolic link inside is removed as a link and its target
    stays. `rglob` would descend into a junction and delete the target's
    files. Returns the files and links removed."""
    import os
    from .private_artifact_remove import remove
    root = Path(root)
    if not os.path.lexists(root):
        return 0
    counts = remove(root.parent, root.name)
    return counts["files"] + counts["links"]


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


def retention_export(home) -> list[dict]:
    return json_records(Path(home) / "state" / "trace-retention")


def retention_delete(home) -> dict:
    return {"removed": remove_tree(Path(home) / "state" / "trace-retention")}


def export_grants_export(home) -> list[dict]:
    return json_records(Path(home) / "state" / "trace-export")


def export_grants_delete(home) -> dict:
    return {"removed": remove_tree(Path(home) / "state" / "trace-export")}
