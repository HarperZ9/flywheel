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

A hold that cannot be saved is kept in this process's memory instead, and its
reason says so: it lasts until the session ends. An open record names the
process that wrote it by id and start time, so a later session can tell a
dead owner from a live one, and from a new process that reused the id.
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
STILL_ACTIVE = 259
#: Holds whose file could not be written, by that file's path.
_UNSAVED: dict = {}


def _windows_started(pid: int) -> "int | None":
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.OpenProcess(0x1000, False, pid)      # query limited information
    if not handle:
        return None
    try:
        code, times = wintypes.DWORD(), [wintypes.FILETIME() for _ in range(4)]
        kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != STILL_ACTIVE:
            return None
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            return None
        return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
    finally:
        kernel.CloseHandle(handle)


def process_started(pid) -> "int | None":
    """When the live process `pid` started, or None when no such process runs.

    On Windows this is the creation time. Elsewhere it is 0 for any live
    process: the open record is only written on Windows, and a start time is
    what tells a reused id from the original owner.
    """
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return None
    if os.name == "nt":
        return _windows_started(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return None
    except OSError:          # it exists and belongs to another account
        return 0
    return 0


def owner_alive(record: dict) -> bool:
    """True when the process that wrote an open record is still that process."""
    started = process_started(record.get("pid"))
    return started is not None and started == record.get("started")


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
    except (FileNotFoundError, NotADirectoryError):
        return None
    except (OSError, ValueError):
        log.warning("could not read %s", path, exc_info=True)
        return {"reason": "its record is unreadable"}
    return record if isinstance(record, dict) else {"reason": "its record is unreadable"}


def hold(root, reason: str, state=None) -> Path:
    """Keep `root` read-only to commands until a person clears the hold."""
    path = _file(HOLDS, root, state)
    if not _write(path, {"root": str(root), "reason": reason, "time": int(time.time())}):
        _UNSAVED[str(path)] = reason
    return path


def hold_reason(root, state=None) -> str:
    """Why `root` is held, with the file to delete, or an empty string."""
    path = _file(HOLDS, root, state)
    record = _read(path)
    if record is None and str(path) in _UNSAVED:
        return (f"{_UNSAVED[str(path)]}. The hold could not be saved to {path}, so it is "
                "kept in memory and lasts until this session ends")
    if record is None:
        return ""
    return (f"{record.get('reason', 'a guarded file could not be put back')}. Check the "
            f"project, then delete {path} to let commands write again")


def clear_hold(root, state=None) -> bool:
    path = _file(HOLDS, root, state)
    unsaved = _UNSAVED.pop(str(path), None) is not None
    try:
        path.unlink()
    except (FileNotFoundError, NotADirectoryError):
        return unsaved
    return True


def mark_open(root, paths, state=None) -> None:
    _write(_file(OPEN, root, state), {"root": str(root), "pid": os.getpid(),
                                      "started": process_started(os.getpid()),
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
