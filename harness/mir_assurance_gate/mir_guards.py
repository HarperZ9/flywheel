# SPDX-License-Identifier: MIT
"""Low-level fail-closed primitive guards for MIR assurance manifests."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

HEX_40_RE = re.compile(r"^[0-9a-f]{40}$")
HEX_PREFIX_RE = re.compile(r"^[0-9a-f]{8,64}$")

REQUIRED_DENIED_EFFECTS = frozenset({"fs", "net", "exec", "unsafe"})
DEFAULT_RV64_FRAME_CEILING = 2048
DEFAULT_RV64_PAGE_BUDGET = 4096
DEFAULT_MIN_FILES = 5
DEFAULT_MIN_INTEGRATION_TESTS = 4
DEFAULT_MIN_PLANTED_CONTROLS = 3


class MirGateError(ValueError):
    """Raised when a MIR assurance manifest is malformed or tampered."""


def load_json_object(path: Path, label: str) -> dict[str, Any]:
    """Load a UTF-8 JSON object from disk, rejecting non-dict payloads."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MirGateError(f"{label}: unreadable JSON ({exc})") from exc
    if not isinstance(raw, dict):
        raise MirGateError(f"{label}: expected JSON object")
    return raw


def require_dict(obj: dict[str, Any], key: str, label: str) -> dict[str, Any]:
    """Return a nested dict field or raise MirGateError."""
    val = obj.get(key)
    if not isinstance(val, dict):
        raise MirGateError(f"{label}: missing or non-object field '{key}'")
    return val


def require_list(obj: dict[str, Any], key: str, label: str) -> list[Any]:
    """Return a non-empty list field or raise MirGateError."""
    val = obj.get(key)
    if not isinstance(val, list) or not val:
        raise MirGateError(f"{label}: missing or empty list field '{key}'")
    return val


def require_str(obj: dict[str, Any], key: str, label: str) -> str:
    """Return a non-empty string field or raise MirGateError."""
    val = obj.get(key)
    if not isinstance(val, str) or not val.strip():
        raise MirGateError(f"{label}: missing or empty string '{key}'")
    return val


def require_bool(obj: dict[str, Any], key: str, label: str) -> bool:
    """Return a strict bool field or raise MirGateError."""
    val = obj.get(key)
    if not isinstance(val, bool):
        raise MirGateError(f"{label}: field '{key}' must be boolean")
    return val


def require_int(
    obj: dict[str, Any],
    key: str,
    label: str,
    *,
    minimum: int = 0,
) -> int:
    """Return a strict non-bool int >= minimum or raise MirGateError."""
    val = obj.get(key)
    if isinstance(val, bool) or not isinstance(val, int):
        raise MirGateError(f"{label}: field '{key}' must be integer")
    if val < minimum:
        raise MirGateError(f"{label}: field '{key}' ({val}) < {minimum}")
    return val


def require_hex_40(obj: dict[str, Any], key: str, label: str) -> str:
    """Return a 40-char lowercase hexadecimal commit SHA."""
    val = require_str(obj, key, label)
    if not HEX_40_RE.match(val):
        raise MirGateError(f"{label}: invalid 40-hex '{key}': {val!r}")
    return val


def require_hex_prefix(obj: dict[str, Any], key: str, label: str) -> str:
    """Return an 8-to-64 char lowercase hexadecimal digest prefix."""
    val = require_str(obj, key, label)
    if not HEX_PREFIX_RE.match(val):
        raise MirGateError(f"{label}: invalid hex prefix '{key}': {val!r}")
    return val


def require_str_tuple(
    obj: dict[str, Any],
    key: str,
    label: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    """Return a tuple of non-empty strings."""
    val = obj.get(key)
    if not isinstance(val, list):
        raise MirGateError(f"{label}: field '{key}' must be a list of strings")
    if not allow_empty and not val:
        raise MirGateError(f"{label}: field '{key}' must be non-empty")
    out: list[str] = []
    for item in val:
        if not isinstance(item, str) or not item.strip():
            raise MirGateError(f"{label}: invalid string entry in '{key}'")
        out.append(item)
    return tuple(out)
