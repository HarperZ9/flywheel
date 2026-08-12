"""Windows identity anchor for private provider staging directories."""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import stat
from ctypes import wintypes


class _FileInfo(ctypes.Structure):
    _fields_ = [
        ("attributes", wintypes.DWORD), ("created", wintypes.FILETIME),
        ("accessed", wintypes.FILETIME), ("written", wintypes.FILETIME),
        ("volume", wintypes.DWORD), ("size_high", wintypes.DWORD),
        ("size_low", wintypes.DWORD), ("links", wintypes.DWORD),
        ("index_high", wintypes.DWORD), ("index_low", wintypes.DWORD),
    ]


class StageAnchor:
    def __init__(self, api, handle, inode: int):
        self.api, self.handle, self.inode = api, handle, inode

    def matches(self, path: Path) -> bool:
        try:
            info = path.lstat()
            return stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode) and info.st_ino == self.inode
        except OSError:
            return False

    def current_path(self) -> Path:
        buffer = ctypes.create_unicode_buffer(32768)
        length = self.api.GetFinalPathNameByHandleW(self.handle, buffer, len(buffer), 0)
        if not length or length >= len(buffer):
            raise OSError(ctypes.get_last_error(), "stage anchor path unavailable")
        value = buffer.value
        if value.startswith("\\\\?\\UNC\\"): value = "\\\\" + value[8:]
        elif value.startswith("\\\\?\\"): value = value[4:]
        return Path(value)

    def close(self) -> None:
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def _reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _remove_leaf(path: Path, info: os.stat_result) -> bool:
    ok = True
    if stat.S_ISREG(info.st_mode) and not _reparse(info):
        flags = os.O_WRONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = None
        try:
            descriptor = os.open(path, flags); opened = os.fstat(descriptor)
            safe = info.st_nlink == opened.st_nlink == 1 and (opened.st_dev, opened.st_ino) == (info.st_dev, info.st_ino)
            if safe: os.ftruncate(descriptor, 0)
            else: ok = False
        except OSError: ok = False
        finally:
            if descriptor is not None: os.close(descriptor)
    try: path.rmdir() if stat.S_ISDIR(info.st_mode) else path.unlink()
    except OSError: ok = False
    return ok


def scrub_owned_tree(root: Path, preserve_root: bool = False) -> bool:
    """Remove an exclusively harness-created tree without traversing reparse leaves."""
    ok, stack = True, [(root, False)]
    while stack:
        path, visited = stack.pop()
        try: info = path.lstat()
        except FileNotFoundError: continue
        except OSError: ok = False; continue
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or _reparse(info):
            ok = _remove_leaf(path, info) and ok; continue
        if visited:
            if preserve_root and path == root: continue
            try: path.rmdir()
            except OSError: ok = False
            continue
        stack.append((path, True))
        try:
            with os.scandir(path) as entries: stack.extend((path / entry.name, False) for entry in entries)
        except OSError: ok = False
    return ok


def anchor_stage(path: Path) -> StageAnchor:
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    api.CreateFileW.restype = wintypes.HANDLE
    api.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.POINTER(_FileInfo)]
    api.GetFinalPathNameByHandleW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    api.GetFinalPathNameByHandleW.restype = wintypes.DWORD
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = api.CreateFileW(str(path), 0x80000000, 0x3, None, 3, 0x02200000, None)
    if handle == wintypes.HANDLE(-1).value:
        raise OSError(ctypes.get_last_error(), "stage directory anchor unavailable")
    info = _FileInfo()
    if not api.GetFileInformationByHandle(handle, ctypes.byref(info)):
        api.CloseHandle(handle)
        raise OSError(ctypes.get_last_error(), "stage directory identity unavailable")
    return StageAnchor(api, handle, (info.index_high << 32) | info.index_low)
