"""A bounded tail of what an MCP server wrote to stderr.

A server that dies on launch says why on stderr; discarding it turns a
one-line ModuleNotFoundError into a bare "closed the connection". The stdio
transport keeps the last lines here for its own error reports. The tail is
only ever handed to code that already decided to show it; the lane console
does not (fixed error codes, O-7).
"""
from __future__ import annotations

import collections
import threading
from typing import IO

TAIL_LINES = 30


class StderrTail:
    """Read a pipe on a daemon thread and keep its last ``TAIL_LINES`` lines."""

    def __init__(self, stream: IO[str] | None, *, lines: int = TAIL_LINES) -> None:
        self._lines: "collections.deque[str]" = collections.deque(maxlen=lines)
        self._reader = threading.Thread(target=self._loop, args=(stream,), daemon=True)
        self._reader.start()

    def _loop(self, stream: IO[str] | None) -> None:
        if stream is None:
            return
        try:
            for line in stream:
                line = line.rstrip()
                if line:
                    self._lines.append(line)
        except (ValueError, OSError):
            pass

    def text(self, *, exited: bool) -> str:
        """The kept lines joined, or ''. After the process exits, the reader is
        joined briefly so the tail is complete."""
        if exited:
            self._reader.join(timeout=0.5)
        return "\n".join(self._lines).strip()
