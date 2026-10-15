"""memory.py -- notes the agent keeps for a project across sessions.

The `remember` tool appends one dated note to the project's memory file in the
Flywheel home (memory/<folder name>-<hash>.md, outside the project tree), and
every new session for that folder starts with the newest notes in its system
prompt (at most 200 lines or 25 KiB). A note is a write the next session will
read, so it is a permission like a file write: it asks in ask mode, runs in
edit and auto, and is refused in plan. `/memory` shows the notes and
`/forget N` removes note N. Each note and each removal goes on the ledger.
"""
from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path

MAX_LINES, MAX_BYTES, MAX_NOTE = 200, 25 * 1024, 1000
TOOL_TEXT = ('Also available: TOOL remember {"note": "<one fact worth keeping for later '
             'sessions>"} saves a note for this project; keep notes short and factual.')


def memory_file(home: str, root: str) -> Path:
    resolved = str(Path(root).resolve()).lower()
    tag = hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:10]
    name = re.sub(r"[^A-Za-z0-9_-]", "_", Path(root).resolve().name)[:40] or "root"
    return Path(home) / "memory" / f"{name}-{tag}.md"


def notes(path: Path) -> list:
    if not path.is_file():
        return []
    return [line[2:] for line in path.read_text(encoding="utf-8").splitlines()
            if line.startswith("- ")]


def remember(path: Path, note: str) -> "tuple[bool, str]":
    note = " ".join(note.split())
    if not note:
        return False, "[error] remember needs a 'note'"
    if len(note) > MAX_NOTE:
        return False, f"[error] keep a note under {MAX_NOTE} characters"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"- {time.strftime('%Y-%m-%d')} {note}\n")
    return True, f"remembered (note {len(notes(path))})"


def forget(path: Path, index: int) -> bool:
    current = notes(path)
    if not 1 <= index <= len(current):
        return False
    del current[index - 1]
    path.write_text("".join(f"- {n}\n" for n in current), encoding="utf-8")
    return True


def system_text(path: Path) -> str:
    current = notes(path)[-MAX_LINES:]
    if not current:
        return ""
    body = "\n".join(f"- {n}" for n in current)
    body = body.encode("utf-8")[-MAX_BYTES:].decode("utf-8", errors="ignore")
    return "Notes kept from earlier sessions in this project (newest last):\n" + body
