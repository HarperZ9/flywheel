from __future__ import annotations

from collections.abc import Callable
import os
import stat


class PosixWitnessWriteError(OSError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def write_once_posix(
    dir_fd: int,
    name: str,
    data: bytes,
    *,
    verify: Callable[[], None],
    write_all: Callable[[int, bytes], None],
) -> str:
    existing = _read_existing(dir_fd, name, verify)
    if existing is not None:
        if existing == data:
            return "idempotent"
        raise PosixWitnessWriteError("conflict")
    return _create_once(dir_fd, name, data, verify=verify, write_all=write_all)


def _create_once(
    dir_fd: int,
    name: str,
    data: bytes,
    *,
    verify: Callable[[], None],
    write_all: Callable[[int, bytes], None],
) -> str:
    fd: int | None = None
    created_key: tuple[int, int] | None = None
    try:
        _verify(verify)
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dir_fd)
        created_key = _stat_key(os.fstat(fd))
        _verify(verify)
        write_all(fd, data)
        _verify(verify)
        os.fsync(fd)
        _verify(verify)
        os.close(fd)
        fd = None
        _verify(verify)
    except PosixWitnessWriteError:
        _close_if_open(fd)
        _cleanup_created(dir_fd, name, created_key)
        raise
    except OSError as exc:
        _close_if_open(fd)
        _cleanup_created(dir_fd, name, created_key)
        raise PosixWitnessWriteError("io_error") from exc
    if _read_existing(dir_fd, name, verify) != data:
        _cleanup_created(dir_fd, name, created_key)
        raise PosixWitnessWriteError("io_error")
    return "created"


def _read_existing(dir_fd: int, name: str, verify: Callable[[], None]) -> bytes | None:
    try:
        fd = os.open(name, _read_flags(), dir_fd=dir_fd)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise PosixWitnessWriteError("unsafe_path") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise PosixWitnessWriteError("conflict")
        data = _pread_all(fd, before.st_size)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    if (_stat_key(before), before.st_size) != (_stat_key(after), after.st_size):
        raise PosixWitnessWriteError("unsafe_path")
    _verify(verify)
    return data


def _cleanup_created(dir_fd: int, name: str, expected_key: tuple[int, int] | None) -> None:
    if expected_key is None:
        return
    try:
        fd = os.open(name, _read_flags(), dir_fd=dir_fd)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise PosixWitnessWriteError("io_error") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or _stat_key(info) != expected_key:
            raise PosixWitnessWriteError("conflict")
    finally:
        os.close(fd)
    try:
        os.unlink(name, dir_fd=dir_fd)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise PosixWitnessWriteError("io_error") from exc


def _verify(verify: Callable[[], None]) -> None:
    try:
        verify()
    except PosixWitnessWriteError:
        raise
    except Exception as exc:
        raise PosixWitnessWriteError("unsafe_path") from exc


def _read_flags() -> int:
    return os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)


def _close_if_open(fd: int | None) -> None:
    if fd is None:
        return
    try:
        os.close(fd)
    except OSError:
        pass


def _pread_all(fd: int, size: int) -> bytes:
    chunks: list[bytes] = []
    offset = 0
    while offset < size:
        chunk = os.pread(fd, size - offset, offset)
        if not chunk:
            break
        chunks.append(chunk)
        offset += len(chunk)
    return b"".join(chunks)


def _stat_key(info: os.stat_result) -> tuple[int, int]:
    return (info.st_dev, info.st_ino)


__all__ = ["PosixWitnessWriteError", "write_once_posix"]
