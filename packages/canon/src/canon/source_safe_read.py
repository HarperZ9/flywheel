from __future__ import annotations

import os
import stat
from pathlib import Path

from . import concurrency_windows_api as _win

_READ_CHUNK = 65536
_WIN_FILE_DIRECTORY_FILE = 0x1
_WIN_VALUE_NAMES = ("FILE_ATTRIBUTE_DIRECTORY", "FILE_ATTRIBUTE_REPARSE_POINT", "FILE_FLAG_BACKUP_SEMANTICS", "FILE_FLAG_OPEN_REPARSE_POINT", "FILE_NON_DIRECTORY_FILE", "FILE_OPEN", "FILE_OPEN_REPARSE_POINT", "FILE_SHARE_DELETE", "FILE_SHARE_READ", "FILE_SHARE_WRITE", "FILE_SYNCHRONOUS_IO_NONALERT", "GENERIC_READ", "OPEN_EXISTING", "SYNCHRONIZE")
_WIN_VALUES = {name: getattr(_win, name, None) for name in _WIN_VALUE_NAMES}
_WIN_SHARE_ALL = _WIN_VALUES["FILE_SHARE_READ"] | _WIN_VALUES["FILE_SHARE_WRITE"] | _WIN_VALUES["FILE_SHARE_DELETE"]
_WIN_SUPPORTED = _win.supported
_WIN_PRIMITIVES = {name: getattr(_win, name, None) for name in ("close_handle", "create_file", "handle_info", "nt_create_relative", "read_file")}
_POSIX_PRIMITIVES = {name: getattr(os, name, None) for name in ("open", "fstat", "pread", "close")}
_POSIX_FLAGS = {name: getattr(os, name, None) for name in ("O_RDONLY", "O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK")}
_POSIX_DIR_FD_OPEN = _POSIX_PRIMITIVES["open"] in getattr(os, "supports_dir_fd", ())


