"""Read one hook delivery from standard input.

Hook clients send UTF-8 JSON. The process's own stdin is read as bytes and
decoded as UTF-8, whatever the locale's encoding is, because a Windows console
locale such as cp1252 would otherwise misread every non-ASCII character. A
test or a caller can inject a text stream instead.
"""
from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from .client_capture_payload import CaptureInputError


def _stdin_text(stdin: TextIO | None, max_chars: int) -> str:
    """At most `max_chars + 1` characters of input. The process's own stdin is
    read as bytes and decoded as UTF-8, since hook clients send UTF-8 JSON and
    a Windows console locale would otherwise misread it."""
    if stdin is not None:
        return stdin.read(max_chars + 1)
    buffer = getattr(sys.stdin, "buffer", None)
    if buffer is None:
        return sys.stdin.read(max_chars + 1)
    raw = buffer.read(4 * (max_chars + 1))
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        if len(raw) >= 4 * (max_chars + 1):
            raise CaptureInputError(f"hook stdin exceeds stdin limit of {max_chars} chars") \
                from exc
        raise CaptureInputError("hook stdin is not valid UTF-8") from exc


def read_hook(stdin: TextIO | None, max_chars: int) -> dict[str, Any]:
    raw = _stdin_text(stdin, max_chars)
    if len(raw) > max_chars:
        raise CaptureInputError(f"hook stdin exceeds stdin limit of {max_chars} chars")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise json.JSONDecodeError("malformed stdin JSON", exc.doc, exc.pos) from exc
    if not isinstance(data, dict):
        raise CaptureInputError("hook stdin JSON must be an object")
    return data
