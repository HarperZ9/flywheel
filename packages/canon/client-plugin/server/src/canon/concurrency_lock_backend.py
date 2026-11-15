from __future__ import annotations

import errno
from collections.abc import Callable
from pathlib import Path

from . import concurrency_capability as _caps
from . import concurrency_posix as _posix
from . import concurrency_windows as _win
from .concurrency_errors import LockError

VerifyDir = Callable[[Path, tuple[Path, int, int]], None]


class RetryableReleaseError(LockError):
    pass


def write_windows(
    lock_dir: Path,
    lock_name: str,
    token: str,
    snapshot: tuple[Path, int, int],
    verify_dir: VerifyDir,
) -> _caps.LockCapability:
    dir_handle = _open_windows_dir(lock_dir)
    file_handle = -1
    try:
        verify_dir(lock_dir, snapshot)
        file_handle = _create_windows_file(dir_handle, lock_name, token, lock_dir)
        verify_dir(lock_dir, snapshot)
        file_id = _verify_windows_file(file_handle, token, lock_dir / lock_name)
        return _cap(lock_dir, lock_name, token, "windows", dir_handle, file_handle, file_id)
    except LockError:
        cleanup_refs("windows", dir_handle, file_handle, lock_name)
        raise


def write_posix(
    lock_dir: Path,
    lock_name: str,
    token: str,
    snapshot: tuple[Path, int, int],
    verify_dir: VerifyDir,
) -> _caps.LockCapability:
    dir_fd = _open_lock_dir_fd(lock_dir)
    file_fd = -1
    try:
        verify_dir(lock_dir, snapshot)
        file_fd = _create_posix_file(dir_fd, lock_name, token, lock_dir)
        verify_dir(lock_dir, snapshot)
        file_id = _verify_posix_file(file_fd, token, lock_dir / lock_name)
        return _cap(lock_dir, lock_name, token, "posix", dir_fd, file_fd, file_id)
    except LockError:
        cleanup_refs("posix", dir_fd, file_fd, lock_name)
        raise


def verify_capability(capability: _caps.LockCapability) -> None:
    path = capability.path
    try:
        if capability.backend == "windows":
            current = _win.file_id(capability.file_ref)
            token = _win.read_token(capability.file_ref)
        else:
            current = _posix.file_id(capability.file_ref)
            token = _posix.read_token(capability.file_ref)
    except UnicodeError as exc:
        raise LockError("lock-token-mismatch", str(path)) from exc
    except OSError as exc:
        raise LockError("lock-release", str(exc)) from exc
    if current != capability.file_id:
        raise LockError("lock-stale", str(path))
    if token != capability.token:
        raise LockError("lock-token-mismatch", str(path))


def delete_capability(capability: _caps.LockCapability) -> None:
    try:
        if capability.backend == "windows":
            _delete_windows_capability(capability)
        else:
            _posix.delete_lock_file(capability.dir_ref, capability.lock_name)
    except OSError as exc:
        raise LockError("lock-release", str(exc)) from exc
    finally:
        if capability.backend != "windows" or capability.file_ref < 0:
            close_capability(capability)


def cleanup_refs(backend: str, dir_ref: int, file_ref: int, lock_name: str = "") -> None:
    if file_ref >= 0:
        try:
            if backend == "windows":
                _win.delete_open_file(file_ref)
            else:
                _posix.delete_lock_file(dir_ref, lock_name)
        except OSError:
            pass
    _close_raw_refs(backend, dir_ref, file_ref)


def close_capability(capability: _caps.LockCapability) -> None:
    _close_raw_refs(capability.backend, capability.dir_ref, capability.file_ref)
    capability.dir_ref = -1
    capability.file_ref = -1


def _open_windows_dir(lock_dir: Path) -> int:
    try:
        return _win.open_directory(lock_dir)
    except OSError as exc:
        raise LockError("lock-open", str(exc)) from exc


def _open_lock_dir_fd(lock_dir: Path) -> int:
    try:
        return _posix.open_directory(lock_dir)
    except OSError as exc:
        code = "lock-reparse" if exc.errno in (errno.ELOOP, errno.ENOTDIR) else "lock-open"
        raise LockError(code, str(exc)) from exc


def _create_windows_file(dir_handle: int, lock_name: str, token: str, lock_dir: Path) -> int:
    try:
        return _win.create_lock_file(dir_handle, lock_name, token)
    except FileExistsError as exc:
        raise LockError("lock-held", str(lock_dir / lock_name)) from exc
    except _win.LockWriteError as exc:
        raise LockError("lock-write", str(exc)) from exc
    except OSError as exc:
        raise LockError("lock-open", str(exc)) from exc


def _delete_windows_capability(capability: _caps.LockCapability) -> None:
    try:
        _win.delete_open_file(capability.file_ref)
    except OSError as exc:
        raise RetryableReleaseError("lock-release", str(exc)) from exc
    close_capability(capability)


def _create_posix_file(dir_fd: int, lock_name: str, token: str, lock_dir: Path) -> int:
    try:
        return _posix.create_lock_file(dir_fd, lock_name, token)
    except FileExistsError as exc:
        raise LockError("lock-held", str(lock_dir / lock_name)) from exc
    except _posix.LockWriteError as exc:
        raise LockError("lock-write", str(exc)) from exc
    except OSError as exc:
        raise LockError("lock-open", str(exc)) from exc


def _verify_windows_file(handle: int, token: str, path: Path) -> tuple[int, ...]:
    capability = _caps.LockCapability(path.parent, "", path.name, token, path, "windows", -1, handle, ())
    _verify_capability_with_id(capability, _win.file_id(handle))
    return capability.file_id


def _verify_posix_file(fd: int, token: str, path: Path) -> tuple[int, ...]:
    capability = _caps.LockCapability(path.parent, "", path.name, token, path, "posix", -1, fd, ())
    _verify_capability_with_id(capability, _posix.file_id(fd))
    return capability.file_id


def _verify_capability_with_id(capability: _caps.LockCapability, file_id: tuple[int, ...]) -> None:
    capability.file_id = file_id
    verify_capability(capability)


def _cap(
    lock_dir: Path,
    lock_name: str,
    token: str,
    backend: str,
    dir_ref: int,
    file_ref: int,
    file_id: tuple[int, ...],
) -> _caps.LockCapability:
    name = lock_name.removesuffix(".lock")
    path = lock_dir / lock_name
    return _caps.LockCapability(lock_dir.parent, name, lock_name, token, path, backend, dir_ref, file_ref, file_id)


def _close_raw_refs(backend: str, dir_ref: int, file_ref: int) -> None:
    close = _win.close_handle if backend == "windows" else _posix.close_fd
    for ref in (file_ref, dir_ref):
        if ref >= 0:
            try:
                close(ref)
            except OSError:
                pass
