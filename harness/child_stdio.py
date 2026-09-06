"""child_stdio.py -- start a protocol server on a pipe and keep its error stream.

Two clients in this tree drive a subprocess that speaks a JSON-RPC dialect over
stdio: the ACP client and the LSP client. What they share is not the protocol,
it is the launch. An environment cut down to what a child actually needs, an
unbuffered pipe in both directions, and a thread reading stderr, because a
server logging into a pipe nobody drains blocks on a full buffer and the symptom
is indistinguishable from a hang.

The stderr text is kept because it is usually the only place a failure explains
itself. A language server that cannot find its configuration says so on stderr
and then answers requests with nulls, which reads on the protocol side as a
server with nothing to say.
"""
from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path
from typing import Sequence

#: How much of a child's error stream is worth keeping. A server in a loop can
#: write megabytes, and the useful part is the start of it.
STDERR_LIMIT = 1 << 16

#: What a child process inherits. Everything else is dropped, so a key or token
#: sitting in this process's environment does not travel into a subprocess that
#: was never meant to read it.
KEEP = frozenset({
    "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "PATH", "TEMP", "TMP",
    "CODEX_HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "PROGRAMDATA",
    "HOME", "LANG", "LC_ALL",
})

__all__ = ["KEEP", "STDERR_LIMIT", "child_env", "drain", "settled", "spawn",
           "text_of"]


def child_env() -> dict[str, str]:
    """The allowlisted environment a child is started under."""
    return {key: value for key, value in os.environ.items()
            if key.upper() in KEEP}


def drain(stream, into: list[bytes], limit: int = STDERR_LIMIT) -> None:
    """Read a stream to its end, keeping the first `limit` bytes of it."""
    held = 0
    try:
        for chunk in iter(lambda: stream.read(4096), b""):
            if held < limit:
                into.append(chunk[:limit - held])
                held += len(chunk)
    except (OSError, ValueError):
        return


def text_of(chunks: list[bytes]) -> str:
    """What the child wrote, as text, with undecodable bytes left visible."""
    return b"".join(chunks).decode("utf-8", "replace")


def spawn(argv: Sequence[str], cwd: Path | str, *,
          env: dict[str, str] | None = None,
          name: str = "child") -> tuple[subprocess.Popen, list[bytes]]:
    """Start a stdio protocol server. Returns the process and its stderr buffer.

    bufsize=0 because framing counts bytes: a buffered writer can hold a header
    while the body goes out, and the far side is then reading a message whose
    length it has not been told yet.
    """
    directory = Path(cwd).resolve()
    if not directory.is_dir():
        raise NotADirectoryError(f"working directory does not exist: {directory}")
    process = subprocess.Popen(
        list(argv), cwd=str(directory), stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=env if env is not None else child_env(), bufsize=0)
    collected: list[bytes] = []
    reader = threading.Thread(target=drain, args=(process.stderr, collected),
                              name=f"{name}-stderr", daemon=True)
    reader.start()
    process.stderr_reader = reader     # so a caller can wait for the last of it
    return process, collected


def settled(process, timeout: float = 2.0) -> None:
    """Wait for the thread reading the child's error stream to reach the end.

    A child that died a moment ago has usually not been read to the end yet, and
    a caller reading the buffer right then sees nothing and reports that the
    server explained nothing. That is the one thing a server which wrote its
    reason to stderr and quit did not do.
    """
    reader = getattr(process, "stderr_reader", None)
    if reader is not None:
        reader.join(timeout)
