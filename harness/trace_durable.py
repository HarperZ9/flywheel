"""Durable replace for custody records (SP-durable).

A record is written to a temporary file next to it, flushed to disk, renamed
over the record with write-through (MoveFileExW on Windows), and then the
folder is flushed. An unclean shutdown leaves either the old record or the
new one, never a zero-filled file where a record was (this machine has shown
NUL-filled files after unclean shutdowns).
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

from .journey_lock import fsync_directory


def replace_through(source: Path, target: Path) -> None:
    """Rename with write-through (MoveFileExW on Windows, rename elsewhere)."""
    if sys.platform != "win32":
        os.replace(source, target)
        return
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.MoveFileExW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD)
    kernel.MoveFileExW.restype = wintypes.BOOL
    if not kernel.MoveFileExW(str(source), str(target), 0x1 | 0x8):
        raise ctypes.WinError(ctypes.get_last_error())


def write_temp(path: Path, data: bytes, *, times=None) -> Path:
    """The temporary file beside `path`, holding `data`, flushed to disk. With
    `times` (an os.stat result) it keeps that access and modification time."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + ".tmp")
    with open(temporary, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    if times is not None:
        os.utime(temporary, ns=(times.st_atime_ns, times.st_mtime_ns))
    return temporary


def commit(temporary: Path, path: Path) -> None:
    """Put a flushed temporary file in place and flush the folder."""
    replace_through(Path(temporary), Path(path))
    fsync_directory(Path(path).parent)


def write_durable(path: Path, data: bytes, *, times=None) -> None:
    commit(write_temp(path, data, times=times), Path(path))
