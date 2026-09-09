"""Shared helpers for desktop font provenance and payload checks."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import struct
from pathlib import Path

PAYLOAD_SCHEMA = "flywheel.desktop-font-payload/v1"
FONT_SUFFIXES = {".ttf", ".otf", ".ttc", ".woff", ".woff2"}


def _refuse(message: str) -> None:
    raise ValueError(message)


def _read_json(path: Path) -> dict:
    if not path.is_file():
        _refuse(f"missing {path.name}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        _refuse(f"{path.name} is not a JSON object")
    return value


def _load_release_manifest_module():
    path = Path(__file__).with_name("release_manifest.py")
    spec = importlib.util.spec_from_file_location("flywheel_release_manifest", path)
    if spec is None or spec.loader is None:
        _refuse("release manifest helper is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_RELEASE_MANIFEST = _load_release_manifest_module()
_POLICY_KEYS = _RELEASE_MANIFEST._POLICY_KEYS
_RESERVED = _RELEASE_MANIFEST._RESERVED
_RESERVED_CHARS = _RELEASE_MANIFEST._RESERVED_CHARS


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _tables(raw: bytes) -> dict[str, tuple[int, int]]:
    if len(raw) < 12:
        _refuse("font file is too small to be an sfnt")
    out: dict[str, tuple[int, int]] = {}
    for index in range(struct.unpack(">H", raw[4:6])[0]):
        start = 12 + 16 * index
        tag, _, offset, length = struct.unpack(">4sLLL", raw[start:start + 16])
        out[tag.decode("ascii")] = (offset, length)
    return out


def name_values(raw: bytes) -> dict[int, set[str]]:
    tables = _tables(raw)
    if "name" not in tables:
        _refuse("font lacks a name table")
    offset, length = tables["name"]
    data = raw[offset:offset + length]
    _, count, strings = struct.unpack(">HHH", data[:6])
    out: dict[int, set[str]] = {}
    for index in range(count):
        row = data[6 + 12 * index:18 + 12 * index]
        platform, _, _, name_id, size, start = struct.unpack(">HHHHHH", row)
        blob = data[strings + start:strings + start + size]
        try:
            text = blob.decode("utf-16-be" if platform in (0, 3) else "latin1")
        except UnicodeDecodeError:
            continue
        out.setdefault(name_id, set()).add(text.replace("\x00", ""))
    return out


def os2_fields(raw: bytes) -> tuple[int, int]:
    tables = _tables(raw)
    if "OS/2" not in tables:
        _refuse("font lacks an OS/2 table")
    offset, _ = tables["OS/2"]
    return (
        struct.unpack(">H", raw[offset + 4:offset + 6])[0],
        struct.unpack(">H", raw[offset + 8:offset + 10])[0],
    )


def _fixed(blob: bytes) -> int:
    return int(round(struct.unpack(">l", blob)[0] / 65536))


def fvar_wght_axis(raw: bytes) -> dict[str, int] | None:
    tables = _tables(raw)
    if "fvar" not in tables:
        return None
    offset, length = tables["fvar"]
    data = raw[offset:offset + length]
    if len(data) < 16:
        _refuse("fvar table is truncated")
    axes_offset = struct.unpack(">H", data[4:6])[0]
    axis_count = struct.unpack(">H", data[8:10])[0]
    axis_size = struct.unpack(">H", data[10:12])[0]
    for index in range(axis_count):
        start = axes_offset + axis_size * index
        record = data[start:start + axis_size]
        if record[:4].decode("ascii") == "wght":
            return {"min": _fixed(record[4:8]), "default": _fixed(record[8:12]), "max": _fixed(record[12:16])}
    return None


def validate_relative_path(value: object, label: str, seen_lower: set[str] | None = None) -> None:
    if not isinstance(value, str):
        _refuse(f"{label} is not normalized relative")
    parts = value.split("/")
    if not value or value.startswith("/") or "\\" in value or ":" in parts[0] or any(part in ("", ".", "..") for part in parts):
        _refuse(f"{label} is not normalized relative: {value!r}")
    if any(token in value for token in ("*", "?", "[")):
        _refuse(f"{label} uses a glob: {value!r}")
    stems = [part.split(".")[0].lower() for part in parts]
    if any(stem in _RESERVED for stem in stems) or any(char in _RESERVED_CHARS for char in value):
        _refuse(f"{label} names a reserved or stream path: {value!r}")
    if seen_lower is not None:
        lowered = value.lower()
        if lowered in seen_lower:
            _refuse(f"case-colliding payload policy path: {value}")
        seen_lower.add(lowered)


def load_policy(desktop_root: str | Path) -> dict:
    policy = _read_json(Path(desktop_root) / "release" / "payload-policy.json")
    if policy.get("font_payload_schema") != PAYLOAD_SCHEMA:
        _refuse("payload policy does not bind the font payload schema")
    if policy.get("blocked") != []:
        _refuse("payload policy still carries blocking font facts")
    for key in _POLICY_KEYS:
        if key not in policy:
            _refuse(f"payload policy lacks {key}")
    for key in [k for k in _POLICY_KEYS if k.startswith("reject_")]:
        if policy.get(key) is not True:
            _refuse(f"payload policy must set {key}=true")
    for key in ("font_provenance", "third_party_notices"):
        value = str(policy.get(key, ""))
        if not value.startswith("accepted:") or value.upper() == "BLOCKED":
            _refuse(f"payload policy {key} is not accepted")
    allow = policy.get("allow")
    if not isinstance(allow, list) or not allow:
        _refuse("payload policy allowlist is empty")
    seen: set[str] = set()
    seen_lower: set[str] = set()
    for row in allow:
        path = row.get("path") if isinstance(row, dict) else None
        validate_relative_path(path, "payload policy allow path", seen_lower)
        if path in seen:
            _refuse(f"duplicate payload policy path: {path}")
        seen.add(path)
        if row.get("source_path") is not None:
            validate_relative_path(row.get("source_path"), "payload policy source path")
        if len(str(row.get("sha256", ""))) != 64:
            _refuse(f"allow row lacks an exact sha256: {path}")
        if not isinstance(row.get("size"), int):
            _refuse(f"allow row lacks an exact byte size: {path}")
        if row.get("license_id") != "OFL-1.1":
            _refuse(f"allow row is not OFL-1.1: {path}")
    return policy


def expected_policy_rows(policy: dict) -> dict[str, dict]:
    return {row["path"]: row for row in policy["allow"]}


def manifest_relative_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    if root.is_symlink() or root.is_junction():
        _refuse(f"a symlink or reparse point is staged: {root.name}")
    try:
        return _RELEASE_MANIFEST._staged_relative_files(root)
    except ValueError as exc:
        _refuse(str(exc))


def actual_source_font_assets(desktop_root: str | Path) -> list[str]:
    root = Path(desktop_root) / "assets" / "fonts"
    return sorted(
        "assets/fonts/" + path.as_posix()
        for path in manifest_relative_files(root)
        if path.suffix.lower() in FONT_SUFFIXES
    )
