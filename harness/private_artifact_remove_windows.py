"""Windows half of handle-based removal. Parents are held open without
FILE_SHARE_DELETE, so they cannot be renamed or replaced while their children
are removed; each entry is opened relative to its parent handle with
FILE_OPEN_REPARSE_POINT, so a junction or symbolic link is opened as itself;
deletion is by handle with POSIX semantics, falling back to delete-on-close
where the file system does not support them (FAT, exFAT)."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path

from . import private_artifact_fs_windows_api as win
from .private_artifact_fs_windows_tail import handle_identity_from_info, is_dir, is_reparse
from .private_artifact_remove import RemovalError

_READ_ATTRIBUTES = 0x80
_DIR_OPEN = win.FILE_DIRECTORY_FILE | win.FILE_OPEN_REPARSE_POINT | win.FILE_SYNCHRONOUS_IO_NONALERT
_ENTRY_OPEN = win.FILE_OPEN_REPARSE_POINT | win.FILE_SYNCHRONOUS_IO_NONALERT
_POSIX_DELETE = 0x1 | 0x2 | 0x10  # DELETE, POSIX_SEMANTICS, IGNORE_READONLY_ATTRIBUTE


class _IoStatus(ctypes.Structure):
    _fields_ = [("Status", ctypes.c_ssize_t), ("Information", ctypes.c_size_t)]


def _delete(handle: int) -> None:
    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtSetInformationFile.argtypes = (wintypes.HANDLE, ctypes.POINTER(_IoStatus),
                                           ctypes.c_void_p, wintypes.ULONG, ctypes.c_int)
    ntdll.NtSetInformationFile.restype = ctypes.c_long
    flags = wintypes.ULONG(_POSIX_DELETE)
    status = ntdll.NtSetInformationFile(wintypes.HANDLE(handle), ctypes.byref(_IoStatus()),
                                        ctypes.byref(flags), ctypes.sizeof(flags), 64)
    if status < 0:
        win.delete_on_close(handle)


def _open_root(root: Path, expected) -> int:
    try:
        handle = win.create_file(str(root), win.GENERIC_READ | win.SYNCHRONIZE,
                                 win.FILE_SHARE_READ | win.FILE_SHARE_WRITE, win.OPEN_EXISTING,
                                 win.FILE_FLAG_BACKUP_SEMANTICS | win.FILE_FLAG_OPEN_REPARSE_POINT)
    except FileNotFoundError:
        raise RemovalError("ROOT_CHANGED" if expected is not None else "NOT_FOUND") from None
    info = win.handle_info(handle)
    if is_reparse(info) or not is_dir(info) or (
            expected is not None and handle_identity_from_info(info) != expected):
        win.close_handle(handle)
        raise RemovalError("ROOT_CHANGED" if expected is not None else "UNSAFE_PATH")
    return handle


def _open(parent: int, name: str, access: int, share: int, options: int) -> int | None:
    try:
        return win.nt_create_relative(parent, name, access, share, win.FILE_OPEN, options)
    except FileNotFoundError:
        return None


def _remove_entry(parent: int, parent_path: Path, name: str, counts: dict) -> None:
    access = win.DELETE | _READ_ATTRIBUTES | win.SYNCHRONIZE
    share = win.FILE_SHARE_READ | win.FILE_SHARE_WRITE | win.FILE_SHARE_DELETE
    handle = _open(parent, name, access, share, _ENTRY_OPEN)
    if handle is None:
        return
    try:
        info = win.handle_info(handle)
        if is_reparse(info):
            _delete(handle)
            counts["links"] += 1
            return
        if is_dir(info):
            here = parent_path / name
            for child in sorted(entry.name for entry in os.scandir(here)):
                _remove_entry(handle, here, child, counts)
            _delete(handle)
            counts["dirs"] += 1
            return
        _delete(handle)
        counts["files"] += 1
    finally:
        win.close_handle(handle)


def remove_at(root: Path, parts: tuple[str, ...], expected) -> dict:
    counts = {"files": 0, "dirs": 0, "links": 0}
    try:
        chain = [_open_root(root, expected)]
    except RemovalError as exc:
        if exc.code == "NOT_FOUND":
            return counts
        raise
    try:
        here = root
        for name in parts[:-1]:
            child = _open(chain[-1], name, win.GENERIC_READ | win.SYNCHRONIZE,
                          win.FILE_SHARE_READ | win.FILE_SHARE_WRITE, _DIR_OPEN)
            if child is None:
                return counts
            chain.append(child)
            if is_reparse(win.handle_info(child)):
                raise RemovalError("UNSAFE_PATH")
            here = here / name
        _remove_entry(chain[-1], here, parts[-1], counts)
        return counts
    except OSError as exc:
        raise RemovalError(f"REMOVE_FAILED:{getattr(exc, 'winerror', None) or exc.errno}") from None
    finally:
        for handle in reversed(chain):
            win.close_handle(handle)
