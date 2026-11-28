# SPDX-License-Identifier: MIT
"""Low-level fail-closed primitive and ISA binary guards for threshold_storage_attest."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

HEX_64_RE = re.compile(r"^[0-9a-f]{64}$")
PREFIXED_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

REQUIRED_ISAS = frozenset({"x64-pe", "x64-elf", "rv64-elf", "aarch64-elf", "wasm"})
ISA_MAGIC: dict[str, bytes] = {
    "x64-pe": b"MZ",
    "x64-elf": b"\x7fELF",
    "rv64-elf": b"\x7fELF",
    "aarch64-elf": b"\x7fELF",
    "wasm": b"\x00asm",
}


class StorageAttestError(ValueError):
    """Raised when a threshold HSM or RAID-6 receipt payload is malformed."""


def load_json_object(path: Path, label: str) -> dict[str, Any]:
    """Load a UTF-8 JSON object from disk, rejecting non-dict payloads."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StorageAttestError(f"{label}: unreadable JSON ({exc})") from exc
    if not isinstance(raw, dict):
        raise StorageAttestError(f"{label}: expected JSON object")
    return raw


def require_dict(obj: dict[str, Any], key: str, label: str) -> dict[str, Any]:
    """Return a nested dict field or raise StorageAttestError."""
    val = obj.get(key)
    if not isinstance(val, dict):
        raise StorageAttestError(f"{label}: missing or non-object field '{key}'")
    return val


def require_list(obj: dict[str, Any], key: str, label: str) -> list[Any]:
    """Return a non-empty list field or raise StorageAttestError."""
    val = obj.get(key)
    if not isinstance(val, list) or not val:
        raise StorageAttestError(f"{label}: missing or empty list '{key}'")
    return val


def require_str(obj: dict[str, Any], key: str, label: str) -> str:
    """Return a non-empty string field or raise StorageAttestError."""
    val = obj.get(key)
    if not isinstance(val, str) or not val.strip():
        raise StorageAttestError(f"{label}: missing or empty string '{key}'")
    return val


def require_int(obj: dict[str, Any], key: str, label: str, *, minimum: int = 0) -> int:
    """Return a strict non-bool int >= minimum or raise StorageAttestError."""
    val = obj.get(key)
    if isinstance(val, bool) or not isinstance(val, int):
        raise StorageAttestError(f"{label}: field '{key}' must be integer")
    if val < minimum:
        raise StorageAttestError(f"{label}: field '{key}' ({val}) < {minimum}")
    return val


def require_prefixed_sha256(obj: dict[str, Any], key: str, label: str) -> str:
    """Return a 'sha256:<64-hex>' digest string."""
    val = require_str(obj, key, label)
    if not PREFIXED_SHA256_RE.match(val):
        raise StorageAttestError(f"{label}: invalid prefixed sha256 '{key}'")
    return val


def classify_isa_relpath(rel_path: str) -> str | None:
    """Map an artifact relative path suffix to one of the 5 Zero-C target ISAs."""
    norm = rel_path.replace("\\", "/")
    if norm.endswith(".exe"):
        return "x64-pe"
    if norm.endswith(".x64.elf"):
        return "x64-elf"
    if norm.endswith(".rv64.elf"):
        return "rv64-elf"
    if norm.endswith(".aarch64.elf"):
        return "aarch64-elf"
    if norm.endswith(".wasm"):
        return "wasm"
    return None


def validate_safe_relpath(rel_path: str, label: str) -> Path:
    """Reject traversal, absolute paths, and drive-qualified paths."""
    norm = rel_path.replace("\\", "/")
    if norm.startswith("/") or ":" in norm:
        raise StorageAttestError(f"{label}: unsafe artifact path {rel_path!r}")
    parts = [p for p in norm.split("/") if p]
    if not parts or any(p in (".", "..") for p in parts):
        raise StorageAttestError(f"{label}: traversal in artifact path {rel_path!r}")
    return Path(*parts)


def verify_isa_binary_on_disk(
    root: Path,
    rel_path: str,
    isa: str,
    expected_bytes: int,
    expected_sha256: str,
) -> str | None:
    """Verify an on-disk Zero-C ISA binary for existence, magic bytes, size, and SHA-256."""
    safe_rel = validate_safe_relpath(rel_path, isa)
    root_res = root.resolve()
    target = (root_res / safe_rel).resolve()
    try:
        target.relative_to(root_res)
    except ValueError:
        return f"{isa}: path escapes root ({rel_path})"
    if not target.is_file():
        return f"{isa}: missing binary on disk ({rel_path})"
    data = target.read_bytes()
    if len(data) != expected_bytes:
        return f"{isa}: size mismatch ({len(data)} != {expected_bytes})"
    magic = ISA_MAGIC[isa]
    if not data.startswith(magic):
        return f"{isa}: invalid binary magic header"
    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    if digest != expected_sha256:
        return f"{isa}: sha256 mismatch on disk"
    return None
