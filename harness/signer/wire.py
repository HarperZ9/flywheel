"""wire.py -- length-prefixed JSON frames, the only thing either side parses.

A frame is a 4-byte big-endian length then that many bytes of UTF-8 JSON. The
cap keeps a hostile caller from making the signer allocate without bound. No
pickle, no code, no paths: the signer reads a small JSON object and nothing
else.
"""
from __future__ import annotations

import json
import struct

MAX_FRAME = 65536


class WireError(RuntimeError):
    """A frame was malformed, oversized or cut short."""


def encode(obj: dict) -> bytes:
    data = json.dumps(obj, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if len(data) > MAX_FRAME:
        raise WireError("frame too large")
    return struct.pack(">I", len(data)) + data


def read_exact(read, n: int) -> bytes:
    """Call ``read(k)`` until n bytes arrive. ``read`` returns b"" at EOF."""
    buf = b""
    while len(buf) < n:
        chunk = read(n - len(buf))
        if not chunk:
            raise WireError("connection closed mid-frame")
        buf += chunk
    return buf


def decode_from(read) -> dict:
    (size,) = struct.unpack(">I", read_exact(read, 4))
    if size > MAX_FRAME:
        raise WireError("frame too large")
    try:
        obj = json.loads(read_exact(read, size).decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise WireError(f"frame is not JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise WireError("frame is not an object")
    return obj
