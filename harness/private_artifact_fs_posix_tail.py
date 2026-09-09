"""Helper tail for private_artifact_fs_posix kept separate for file gate."""
from __future__ import annotations

import errno
import ctypes
import os
from pathlib import Path, PurePosixPath

from .private_artifact_fs import (
    IO_ERROR,
    UNSAFE_PATH,
    UNSUPPORTED_OS,
    ArtifactIdentity,
    PrivateArtifactError,
)

AT_EMPTY_PATH = 0x1000
_LINKAT = None
_UNSUPPORTED_TMP = {
    getattr(errno, name)
    for name in ("EINVAL", "ENOSYS", "ENOTSUP", "EOPNOTSUPP", "EPERM")
    if hasattr(errno, name)
}


def relative_parts(rel: str | os.PathLike[str]) -> tuple[str, ...]:
    try:
        text = os.fspath(rel)
    except TypeError as exc:
        raise PrivateArtifactError(UNSAFE_PATH) from exc
    if type(text) is not str or not text or "\\" in text or ":" in text:
        raise PrivateArtifactError(UNSAFE_PATH)
    path = PurePosixPath(text)
    if path.is_absolute():
        raise PrivateArtifactError(UNSAFE_PATH)
    parts = path.parts
    if not parts:
        raise PrivateArtifactError(UNSAFE_PATH)
    for part in parts:
        check_name(part)
    return tuple(parts)


def absolute_existing(root: Path) -> Path:
    root = Path(root)
    if not root.is_absolute():
        root = Path.cwd() / root
    if any(part in (".", "..") for part in root.parts[1:]):
        raise PrivateArtifactError(UNSAFE_PATH)
    return root


def check_name(name: str) -> None:
    if type(name) is str:
        try:
            name.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise PrivateArtifactError(UNSAFE_PATH) from exc
    if (
        type(name) is not str
        or name in ("", ".", "..")
        or "/" in name
        or "\\" in name
        or "\0" in name
        or ":" in name
    ):
        raise PrivateArtifactError(UNSAFE_PATH)


def read_flags() -> int:
    return os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)


def write_flags() -> int:
    return os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW


def open_anonymous_tmp(dir_fd: int) -> int:
    flags = getattr(os, "O_TMPFILE", 0)
    if not flags:
        raise PrivateArtifactError(UNSUPPORTED_OS)
    try:
        return os.open(".", os.O_RDWR | flags | getattr(os, "O_CLOEXEC", 0), 0o600, dir_fd=dir_fd)
    except OSError as exc:
        if exc.errno in _UNSUPPORTED_TMP:
            raise PrivateArtifactError(UNSUPPORTED_OS) from exc
        raise


def link_fd_to_name(fd: int, parent_fd: int, name: str) -> None:
    encoded = os.fsencode(name)
    rc = _linkat()(fd, b"", parent_fd, encoded, AT_EMPTY_PATH)
    if rc == 0:
        return
    err = ctypes.get_errno()
    if err == errno.EEXIST:
        raise FileExistsError(err, "file exists", name)
    if err in _UNSUPPORTED_TMP:
        raise PrivateArtifactError(UNSUPPORTED_OS) from OSError(err, "linkat unsupported", name)
    raise OSError(err, "linkat failed", name)


def write_all(fd: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(fd, data[offset:])
        if written <= 0:
            raise OSError(errno.EIO, "short write")
        offset += written


def identity(info: os.stat_result) -> ArtifactIdentity:
    return ArtifactIdentity("posix", int(info.st_dev), int(info.st_ino))


def fsync_dir(fd: int) -> None:
    try:
        os.fsync(fd)
    except OSError as exc:
        if exc.errno in {errno.EINVAL, getattr(errno, "ENOTSUP", 0), getattr(errno, "EOPNOTSUPP", 0)}:
            return
        raise PrivateArtifactError(IO_ERROR) from exc


def _linkat():
    global _LINKAT
    if _LINKAT is None:
        libc = ctypes.CDLL(None, use_errno=True)
        func = libc.linkat
        func.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
        func.restype = ctypes.c_int
        _LINKAT = func
    return _LINKAT


def close_fd(fd: int | None) -> None:
    if fd is None:
        return
    try:
        os.close(fd)
    except OSError:
        pass


__all__ = [
    "absolute_existing",
    "check_name",
    "close_fd",
    "fsync_dir",
    "identity",
    "link_fd_to_name",
    "open_anonymous_tmp",
    "read_flags",
    "relative_parts",
    "write_all",
    "write_flags",
]
