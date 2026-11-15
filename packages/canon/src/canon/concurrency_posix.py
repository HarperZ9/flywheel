from __future__ import annotations

import errno
import os
import stat
from pathlib import Path

_LOCK_FLAGS = os.O_CREAT | os.O_EXCL | os.O_RDWR
_MAX_TOKEN_BYTES = 4096
_HAS_DIR_FD_LOCKS = os.open in os.supports_dir_fd and os.unlink in os.supports_dir_fd


class LockWriteError(OSError):
    pass


def supported() -> bool:
    return _HAS_DIR_FD_LOCKS and hasattr(os, "pread") and all(
        hasattr(os, name) for name in ("O_DIRECTORY", "O_NOFOLLOW")
    )


def open_directory(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY") | getattr(os, "O_NOFOLLOW")
    return os.open(path, flags)


def create_lock_file(dir_fd: int, name: str, token: str) -> int:
    fd = os.open(name, _LOCK_FLAGS | getattr(os, "O_NOFOLLOW"), 0o600, dir_fd=dir_fd)
    try:
        _write_all(fd, token.encode("ascii"))
        return fd
    except OSError as exc:
        close_fd(fd)
        delete_lock_file(dir_fd, name)
        raise LockWriteError(exc.errno, str(exc)) from exc


def file_id(fd: int) -> tuple[int, int]:
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        raise OSError(errno.EINVAL, "lock file is non-regular")
    return (info.st_dev, info.st_ino)


def read_token(fd: int) -> str:
    size = os.fstat(fd).st_size
    if size > _MAX_TOKEN_BYTES:
        raise OSError(errno.EFBIG, "lock token too large")
    return os.pread(fd, size, 0).decode("ascii")


def delete_lock_file(dir_fd: int, name: str) -> None:
    try:
        os.unlink(name, dir_fd=dir_fd)
    except FileNotFoundError:
        return


def close_fd(fd: int) -> None:
    os.close(fd)


def _write_all(fd: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(fd, data[offset:])
        if written <= 0:
            raise OSError(errno.EIO, "lock write made no progress")
        offset += written
