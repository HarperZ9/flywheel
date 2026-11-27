"""Canonical JSON and fingerprints (SPEC.md section 0.1).

The prototype implements the subset of RFC 8785 it needs: objects with
string keys, arrays, strings, integers, booleans and null. Keys sort by
code point, which equals RFC 8785's UTF-16 order for the ASCII keys the
protocol uses. Floats are refused, so no number formatting question arises.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


class CanonError(ValueError):
    """A value or byte string is not canonical under the prototype's rules."""


def _check(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (bool, str)):
        return
    if isinstance(value, int):
        if abs(value) > 2**53 - 1:
            raise CanonError(f"{path}: integer outside the I-JSON range")
        return
    if isinstance(value, float):
        raise CanonError(f"{path}: floats are not allowed in signed messages")
    if isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            _check(item, f"{path}[{i}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonError(f"{path}: non-string key")
            _check(item, f"{path}.{key}")
        return
    raise CanonError(f"{path}: type {type(value).__name__} is not allowed")


def canon(value: Any) -> bytes:
    """Canonical bytes of a JSON value."""
    _check(value)
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return text.encode("utf-8")


def parse_canonical(data: bytes) -> Any:
    """Parse bytes and refuse them unless they are already canonical (check 1)."""
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CanonError(f"does not parse: {exc}") from exc
    if canon(value) != data:
        raise CanonError("bytes are not in canonical form")
    return value


def tag(msg_type: str) -> bytes:
    """Domain tag: fsp/v0/<type> and one newline byte."""
    return f"fsp/v0/{msg_type}\n".encode("ascii")


def fingerprint(msg_type: str, value: Any) -> str:
    """SHA-256 over the domain tag and the canonical bytes, as hex."""
    return hashlib.sha256(tag(msg_type) + canon(value)).hexdigest()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
