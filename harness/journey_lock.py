"""Portable exclusive file locking for one durable Journey mutation."""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import time
from typing import Iterator


class JourneyLockBusy(RuntimeError):
    """The fixed failure raised when a Journey lock misses its deadline."""

    def __init__(self) -> None:
        super().__init__("STORE_BUSY")


def fsync_directory(path: Path) -> None:
    """Flush directory metadata on POSIX and Windows or fail closed."""
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = (
        ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
        ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
    )
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.FlushFileBuffers.argtypes = (ctypes.c_void_p,)
    kernel32.FlushFileBuffers.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    handle = kernel32.CreateFileW(str(path), 0x40000000, 7, None, 3, 0x02000000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not kernel32.FlushFileBuffers(handle):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel32.CloseHandle(handle)


def _try_lock(stream) -> bool:
    if os.name == "nt":
        import msvcrt
        try:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    import fcntl
    try:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except BlockingIOError:
        return False


def _unlock(stream) -> None:
    if os.name == "nt":
        import msvcrt
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl
    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class ExclusiveJourneyLock:
    """Cross-process advisory lock with a bounded acquisition deadline."""

    @staticmethod
    @contextmanager
    def acquire(lock_path: Path, timeout_s: float = 2.0) -> Iterator[None]:
        if timeout_s < 0:
            raise ValueError("timeout_s must not be negative")
        path = Path(lock_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as stream:
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"\0")
                stream.flush()
                os.fsync(stream.fileno())
            deadline = time.monotonic() + timeout_s
            while not _try_lock(stream):
                if time.monotonic() >= deadline:
                    raise JourneyLockBusy()
                time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))
            try:
                yield
            finally:
                _unlock(stream)
