from __future__ import annotations

import errno
import os
import stat

from .canonical_json import sha256_bytes
from .undo_posix_core import DirCap, check_name, close_fd, fsync_dir, verify
from .undo_receipts import UndoError

_TEMP_ATTEMPTS = 8


def read_at(parent: DirCap, name: str, *, required: bool) -> bytes | None:
    check_name(name)
    verify(parent)
    try:
        fd = os.open(name, _file_read_flags(), dir_fd=parent.fd)
    except FileNotFoundError:
        if required:
            raise UndoError("conflict")
        return None
    except OSError as exc:
        raise UndoError("unsafe_path") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise UndoError("unsafe_path")
        data = _read_fd(fd, info.st_size)
        verify(parent)
        return data
    finally:
        os.close(fd)


def write_new_or_same(parent: DirCap, name: str, data: bytes) -> str:
    check_name(name)
    status = _existing_status(parent, name, data, required=False)
    if status is not None:
        return status
    created_key: tuple[int, int] | None = None
    fd: int | None = None
    try:
        verify(parent)
        fd = os.open(name, _file_write_flags(), 0o600, dir_fd=parent.fd)
        created_key = _fd_key(fd)
        _write_all(fd, data)
        os.fsync(fd)
    except FileExistsError:
        close_fd(fd)
        return _existing_status(parent, name, data, required=True) or _conflict()
    except Exception:
        close_fd(fd)
        _cleanup_created(parent.fd, name, created_key)
        raise
    close_fd(fd)
    try:
        verify(parent)
        if read_at(parent, name, required=True) != data:
            raise UndoError("io_error")
        fsync_dir(parent.fd)
    except Exception:
        _cleanup_created(parent.fd, name, created_key)
        raise
    return "created"


def _existing_status(parent: DirCap, name: str, data: bytes, *, required: bool) -> str | None:
    current = read_at(parent, name, required=required)
    if current is None:
        return None
    if current == data:
        return "idempotent"
    raise UndoError("conflict")


def _conflict() -> str:
    raise UndoError("conflict")


def replace_at(root: DirCap, parent: DirCap, name: str, expected_hash: str, data: bytes) -> None:
    check_name(name)
    before = read_at(parent, name, required=True)
    if before is None or sha256_bytes(before) != expected_hash:
        raise UndoError("conflict")
    mode = _regular_mode_at(parent, name)
    temp = _write_temp(root, parent, name, data, mode, verify_first=True)
    committed = False
    try:
        verify(root)
        verify(parent)
        if sha256_bytes(read_at(parent, name, required=True) or b"") != expected_hash:
            raise UndoError("conflict")
        os.rename(temp, name, src_dir_fd=parent.fd, dst_dir_fd=parent.fd)
        committed = True
        fsync_dir(parent.fd)
        verify(root)
        verify(parent)
        if sha256_bytes(read_at(parent, name, required=True) or b"") != sha256_bytes(data):
            raise UndoError("io_error")
    except Exception:
        _restore(parent, name, before, mode) if committed else _unlink(parent.fd, temp)
        raise


def list_names(parent: DirCap) -> list[str]:
    verify(parent)
    names = os.listdir(parent.fd)
    verify(parent)
    return names


def _write_temp(root: DirCap, parent: DirCap, name: str, data: bytes, mode: int, *, verify_first: bool) -> str:
    for _attempt in range(_TEMP_ATTEMPTS):
        temp = f".{name}.{os.urandom(8).hex()}.tmp"
        fd: int | None = None
        try:
            if verify_first:
                verify(root)
                verify(parent)
            fd = os.open(temp, _file_write_flags(), mode, dir_fd=parent.fd)
            os.fchmod(fd, mode)
            _write_all(fd, data)
            os.fsync(fd)
            os.close(fd)
            return temp
        except FileExistsError:
            continue
        except Exception:
            close_fd(fd)
            _unlink(parent.fd, temp)
            raise
    raise UndoError("io_error")


def _restore(parent: DirCap, name: str, data: bytes, mode: int) -> None:
    temp = _write_temp(parent, parent, name, data, mode, verify_first=False)
    try:
        os.rename(temp, name, src_dir_fd=parent.fd, dst_dir_fd=parent.fd)
        fsync_dir(parent.fd)
    except Exception:
        _unlink(parent.fd, temp)
        raise


def _regular_mode_at(parent: DirCap, name: str) -> int:
    fd = os.open(name, _file_read_flags(), dir_fd=parent.fd)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise UndoError("unsafe_path")
        return stat.S_IMODE(info.st_mode)
    finally:
        os.close(fd)


def _file_read_flags() -> int:
    return os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)


def _file_write_flags() -> int:
    return os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW


def _read_fd(fd: int, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = os.read(fd, min(remaining, 65536))
        if not chunk:
            raise UndoError("io_error")
        chunks.append(chunk)
        remaining -= len(chunk)
    if os.read(fd, 1):
        raise UndoError("io_error")
    return b"".join(chunks)


def _write_all(fd: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(fd, data[offset:])
        if written <= 0:
            raise OSError(errno.EIO, "short write")
        offset += written


def _cleanup_created(dir_fd: int, name: str, expected_key: tuple[int, int] | None) -> None:
    if expected_key is None:
        return
    try:
        fd = os.open(name, _file_read_flags(), dir_fd=dir_fd)
    except OSError:
        return
    try:
        info = os.fstat(fd)
        if stat.S_ISREG(info.st_mode) and _stat_key(info) == expected_key:
            _unlink(dir_fd, name)
    finally:
        os.close(fd)


def _unlink(dir_fd: int, name: str) -> None:
    try:
        os.unlink(name, dir_fd=dir_fd)
    except OSError:
        pass


def _fd_key(fd: int) -> tuple[int, int]:
    return _stat_key(os.fstat(fd))


def _stat_key(info: os.stat_result) -> tuple[int, int]:
    return (info.st_dev, info.st_ino)


__all__ = ["list_names", "read_at", "replace_at", "write_new_or_same"]
