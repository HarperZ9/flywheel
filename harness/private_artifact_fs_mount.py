"""Object-bound filesystem admission for private_artifact_fs POSIX roots."""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import sys

from .private_artifact_fs import IO_ERROR, UNSUPPORTED_FS, PrivateArtifactError

_MOUNTINFO = Path("/proc/self/mountinfo")
_ALLOWED_POSIX_FSTYPES = frozenset({"btrfs", "ext2", "ext3", "ext4", "overlay", "tmpfs", "xfs"})
_REFUSED_POSIX_FSTYPES = frozenset({"9p", "drvfs"})
_ALLOWED_MAGIC = frozenset({0xEF53, 0x01021994, 0x58465342, 0x9123683E, 0x794C7630})
_REFUSED_MAGIC = frozenset({0x01021997})
_LIBC = None


def supported() -> bool:
    return os.name != "nt" and sys.platform.startswith("linux") and _MOUNTINFO.is_file()


def admit_fd_mount(fd: int) -> None:
    magic = _fstatfs_magic(fd)
    if magic in _REFUSED_MAGIC or magic not in _ALLOWED_MAGIC:
        raise PrivateArtifactError(UNSUPPORTED_FS)
    fstypes = _fstypes_for_fd(fd)
    if fstypes & _REFUSED_POSIX_FSTYPES:
        raise PrivateArtifactError(UNSUPPORTED_FS)
    if not fstypes or any(fstype not in _ALLOWED_POSIX_FSTYPES for fstype in fstypes):
        raise PrivateArtifactError(UNSUPPORTED_FS)


def _fstypes_for_fd(fd: int) -> frozenset[str]:
    if not supported():
        raise PrivateArtifactError(UNSUPPORTED_FS)
    try:
        st_dev = os.fstat(fd).st_dev
    except OSError as exc:
        raise PrivateArtifactError(IO_ERROR) from exc
    try:
        target = f"{os.major(st_dev)}:{os.minor(st_dev)}"
    except (AttributeError, OverflowError, ValueError) as exc:
        raise PrivateArtifactError(UNSUPPORTED_FS) from exc
    matches: set[str] = set()
    try:
        lines = _mountinfo_lines()
    except OSError as exc:
        raise PrivateArtifactError(UNSUPPORTED_FS) from exc
    for line in lines:
        parsed = _parse_mountinfo(line)
        if parsed is None:
            continue
        device, fstype = parsed
        if device == target:
            matches.add(fstype)
    if not matches:
        raise PrivateArtifactError(UNSUPPORTED_FS)
    return frozenset(matches)


def _fstatfs_magic(fd: int) -> int:
    if not supported():
        raise PrivateArtifactError(UNSUPPORTED_FS)
    buf = ctypes.create_string_buffer(256)
    rc = _libc().fstatfs(fd, ctypes.byref(buf))
    if rc != 0:
        err = ctypes.get_errno()
        raise PrivateArtifactError(IO_ERROR) from OSError(err, "fstatfs failed")
    width = ctypes.sizeof(ctypes.c_long)
    return int(ctypes.c_long.from_buffer_copy(buf.raw[:width]).value) & 0xFFFFFFFF


def _mountinfo_lines() -> list[str]:
    return _MOUNTINFO.read_text(encoding="utf-8").splitlines()


def _libc():
    global _LIBC
    if _LIBC is None:
        try:
            libc = ctypes.CDLL(None, use_errno=True)
            libc.fstatfs.argtypes = [ctypes.c_int, ctypes.c_void_p]
            libc.fstatfs.restype = ctypes.c_int
        except (AttributeError, OSError) as exc:
            raise PrivateArtifactError(UNSUPPORTED_FS) from exc
        _LIBC = libc
    return _LIBC


def _parse_mountinfo(line: str) -> tuple[str, str] | None:
    fields = line.split()
    if len(fields) < 10:
        return None
    try:
        separator = fields.index("-")
    except ValueError:
        return None
    if separator < 3 or separator + 1 >= len(fields):
        return None
    return fields[2], fields[separator + 1]


__all__ = ["admit_fd_mount", "supported"]
