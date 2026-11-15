from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import stat
import unicodedata
import zipfile
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path

from .canonical_json import canonical_json_bytes, sha256_bytes
from .path_policy import is_reparse_point, is_windows_ads_path

MANIFEST_SCHEMA = "canonpack.manifest/v1"
MANIFEST_NAME = "manifest.json"
_SUPPORTED = {zipfile.ZIP_STORED: "stored", zipfile.ZIP_DEFLATED: "deflated"}
_ENTRY_KEYS = frozenset({"path", "sha256", "size", "compressed_size", "compression", "kind"})
_MANIFEST_KEYS = frozenset({"schema", "entries"})
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_RESERVED = frozenset({"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))})
_CHUNK = 64 * 1024


class CanonpackError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        super().__init__(f"{code}: {detail}" if detail else code)

def _check_limit(name: str, value: object, *, positive: bool = False) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0 or (positive and value == 0):
        raise CanonpackError("invalid-limit", name)

@dataclass(frozen=True, slots=True)
class CanonpackLimits:
    max_entries: int = 2000; max_total_uncompressed: int = 50_000_000
    max_entry_uncompressed: int = 10_000_000; max_manifest_bytes: int = 1_000_000
    max_compression_ratio: int = 100

    def __post_init__(self) -> None:
        _check_limit("max_entries", self.max_entries, positive=True)
        _check_limit("max_compression_ratio", self.max_compression_ratio, positive=True)
        for name in ("max_total_uncompressed", "max_entry_uncompressed", "max_manifest_bytes"):
            _check_limit(name, getattr(self, name))

@dataclass(frozen=True, slots=True)
class CanonpackEntry:
    path: str; sha256: str; size: int
    compressed_size: int; compression: str; kind: str

@dataclass(frozen=True, slots=True)
class CanonpackPreflight:
    ok: bool; entries: tuple[CanonpackEntry, ...]
    manifest_sha256: str; reason_codes: tuple[str, ...]

def normalize_manifest_path(name: str) -> str:
    if not isinstance(name, str) or name == "":
        raise CanonpackError("invalid-path", "path must be a non-empty string")
    if "\0" in name or any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
        raise CanonpackError("invalid-path", name)
    if unicodedata.normalize("NFC", name) != name:
        raise CanonpackError("invalid-path", name)
    if "\\" in name or name.startswith(("/", "//")) or _DRIVE_RE.match(name):
        raise CanonpackError("invalid-path", name)
    if is_windows_ads_path(name) or ":" in name:
        raise CanonpackError("invalid-path", name)
    if posixpath.normpath(name) != name:
        raise CanonpackError("invalid-path", name)
    parts = name.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise CanonpackError("invalid-path", name)
    for part in parts:
        _reject_windows_alias(part, name)
    return name

def preflight_manifest(manifest: dict, *, limits: CanonpackLimits = CanonpackLimits()) -> CanonpackPreflight:
    _require_limits(limits)
    if not isinstance(manifest, dict) or set(manifest) != _MANIFEST_KEYS:
        raise CanonpackError("invalid-manifest")
    if manifest.get("schema") != MANIFEST_SCHEMA or not isinstance(manifest.get("entries"), list):
        raise CanonpackError("invalid-manifest")
    raw_entries = manifest["entries"]
    if len(raw_entries) > limits.max_entries:
        raise CanonpackError("entry-count")
    entries = tuple(sorted((_entry_from_json(item, limits) for item in raw_entries), key=lambda e: e.path))
    _check_manifest_totals(entries, limits)
    _check_duplicate_paths(entry.path for entry in entries)
    digest = sha256_bytes(canonical_json_bytes(_canonical_manifest(entries)))
    return CanonpackPreflight(True, entries, digest, ())

def preflight_zip(path: str | Path, *, limits: CanonpackLimits = CanonpackLimits()) -> CanonpackPreflight:
    _require_limits(limits)
    archive = _coerce_archive_path(path)
    if is_reparse_point(archive):
        raise CanonpackError("archive-reparse", os.fspath(path))
    try:
        with zipfile.ZipFile(archive) as zf:
            infos = _scan_central_directory(zf, limits)
            manifest_info = _one_manifest(infos)
            _check_manifest_info(manifest_info, limits)
            result = preflight_manifest(_read_manifest(zf, manifest_info), limits=limits)
            _compare_manifest_to_central(result.entries, infos)
            _verify_zip_payloads(zf, result.entries, infos)
            return result
    except CanonpackError:
        raise
    except (OSError, zipfile.BadZipFile, NotImplementedError) as exc:
        raise CanonpackError("invalid-zip", str(exc)) from exc

def _reject_windows_alias(part: str, full: str) -> None:
    if part.endswith((" ", ".")):
        raise CanonpackError("invalid-path", full)
    stem = part.split(".", 1)[0].casefold()
    if stem in _RESERVED:
        raise CanonpackError("invalid-path", full)

def _require_limits(limits: object) -> None:
    if not isinstance(limits, CanonpackLimits):
        raise CanonpackError("invalid-limit", "limits must be CanonpackLimits")

def _entry_from_json(raw: object, limits: CanonpackLimits) -> CanonpackEntry:
    if not isinstance(raw, dict) or set(raw) != _ENTRY_KEYS:
        raise CanonpackError("invalid-entry")
    path = normalize_manifest_path(raw["path"])
    size = _non_negative_int(raw["size"], "entry-size")
    compressed_size = _non_negative_int(raw["compressed_size"], "compressed-size")
    if size > limits.max_entry_uncompressed:
        raise CanonpackError("entry-size", path)
    if not isinstance(raw["sha256"], str) or _SHA256_RE.fullmatch(raw["sha256"]) is None:
        raise CanonpackError("sha256", path)
    if raw["compression"] not in ("stored", "deflated"):
        raise CanonpackError("unsupported-compression", path)
    _check_ratio(size, compressed_size, limits, path)
    if raw["compression"] == "stored" and size != compressed_size:
        raise CanonpackError("metadata-mismatch", path)
    if not isinstance(raw["kind"], str) or raw["kind"] == "" or _has_control(raw["kind"]):
        raise CanonpackError("invalid-entry", path)
    return CanonpackEntry(path, raw["sha256"], size, compressed_size, raw["compression"], raw["kind"])

def _non_negative_int(value: object, code: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise CanonpackError(code)
    return value

def _has_control(value: str) -> bool:
    return any(ord(ch) < 32 or ord(ch) == 127 for ch in value)

def _check_ratio(size: int, compressed_size: int, limits: CanonpackLimits, label: str) -> None:
    if compressed_size == 0:
        if size:
            raise CanonpackError("compression-ratio", label)
        return
    if size > compressed_size * limits.max_compression_ratio:
        raise CanonpackError("compression-ratio", label)

def _check_manifest_totals(entries: tuple[CanonpackEntry, ...], limits: CanonpackLimits) -> None:
    total_size = sum(entry.size for entry in entries)
    total_compressed = sum(entry.compressed_size for entry in entries)
    if total_size > limits.max_total_uncompressed:
        raise CanonpackError("total-size")
    _check_ratio(total_size, total_compressed, limits, "manifest-total")

def _check_duplicate_paths(paths: object) -> None:
    seen: set[str] = set()
    for path in paths:
        key = unicodedata.normalize("NFC", path.casefold())
        if key in seen:
            raise CanonpackError("duplicate-path", path)
        seen.add(key)

def _canonical_manifest(entries: tuple[CanonpackEntry, ...]) -> dict:
    return {"schema": MANIFEST_SCHEMA, "entries": [_entry_dict(entry) for entry in entries]}

def _entry_dict(entry: CanonpackEntry) -> dict:
    return {
        "path": entry.path, "sha256": entry.sha256, "size": entry.size,
        "compressed_size": entry.compressed_size, "compression": entry.compression,
        "kind": entry.kind,
    }

def _coerce_archive_path(path: str | Path) -> Path:
    try:
        raw = os.fspath(path)
    except TypeError as exc:
        raise CanonpackError("invalid-archive-path", type(path).__name__) from exc
    if not isinstance(raw, str) or "\0" in raw:
        raise CanonpackError("invalid-archive-path")
    if is_windows_ads_path(raw):
        raise CanonpackError("archive-ads")
    return Path(raw)

def _scan_central_directory(zf: zipfile.ZipFile, limits: CanonpackLimits) -> dict[str, zipfile.ZipInfo]:
    infos: dict[str, zipfile.ZipInfo] = {}
    seen: set[str] = set()
    for info in zf.infolist():
        name = normalize_manifest_path(info.filename)
        _check_central_info(info, name, limits)
        if name == MANIFEST_NAME and MANIFEST_NAME in infos:
            raise CanonpackError("multiple-manifest")
        key = name.casefold()
        if key in seen:
            raise CanonpackError("duplicate-path", name)
        seen.add(key)
        infos[name] = info
    data = tuple(info for name, info in infos.items() if name != MANIFEST_NAME)
    if len(data) > limits.max_entries:
        raise CanonpackError("entry-count")
    total = sum(info.file_size for info in data)
    compressed = sum(info.compress_size for info in data)
    if total > limits.max_total_uncompressed:
        raise CanonpackError("total-size")
    _check_ratio(total, compressed, limits, "archive-total")
    return infos

def _check_central_info(info: zipfile.ZipInfo, name: str, limits: CanonpackLimits) -> None:
    if info.flag_bits & 1:
        raise CanonpackError("encrypted-entry", name)
    if info.compress_type not in _SUPPORTED:
        raise CanonpackError("unsupported-compression", name)
    mode = info.external_attr >> 16
    if info.is_dir():
        raise CanonpackError("special-entry", name)
    if mode:
        file_type = stat.S_IFMT(mode)
        if stat.S_ISLNK(mode):
            raise CanonpackError("symlink-entry", name)
        if file_type and file_type != stat.S_IFREG:
            raise CanonpackError("special-entry", name)
    _check_ratio(info.file_size, info.compress_size, limits, name)
    if info.file_size > limits.max_entry_uncompressed and name != MANIFEST_NAME:
        raise CanonpackError("entry-size", name)

def _one_manifest(infos: dict[str, zipfile.ZipInfo]) -> zipfile.ZipInfo:
    if MANIFEST_NAME not in infos:
        raise CanonpackError("missing-manifest")
    return infos[MANIFEST_NAME]

def _check_manifest_info(info: zipfile.ZipInfo, limits: CanonpackLimits) -> None:
    if info.file_size > limits.max_manifest_bytes:
        raise CanonpackError("manifest-size")
    _check_ratio(info.file_size, info.compress_size, limits, MANIFEST_NAME)

def _read_manifest(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> dict:
    raw = _read_exact_member(zf, info, info.file_size, hash_payload=False)
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_json_object)
    except (UnicodeDecodeError, JSONDecodeError) as exc:
        raise CanonpackError("manifest-json", str(exc)) from exc

def _json_object(pairs: list[tuple[str, object]]) -> dict:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise CanonpackError("duplicate-json-key", key)
        result[key] = value
    return result

def _compare_manifest_to_central(entries: tuple[CanonpackEntry, ...], infos: dict[str, zipfile.ZipInfo]) -> None:
    manifest_paths = {entry.path for entry in entries}
    central_paths = {name for name in infos if name != MANIFEST_NAME}
    for path in sorted(central_paths - manifest_paths):
        raise CanonpackError("extra-member", path)
    for path in sorted(manifest_paths - central_paths):
        raise CanonpackError("missing-member", path)
    for entry in entries:
        info = infos[entry.path]
        if (entry.size, entry.compressed_size, entry.compression) != (info.file_size, info.compress_size, _SUPPORTED[info.compress_type]):
            raise CanonpackError("metadata-mismatch", entry.path)

def _verify_zip_payloads(zf: zipfile.ZipFile, entries: tuple[CanonpackEntry, ...], infos: dict[str, zipfile.ZipInfo]) -> None:
    for entry in entries:
        digest = _read_exact_member(zf, infos[entry.path], entry.size, hash_payload=True)
        if digest != entry.sha256:
            raise CanonpackError("digest-mismatch", entry.path)

def _read_exact_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo, expected: int, *, hash_payload: bool) -> bytes | str:
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    seen = 0
    with zf.open(info, "r") as fp:
        while seen <= expected:
            want = min(_CHUNK, expected - seen + 1)
            chunk = fp.read(want)
            if not chunk:
                break
            seen += len(chunk)
            if seen > expected:
                raise CanonpackError("size-mismatch", info.filename)
            digest.update(chunk)
            if not hash_payload:
                chunks.append(chunk)
    if seen != expected:
        raise CanonpackError("size-mismatch", info.filename)
    return "sha256:" + digest.hexdigest() if hash_payload else b"".join(chunks)
