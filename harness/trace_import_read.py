"""Read one source by handle and prove it did not change during the read (I9).

The identity before and after the read must match, or the item is aborted
with SOURCE_CHANGED and its staged bytes are discarded by the caller. On
Windows the identity comes from the handle (trace_import_open_win); on POSIX
the file is opened with O_NOFOLLOW and `fstat` gives device, inode, size,
mtime and ctime. On FAT and exFAT the file index is not stable, so the file
is hashed a second time after the read and the manifest says so.
"""
from __future__ import annotations

import hashlib
import os
import sys


class SourceRefused(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _posix_identity(fd: int) -> tuple:
    info = os.fstat(fd)
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _read_posix(path, on_chunk, on_read) -> dict:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        raise SourceRefused("UNREADABLE") from None
    try:
        before = _posix_identity(fd)
        if on_read:
            on_read(path)
        digest, total = hashlib.sha256(), 0
        while chunk := os.read(fd, 1024 * 1024):
            digest.update(chunk)
            total += len(chunk)
            on_chunk(chunk)
        after = _posix_identity(fd)
    finally:
        os.close(fd)
    return {"before": before, "after": after, "bytes": total, "sha256": digest.hexdigest(),
            "second_hash": False}


def _read_windows(path, on_chunk, on_read) -> dict:
    from . import trace_import_open_win as win
    try:
        handle = win.open_source(path)
    except PermissionError as exc:
        raise SourceRefused("REPARSE_REFUSED" if "REPARSE" in str(exc) else "UNREADABLE") \
            from None
    except OSError:
        raise SourceRefused("UNREADABLE") from None
    try:
        before = win.identity(handle)
        if on_read:
            on_read(path)
        digest = hashlib.sha256()

        def take(chunk):
            digest.update(chunk)
            on_chunk(chunk)
        total = win.read_chunks(handle, take)
        after = win.identity(handle)
        unstable = win.file_system(handle).upper() in ("FAT", "FAT32", "EXFAT")
    finally:
        win.close(handle)
    return {"before": before, "after": after, "bytes": total, "sha256": digest.hexdigest(),
            "second_hash": unstable}


def read_source(path, on_chunk, *, on_read=None) -> dict:
    """Stream `path` to `on_chunk`; raise SourceRefused("SOURCE_CHANGED") when
    its identity moved during the read."""
    reader = _read_windows if sys.platform == "win32" else _read_posix
    result = reader(path, on_chunk, on_read)
    if result["before"] != result["after"] or result["bytes"] != result["before"][2]:
        raise SourceRefused("SOURCE_CHANGED")
    if result["second_hash"]:
        again = hashlib.sha256()
        with open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                again.update(chunk)
        if again.hexdigest() != result["sha256"]:
            raise SourceRefused("SOURCE_CHANGED")
    return result
