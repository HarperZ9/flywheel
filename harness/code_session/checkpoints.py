"""checkpoints.py -- per-turn file snapshots, so `/undo` puts a turn back.

Before a write tool touches a file, the file's prior bytes are kept for the
current turn, or its absence is, so a file the turn created is deleted on undo.
Only the first write to a path in a turn is snapshotted: that is the state the
turn started from. `/undo` restores the newest turn that changed anything and
reports each path with the sha256 it was restored to.

Changes a shell command makes are not tracked. In a session the project folder
is read-only to commands, so the write tools are the only way files change, and
those are exactly the calls this module sees.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field

from harness.local_tools import _safe_path, _strip_ab


def target_paths(root: str, name: str, args: dict) -> list[str]:
    """The absolute files a write tool call would change (inside root only)."""
    rels: list[str] = []
    if name in ("write_file", "edit_file"):
        rels.append(str(args.get("path", "")))
    elif name == "apply_patch":
        patch = str(args.get("patch") or args.get("diff") or "")
        for line in patch.replace("\r\n", "\n").split("\n"):
            if line.startswith("+++ "):
                rels.append(_strip_ab(line[4:].strip()))
    out = []
    for rel in rels:
        target = _safe_path(root, rel) if rel else None
        if target is not None and target not in out:
            out.append(target)
    return out


def _sha(data: "bytes | None") -> str:
    return "absent" if data is None else hashlib.sha256(data).hexdigest()


@dataclass
class CheckpointStore:
    root: str
    turns: list = field(default_factory=list)      # [{path: bytes | None}], oldest first

    def begin_turn(self) -> None:
        self.turns.append({})

    def snapshot(self, name: str, args: dict) -> None:
        if not self.turns:
            self.begin_turn()
        current = self.turns[-1]
        for path in target_paths(self.root, name, args):
            if path in current:
                continue
            try:
                with open(path, "rb") as f:
                    current[path] = f.read()
            except FileNotFoundError:
                current[path] = None
            except OSError:
                continue          # unreadable: the write will fail the same way

    def undoable(self) -> int:
        return sum(1 for t in self.turns if t)

    def undo(self) -> "list[dict] | None":
        """Restore the newest turn that changed files. None when there is none."""
        while self.turns and not self.turns[-1]:
            self.turns.pop()
        if not self.turns:
            return None
        restored = []
        for path, data in sorted(self.turns.pop().items()):
            if data is None:
                if os.path.exists(path):
                    os.remove(path)
            else:
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                with open(path, "wb") as f:
                    f.write(data)
            restored.append({"path": os.path.relpath(path, self.root), "sha256": _sha(data)})
        return restored
