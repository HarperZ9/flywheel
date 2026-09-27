"""Read one source by handle and prove it did not change during the read (I9).

The identity before and after the read must match, or the item is aborted
with SOURCE_CHANGED and its staged bytes are discarded by the caller. On
Windows the identity comes from the handle (trace_import_open_win); on POSIX
the file is opened with O_NOFOLLOW and `fstat` gives device, inode, size,
mtime and ctime. On FAT and exFAT the file index is not stable, so the file
is hashed a second time after the read and the manifest says so.

With `root`, the path the open handle actually reached (GetFinalPathName on
Windows, the descriptor's link in /proc elsewhere) must lie inside it, so a
folder swapped for a junction between the check and the open is refused as
OUTSIDE_ROOT. `read_prefix` reads the first bytes the same way, for the
exclusion and idempotence probes, instead of a plain open that follows links.
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
        final = _posix_final(fd, path)
    finally:
        os.close(fd)
    return {"before": before, "after": after, "bytes": total, "sha256": digest.hexdigest(),
            "second_hash": False, "final": final}


def _posix_final(fd: int, path) -> str:
    try:
        return os.readlink(f"/proc/self/fd/{fd}")
    except OSError:
        return os.path.realpath(path)


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
            "second_hash": unstable, "final": before[5]}


class _Enough(Exception):
    pass


def read_prefix(path, limit: int, on_chunk) -> None:
    """Pass at most `limit` leading bytes to `on_chunk`, opening by handle
    without following a link (REPARSE_REFUSED or UNREADABLE otherwise)."""
    seen = [0]

    def take(chunk):
        room = limit - seen[0]
        if room > 0:
            on_chunk(chunk[:room])
        seen[0] += len(chunk)
        if seen[0] >= limit:
            raise _Enough()
    reader = _read_windows if sys.platform == "win32" else _read_posix
    if limit > 0:
        try:
            reader(path, take, None)
        except _Enough:
            pass


def _inside(final: str, root) -> bool:
    text = final
    for prefix in ("\\\\?\\UNC\\", "\\\\?\\"):
        if text.startswith(prefix):
            if prefix.endswith("UNC\\"):
                return False
            text = text[len(prefix):]
    base = os.path.normcase(os.path.realpath(root))
    try:
        return os.path.normcase(os.path.commonpath([os.path.normcase(text), base])) == base
    except ValueError:
        return False


def read_source(path, on_chunk, *, on_read=None, root=None) -> dict:
    """Stream `path` to `on_chunk`; raise SourceRefused("SOURCE_CHANGED") when
    its identity moved during the read, and OUTSIDE_ROOT when the handle
    reached a file outside `root`."""
    reader = _read_windows if sys.platform == "win32" else _read_posix
    result = reader(path, on_chunk, on_read)
    if root is not None and not _inside(result["final"], root):
        raise SourceRefused("OUTSIDE_ROOT")
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
