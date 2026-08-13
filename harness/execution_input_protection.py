"""OS-enforced immutability for files executed by a child verifier."""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path

PROTECTION = "windows-share-lock/v1"


class ExecutionInputProtectionUnavailable(RuntimeError):
    """The host cannot establish the execution-input invariant."""


@contextmanager
def protect_execution_inputs(paths: list[Path]):
    """Deny child write/delete opens while allowing source reads.

    Windows share modes are enforced by the kernel and cannot be bypassed by a
    child that restores bytes before the parent post-check. Other hosts are an
    honest null until they have an equivalent enforced implementation.
    """
    if os.name != "nt":
        raise ExecutionInputProtectionUnavailable(
            "this host has no OS-enforced child-unmodifiable execution store")
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle; close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL; handles = []
    try:
        for path in paths:
            handle = create(str(path.resolve(strict=True)), 0x80000000, 0x1,
                None, 3, 0x80, None)
            if handle in (None, ctypes.c_void_p(-1).value):
                error = ctypes.get_last_error()
                raise ExecutionInputProtectionUnavailable(
                    f"cannot lock prepared input (windows error {error})")
            handles.append(handle)
        yield PROTECTION
    finally:
        for handle in reversed(handles): close(handle)
