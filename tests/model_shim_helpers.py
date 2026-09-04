"""Shared helpers for the model_shim test files (test_model_shim.py holds the
wire-protocol and CLI falsifiers, test_model_receipts.py the boundary-receipt
falsifiers). Subprocess spawn/teardown and the client-side wire-contract
primitives both files exercise."""
from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path

from harness.oracle import spawn_killable

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "model-receipt-golden.json"


def spawn_shim(*extra_args: str) -> subprocess.Popen:
    cmd = [sys.executable, "-m", "harness.model_shim", "--port", "0", *extra_args]
    return spawn_killable(cmd, cwd=str(REPO_ROOT), stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, bufsize=1)


def cleanup(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        try:
            proc.kill()
        except Exception:
            pass
    try:
        proc.wait(timeout=5)
    except Exception:
        pass


def read_bound_port(proc: subprocess.Popen) -> int:
    line = proc.stdout.readline()
    assert line, f"shim produced no port line; stderr={proc.stderr.read()!r}"
    return int(line.strip())


def read_to_close(sock: socket.socket) -> bytes:
    data = bytearray()
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            return bytes(data)
        data += chunk


def trim_trailing_newline(data: bytes) -> str:
    """Mirror the client-side trim the wire contract specifies: exactly one
    trailing \n, and a \r immediately before it, if present."""
    if data.endswith(b"\n"):
        data = data[:-1]
    if data.endswith(b"\r"):
        data = data[:-1]
    return data.decode("utf-8")
