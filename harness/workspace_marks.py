"""workspace_marks.py -- two facts about a project that outlive a process.

  hold   a guarded file could not be put back after a command, or Windows could
         not close the project again. Commands get a read-only project until a
         person has looked and deleted the hold file. A file that could not be
         restored is never taken as the next run's starting point.
  open   on Windows the project is labelled low integrity while a writing
         command runs. The record names the labelled folders, so the next
         session can close them when a process died before it could.

Both are one small JSON file per project under the Flywheel home, which no
sandboxed command can write. A record that cannot be read counts as present.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path

log = logging.getLogger(__name__)
HOLDS, OPEN = "workspace-holds", "workspace-open"


def _folder(kind: str, state=None) -> Path:
    if state is None:
        from .lane_workdir import flywheel_home
        state = flywheel_home(os.environ)
    return Path(state) / kind


def _file(kind: str, root, state=None) -> Path:
    name = os.path.normcase(str(Path(root).resolve()))
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:32]
    return _folder(kind, state) / f"{digest}.json"


def _write(path: Path, record: dict) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    except OSError:
        log.warning("could not write %s", path, exc_info=True)
        return False
    return True


def _read(path: Path) -> "dict | None":
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        log.warning("could not read %s", path, exc_info=True)
        return {"reason": "its record is unreadable"}
    return record if isinstance(record, dict) else {"reason": "its record is unreadable"}


def hold(root, reason: str, state=None) -> Path:
    """Keep `root` read-only to commands until a person clears the hold."""
    path = _file(HOLDS, root, state)
    _write(path, {"root": str(root), "reason": reason, "time": int(time.time())})
    return path


def hold_reason(root, state=None) -> str:
    """Why `root` is held, with the file to delete, or an empty string."""
    path = _file(HOLDS, root, state)
    record = _read(path)
    if record is None:
        return ""
    return (f"{record.get('reason', 'a guarded file could not be put back')}. Check the "
            f"project, then delete {path} to let commands write again")


def clear_hold(root, state=None) -> bool:
    try:
        _file(HOLDS, root, state).unlink()
    except FileNotFoundError:
        return False
    return True


def mark_open(root, paths, state=None) -> None:
    _write(_file(OPEN, root, state), {"root": str(root), "pid": os.getpid(),
                                      "paths": [str(path) for path in paths]})


def mark_closed(root, state=None) -> None:
    try:
        _file(OPEN, root, state).unlink()
    except FileNotFoundError:
        return
    except OSError:
        log.warning("could not remove the open record for %s", root, exc_info=True)


def left_open(state=None) -> list:
    """Every open record on disk, as (file, record)."""
    try:
        files = sorted(_folder(OPEN, state).glob("*.json"))
    except OSError:
        return []
    return [(path, _read(path) or {}) for path in files]
