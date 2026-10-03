"""Stream helpers for Codex session transports."""
from __future__ import annotations


class CodexStreamWriteError(OSError):
    pass


def write_all(stream, data: bytes) -> None:
    view = memoryview(data)
    offset = 0
    while offset < len(view):
        written = stream.write(view[offset:].tobytes())
        remaining = len(view) - offset
        if (not isinstance(written, int) or isinstance(written, bool)
                or written <= 0 or written > remaining):
            raise CodexStreamWriteError("invalid write result")
        offset += written
    stream.flush()


def close_stream(stream) -> None:
    close = getattr(stream, "close", None)
    if close is None:
        return
    try:
        close()
    except Exception:
        pass


def acquire_lock(lock, timeout: float | None) -> bool:
    if timeout is None:
        lock.acquire()
        return True
    return lock.acquire(timeout=max(0.0, timeout))
