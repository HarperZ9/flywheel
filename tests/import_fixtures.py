"""A synthetic Claude Code directory for the import tests.

One project with a transcript (user, assistant with a tool call, a tool
result, and a record type no parser knows), a subagent transcript, a binary
spilled tool result, an orphaned variant, an undocumented `workflows/`
folder, a junction or symlink to a folder outside the root, and the
top-level stores the importer names but does not import. No real history.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SESSION = "3b1f9a52-7c4d-4e8b-9a61-5d2c8e0f7a14"
PROJECT = "C--work-demo"
OWNER = "owner_" + "a" * 32


def _lines(*records) -> bytes:
    return b"".join(json.dumps(r).encode() + b"\n" for r in records)


def transcript(extra: bytes = b"") -> bytes:
    return _lines(
        {"type": "user", "sessionId": SESSION, "cwd": "C:/work/demo",
         "message": {"role": "user", "content": "please list the files"}},
        {"type": "assistant", "sessionId": SESSION,
         "message": {"role": "assistant", "content": [
             {"type": "text", "text": "Listing now."},
             {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}}]}},
        {"type": "user", "sessionId": SESSION, "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "a.txt\nb.txt"}]}},
        {"type": "mystery-kind", "payload": {"x": 1}},
    ) + extra


def link_dir(link: Path, target: Path) -> bool:
    if sys.platform == "win32":
        done = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                              capture_output=True)
        return done.returncode == 0
    os.symlink(target, link, target_is_directory=True)
    return True


def claude_tree(base: Path) -> tuple[Path, Path, bool]:
    """(client root, the folder the link points at, whether the link exists)."""
    root = base / "claude"
    project = root / "projects" / PROJECT
    (project / SESSION / "subagents").mkdir(parents=True)
    (project / SESSION / "tool-results").mkdir()
    (project / SESSION / "workflows").mkdir()
    (project / f"{SESSION}.jsonl").write_bytes(transcript())
    (project / SESSION / "subagents" / "agent-1.jsonl").write_bytes(
        _lines({"type": "assistant", "message": {"content": "sub"}}))
    (project / SESSION / "tool-results" / "out-1.bin").write_bytes(bytes(range(256)) * 4)
    (project / f"{SESSION}.orphaned.jsonl").write_bytes(_lines({"type": "summary"}))
    (project / SESSION / "workflows" / "wf.json").write_bytes(b'{"steps": 2}')
    (root / "history.jsonl").write_bytes(_lines({"display": "an old prompt"}))
    (root / "file-history").mkdir()
    (root / "file-history" / "x.txt").write_bytes(b"old file")
    (root / "settings.json").write_text(json.dumps({"cleanupPeriodDays": 30}))
    outside = base / "outside"
    outside.mkdir()
    (outside / "id_ed25519").write_bytes(b"NOT-A-REAL-KEY-" + b"k" * 32)
    linked = link_dir(project / "linked", outside)
    age_tree(root, seconds=300)
    return root, outside, linked


def age_tree(root: Path, seconds: float) -> None:
    """Set every file's modification time `seconds` back, so the importer's
    live-writer rule (a file written in the last minute) does not apply."""
    import time
    stamp = time.time() - seconds
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if not _is_link(Path(dirpath) / d)]
        for name in filenames:
            path = Path(dirpath) / name
            if not _is_link(path):
                os.utime(path, (stamp, stamp))


def _is_link(path: Path) -> bool:
    info = path.lstat()
    return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def snapshot(root: Path) -> dict:
    """Bytes, modification time and mode of every entry, following no link."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in dirnames + filenames:
            path = Path(dirpath) / name
            info = path.lstat()
            data = path.read_bytes() if path.is_file() and not path.is_symlink() else None
            out[str(path.relative_to(root))] = (data, info.st_mtime_ns, info.st_mode)
    return out


def old(path: Path, days: float) -> None:
    import time
    stamp = time.time() - days * 86400
    os.utime(path, (stamp, stamp))
