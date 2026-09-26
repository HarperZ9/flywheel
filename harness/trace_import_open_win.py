"""Windows source reading for imports (7.6, SP-30).

A source is opened with GENERIC_READ, sharing read, write and delete, and
FILE_FLAG_OPEN_REPARSE_POINT; a handle whose attributes show a reparse point
is closed and refused. Sharing delete lets a Claude Code sweep or a Codex
compression rename the file during the read; that shows up as a changed
identity. The identity is the volume serial, file index, size, last-write
and change times, and the final path of the handle, taken before and after
the read. Nothing is opened for writing and no timestamp is touched.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from . import private_artifact_fs_windows_api as win

_FILE_FLAG_SEQUENTIAL_SCAN = 0x08000000
_CHUNK = 1024 * 1024


class _BasicInfo(ctypes.Structure):
    _fields_ = [("CreationTime", ctypes.c_longlong), ("LastAccessTime", ctypes.c_longlong),
                ("LastWriteTime", ctypes.c_longlong), ("ChangeTime", ctypes.c_longlong),
                ("FileAttributes", wintypes.DWORD)]


def _kernel():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetFileInformationByHandleEx.argtypes = (wintypes.HANDLE, ctypes.c_int,
                                                    ctypes.c_void_p, wintypes.DWORD)
    kernel.GetFinalPathNameByHandleW.argtypes = (wintypes.HANDLE, wintypes.LPWSTR,
                                                 wintypes.DWORD, wintypes.DWORD)
    kernel.GetFinalPathNameByHandleW.restype = wintypes.DWORD
    kernel.GetVolumeInformationByHandleW.argtypes = (
        wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, wintypes.LPWSTR, wintypes.DWORD)
    kernel.ReadFile.argtypes = (wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                                ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p)
    return kernel


def open_source(path) -> int:
    """A read handle, or OSError; a reparse point raises PermissionError."""
    handle = win.create_file(str(path), win.GENERIC_READ,
                             win.FILE_SHARE_READ | win.FILE_SHARE_WRITE | win.FILE_SHARE_DELETE,
                             win.OPEN_EXISTING,
                             win.FILE_FLAG_OPEN_REPARSE_POINT | _FILE_FLAG_SEQUENTIAL_SCAN)
    if int(win.handle_info(handle).dwFileAttributes) & win.FILE_ATTRIBUTE_REPARSE_POINT:
        win.close_handle(handle)
        raise PermissionError("REPARSE_REFUSED")
    return handle


def identity(handle: int) -> tuple:
    info = win.handle_info(handle)
    kernel = _kernel()
    basic = _BasicInfo()
    if not kernel.GetFileInformationByHandleEx(wintypes.HANDLE(handle), 0, ctypes.byref(basic),
                                               ctypes.sizeof(basic)):
        raise ctypes.WinError(ctypes.get_last_error())
    buffer = ctypes.create_unicode_buffer(1024)
    kernel.GetFinalPathNameByHandleW(wintypes.HANDLE(handle), buffer, 1024, 0)
    size = (int(info.nFileSizeHigh) << 32) | int(info.nFileSizeLow)
    index = (int(info.nFileIndexHigh) << 32) | int(info.nFileIndexLow)
    return (int(info.dwVolumeSerialNumber), index, size, basic.LastWriteTime,
            basic.ChangeTime, buffer.value)


def file_system(handle: int) -> str:
    kernel = _kernel()
    name = ctypes.create_unicode_buffer(64)
    if not kernel.GetVolumeInformationByHandleW(wintypes.HANDLE(handle), None, 0, None, None,
                                                None, name, 64):
        return "unknown"
    return name.value


def read_chunks(handle: int, on_chunk) -> int:
    """Read to the end in 1 MiB pieces, passing each to `on_chunk`."""
    kernel = _kernel()
    buffer = ctypes.create_string_buffer(_CHUNK)
    got, total = wintypes.DWORD(), 0
    while True:
        if not kernel.ReadFile(wintypes.HANDLE(handle), buffer, _CHUNK, ctypes.byref(got), None):
            raise ctypes.WinError(ctypes.get_last_error())
        if got.value == 0:
            return total
        on_chunk(buffer.raw[:got.value])
        total += got.value


def close(handle: int) -> None:
    win.close_handle(handle)