class SafeSourceReadError(OSError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def read_regular_under_root(
    root: Path,
    root_key: tuple[int, int],
    relative: str,
    *,
    max_bytes: int,
) -> bytes:
    parts = _relative_parts(relative)
    _check_limit(max_bytes)
    if not _safe_backend_supported():
        raise SafeSourceReadError("unsafe_path")
    if os.name == "nt":
        return _win_read_under_root(root, root_key, parts, max_bytes)
    return _posix_read_under_root(root, root_key, parts, max_bytes)


def _safe_backend_supported() -> bool:
    try:
        return _win_supported() if os.name == "nt" else _posix_supported()
    except Exception:
        return False

def _relative_parts(relative: str) -> tuple[str, ...]:
    if type(relative) is not str or relative == "" or "\0" in relative:
        raise SafeSourceReadError("unsafe_path")
    if relative.startswith("/") or "\\" in relative or ":" in relative:
        raise SafeSourceReadError("unsafe_path")
    parts = tuple(relative.split("/"))
    if any(part in ("", ".", "..") for part in parts):
        raise SafeSourceReadError("unsafe_path")
    return parts


def _check_limit(max_bytes: int) -> None:
    if type(max_bytes) is not int or max_bytes < 0:
        raise SafeSourceReadError("invalid_args")


def _posix_supported() -> bool:
    return (
        os.name != "nt"
        and _POSIX_DIR_FD_OPEN
        and all(_posix_primitive_bound(name) for name in _POSIX_PRIMITIVES)
        and all(_constant_bound(os, _POSIX_FLAGS, name) for name in _POSIX_FLAGS)
    )


def _posix_primitive_bound(name: str) -> bool:
    primitive = _POSIX_PRIMITIVES.get(name)
    return callable(primitive) and getattr(os, name, None) is primitive

def _constant_bound(module: object, values: dict[str, object], name: str) -> bool:
    value = values.get(name)
    current = getattr(module, name, None)
    return type(value) is int and type(current) is int and current == value

def _win_supported() -> bool:
    if getattr(_win, "supported", None) is not _WIN_SUPPORTED:
        return False
    try:
        available = _WIN_SUPPORTED()
    except Exception:
        return False
    return bool(available) and all(_win_primitive_bound(name) for name in _WIN_PRIMITIVES) and all(_constant_bound(_win, _WIN_VALUES, name) for name in _WIN_VALUES)


def _win_primitive_bound(name: str) -> bool:
    primitive = _WIN_PRIMITIVES.get(name)
    return callable(primitive) and getattr(_win, name, None) is primitive


def _posix_read_under_root(
    root: Path,
    root_key: tuple[int, int],
    parts: tuple[str, ...],
    max_bytes: int,
) -> bytes:
    dirs = [_posix_open_root(root, root_key)]
    try:
        for part in parts[:-1]:
            dirs.append(_posix_open_dir_at(dirs[-1], part))
        return _posix_read_regular_at(dirs[-1], parts[-1], max_bytes)
    finally:
        for fd in reversed(dirs):
            _posix_close(fd)


def _posix_open_root(root: Path, root_key: tuple[int, int]) -> int:
    try:
        fd = _POSIX_PRIMITIVES["open"](root, _posix_dir_flags())
    except OSError as exc:
        raise SafeSourceReadError("unsafe_path") from exc
    try:
        info = _POSIX_PRIMITIVES["fstat"](fd)
        if not stat.S_ISDIR(info.st_mode) or _stat_key(info) != root_key:
            raise SafeSourceReadError("unsafe_path")
        return fd
    except Exception:
        _posix_close(fd)
        raise


def _posix_open_dir_at(parent_fd: int, name: str) -> int:
    try:
        return _POSIX_PRIMITIVES["open"](name, _posix_dir_flags(), dir_fd=parent_fd)
    except FileNotFoundError as exc:
        raise SafeSourceReadError("source_unreachable") from exc
    except OSError as exc:
        raise SafeSourceReadError("unsafe_path") from exc


def _posix_read_regular_at(parent_fd: int, name: str, max_bytes: int) -> bytes:
    try:
        flags = _POSIX_FLAGS["O_RDONLY"] | _POSIX_FLAGS["O_NOFOLLOW"] | _POSIX_FLAGS["O_NONBLOCK"]
        fd = _POSIX_PRIMITIVES["open"](name, flags, dir_fd=parent_fd)
    except FileNotFoundError as exc:
        raise SafeSourceReadError("source_unreachable") from exc
    except OSError as exc:
        raise SafeSourceReadError("unsafe_path") from exc
    try:
        info = _POSIX_PRIMITIVES["fstat"](fd)
        if not stat.S_ISREG(info.st_mode):
            raise SafeSourceReadError("unsafe_path")
        if info.st_size > max_bytes:
            raise SafeSourceReadError("invalid_args")
        return _posix_pread_exact(fd, info.st_size)
    finally:
        _posix_close(fd)


def _posix_pread_exact(fd: int, size: int) -> bytes:
    chunks: list[bytes] = []
    offset = 0
    while offset < size:
        chunk = _POSIX_PRIMITIVES["pread"](fd, min(size - offset, _READ_CHUNK), offset)
        if not chunk:
            raise SafeSourceReadError("source_unreachable")
        chunks.append(chunk)
        offset += len(chunk)
    if _POSIX_PRIMITIVES["pread"](fd, 1, size):
        raise SafeSourceReadError("source_unreachable")
    return b"".join(chunks)


def _posix_dir_flags() -> int:
    return _POSIX_FLAGS["O_RDONLY"] | _POSIX_FLAGS["O_DIRECTORY"] | _POSIX_FLAGS["O_NOFOLLOW"] | _POSIX_FLAGS["O_NONBLOCK"]


def _posix_close(fd: int) -> None:
    try:
        _POSIX_PRIMITIVES["close"](fd)
    except OSError:
        pass


def _win_read_under_root(
    root: Path,
    root_key: tuple[int, int],
    parts: tuple[str, ...],
    max_bytes: int,
) -> bytes:
    handles = [_win_open_root(root, root_key)]
    try:
        for part in parts[:-1]:
            handles.append(_win_open_dir_at(handles[-1], part))
        return _win_read_regular_at(handles[-1], parts[-1], max_bytes)
    finally:
        for handle in reversed(handles):
            _win_close(handle)


def _win_open_root(root: Path, root_key: tuple[int, int]) -> int:
    flags = _WIN_VALUES["FILE_FLAG_BACKUP_SEMANTICS"] | _WIN_VALUES["FILE_FLAG_OPEN_REPARSE_POINT"]
    try:
        handle = _WIN_PRIMITIVES["create_file"](str(root), _WIN_VALUES["GENERIC_READ"], _WIN_SHARE_ALL, _WIN_VALUES["OPEN_EXISTING"], flags)
    except OSError as exc:
        raise SafeSourceReadError("unsafe_path") from exc
    try:
        info = _WIN_PRIMITIVES["handle_info"](handle)
        if not _win_is_directory(info) or _win_is_reparse(info) or _win_key(info) != root_key:
            raise SafeSourceReadError("unsafe_path")
        return handle
    except Exception:
        _win_close(handle)
        raise


def _win_open_dir_at(parent_handle: int, name: str) -> int:
    options = _WIN_FILE_DIRECTORY_FILE | _WIN_VALUES["FILE_OPEN_REPARSE_POINT"] | _WIN_VALUES["FILE_SYNCHRONOUS_IO_NONALERT"]
    try:
        handle = _WIN_PRIMITIVES["nt_create_relative"](
            parent_handle,
            name,
            _WIN_VALUES["GENERIC_READ"] | _WIN_VALUES["SYNCHRONIZE"],
            _WIN_SHARE_ALL,
            _WIN_VALUES["FILE_OPEN"],
            options,
        )
    except FileNotFoundError as exc:
        raise SafeSourceReadError("source_unreachable") from exc
    except OSError as exc:
        raise SafeSourceReadError("unsafe_path") from exc
    try:
        info = _WIN_PRIMITIVES["handle_info"](handle)
        if not _win_is_directory(info) or _win_is_reparse(info):
            raise SafeSourceReadError("unsafe_path")
        return handle
    except Exception:
        _win_close(handle)
        raise


def _win_read_regular_at(parent_handle: int, name: str, max_bytes: int) -> bytes:
    options = _WIN_VALUES["FILE_NON_DIRECTORY_FILE"] | _WIN_VALUES["FILE_OPEN_REPARSE_POINT"] | _WIN_VALUES["FILE_SYNCHRONOUS_IO_NONALERT"]
    try:
        handle = _WIN_PRIMITIVES["nt_create_relative"](
            parent_handle,
            name,
            _WIN_VALUES["GENERIC_READ"] | _WIN_VALUES["SYNCHRONIZE"],
            _WIN_SHARE_ALL,
            _WIN_VALUES["FILE_OPEN"],
            options,
        )
    except FileNotFoundError as exc:
        raise SafeSourceReadError("source_unreachable") from exc
    except OSError as exc:
        raise SafeSourceReadError("unsafe_path") from exc
    try:
        return _win_read_checked(handle, max_bytes)
    finally:
        _win_close(handle)


def _win_read_checked(handle: int, max_bytes: int) -> bytes:
    info = _WIN_PRIMITIVES["handle_info"](handle)
    if _win_is_reparse(info) or _win_is_directory(info):
        raise SafeSourceReadError("unsafe_path")
    size = _win_size(info)
    if size > max_bytes:
        raise SafeSourceReadError("invalid_args")
    data = _WIN_PRIMITIVES["read_file"](handle, size + 1)
    if len(data) != size:
        raise SafeSourceReadError("source_unreachable")
    return data


def _win_is_directory(info: _win.HandleInfo) -> bool:
    return bool(int(info.dwFileAttributes) & _WIN_VALUES["FILE_ATTRIBUTE_DIRECTORY"])


def _win_is_reparse(info: _win.HandleInfo) -> bool:
    return bool(int(info.dwFileAttributes) & _WIN_VALUES["FILE_ATTRIBUTE_REPARSE_POINT"])


def _win_key(info: _win.HandleInfo) -> tuple[int, int]:
    index = (int(info.nFileIndexHigh) << 32) | int(info.nFileIndexLow)
    return (int(info.dwVolumeSerialNumber), index)


def _win_size(info: _win.HandleInfo) -> int:
    return (int(info.nFileSizeHigh) << 32) | int(info.nFileSizeLow)


def _win_close(handle: int) -> None:
    try:
        _WIN_PRIMITIVES["close_handle"](handle)
    except OSError:
        pass


def _stat_key(info: os.stat_result) -> tuple[int, int]:
    if os.name == "nt":
        return (info.st_dev & 0xFFFFFFFF, info.st_ino)
    return (info.st_dev, info.st_ino)
