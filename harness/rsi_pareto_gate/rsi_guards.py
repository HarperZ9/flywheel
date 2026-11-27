# SPDX-License-Identifier: MIT
"""Low-level fail-closed primitive guards for RSI Pareto and WASM 100-pack manifests."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
WASM_MAGIC = b"\x00asm"

DEFAULT_MAX_3WAY_ERR = 1e-10
DEFAULT_REQUIRED_WASM_MODULES = 100
DEFAULT_MIN_ZERO_IMPORT_WASM = 16
DEFAULT_MAX_WASM_PACK_BYTES = 1_310_720  # 1.25 MiB ceiling


class RsiGateError(ValueError):
    """Raised when an RSI Pareto report or WASM pack manifest fails parsing."""


def load_json_object(path: Path, label: str) -> dict[str, Any]:
    """Load a UTF-8 JSON object from disk, rejecting non-dict payloads."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RsiGateError(f"{label}: unreadable JSON ({exc})") from exc
    if not isinstance(raw, dict):
        raise RsiGateError(f"{label}: expected JSON object")
    return raw


def require_dict(obj: dict[str, Any], key: str, label: str) -> dict[str, Any]:
    """Return a nested dict field or raise RsiGateError."""
    val = obj.get(key)
    if not isinstance(val, dict):
        raise RsiGateError(f"{label}: missing or non-object field '{key}'")
    return val


def require_list(obj: dict[str, Any], key: str, label: str) -> list[Any]:
    """Return a non-empty list field or raise RsiGateError."""
    val = obj.get(key)
    if not isinstance(val, list) or not val:
        raise RsiGateError(f"{label}: missing or empty list field '{key}'")
    return val


def require_str(obj: dict[str, Any], key: str, label: str) -> str:
    """Return a non-empty string field or raise RsiGateError."""
    val = obj.get(key)
    if not isinstance(val, str) or not val.strip():
        raise RsiGateError(f"{label}: missing or empty string '{key}'")
    return val


def require_bool(obj: dict[str, Any], key: str, label: str) -> bool:
    """Return a strict bool field or raise RsiGateError."""
    val = obj.get(key)
    if not isinstance(val, bool):
        raise RsiGateError(f"{label}: field '{key}' must be boolean")
    return val


def require_int(
    obj: dict[str, Any],
    key: str,
    label: str,
    *,
    minimum: int = 0,
) -> int:
    """Return a strict non-bool int >= minimum or raise RsiGateError."""
    val = obj.get(key)
    if isinstance(val, bool) or not isinstance(val, int):
        raise RsiGateError(f"{label}: field '{key}' must be integer")
    if val < minimum:
        raise RsiGateError(f"{label}: field '{key}' ({val}) < {minimum}")
    return val


def require_finite_float(obj: dict[str, Any], key: str, label: str) -> float:
    """Return a strict non-bool finite float or raise RsiGateError."""
    val = obj.get(key)
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise RsiGateError(f"{label}: field '{key}' must be numeric")
    fval = float(val)
    if not math.isfinite(fval):
        raise RsiGateError(f"{label}: field '{key}' must be finite")
    return fval


def require_sha256(obj: dict[str, Any], key: str, label: str) -> str:
    """Return a 64-character lowercase hex SHA-256 string."""
    val = require_str(obj, key, label)
    if not SHA256_RE.match(val):
        raise RsiGateError(f"{label}: invalid SHA-256 '{key}': {val!r}")
    return val


def validate_relative_wasm_path(raw_path: str, label: str) -> Path:
    """Reject traversal, absolute paths, drive letters, and non-.wasm files."""
    norm = raw_path.replace("\\", "/")
    if norm.startswith("/") or ":" in norm:
        raise RsiGateError(f"{label}: wasm_path must be relative: {raw_path!r}")
    parts = [p for p in norm.split("/") if p]
    if not parts or any(p in (".", "..") for p in parts):
        raise RsiGateError(f"{label}: unsafe relative wasm_path: {raw_path!r}")
    if not norm.endswith(".wasm"):
        raise RsiGateError(f"{label}: wasm_path must end with .wasm: {raw_path!r}")
    return Path(*parts)


def verify_wasm_file_on_disk(
    pack_root: Path,
    rel_path: Path,
    expected_bytes: int,
    expected_sha256: str,
) -> str | None:
    """Verify an on-disk WASM module exists, has WASM magic, size, and SHA-256."""
    root_resolved = pack_root.resolve()
    target = (root_resolved / rel_path).resolve()
    try:
        target.relative_to(root_resolved)
    except ValueError:
        return f"wasm path escapes pack_root: {rel_path.as_posix()}"
    if not target.is_file():
        return f"missing wasm file on disk: {rel_path.as_posix()}"
    data = target.read_bytes()
    if len(data) != expected_bytes:
        return (
            f"size mismatch for {rel_path.as_posix()}: {len(data)} != {expected_bytes}"
        )
    if not data.startswith(WASM_MAGIC):
        return f"invalid WASM magic header in {rel_path.as_posix()}"
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected_sha256:
        return f"sha256 mismatch for {rel_path.as_posix()}"
    return None
