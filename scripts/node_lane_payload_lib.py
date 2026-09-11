"""Shared helpers for build-only Node lane payload packaging."""
from __future__ import annotations

import base64
import fnmatch
import hashlib
import json
import os
import shutil
import stat
import tarfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]


class PayloadError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PayloadError(f"line {number}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise PayloadError(f"line {number}: row is not an object")
        rows.append(row)
    return rows


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PayloadError(message)


def reject_c_drive_source(path: Path | str) -> None:
    raw = str(path).replace("\\", "/")
    drive = Path(path).drive.upper()
    if drive == "C:" or raw.upper().startswith("C:/"):
        raise PayloadError("C: source roots are not allowed")


def is_reparse_point(path: Path) -> bool:
    try:
        attrs = path.stat(follow_symlinks=False).st_file_attributes
    except AttributeError:
        return path.is_symlink()
    return bool(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def safe_member_path(name: str, strip_prefix: str | None = None) -> Path:
    pure = PurePosixPath(name.replace("\\", "/"))
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise PayloadError(f"unsafe archive path: {name}")
    parts = pure.parts
    if strip_prefix:
        prefix = strip_prefix.rstrip("/")
        if parts and parts[0] == prefix:
            parts = parts[1:]
        else:
            raise PayloadError(f"archive path missing {strip_prefix!r} prefix: {name}")
    if not parts:
        raise PayloadError(f"empty archive path after prefix strip: {name}")
    return Path(*parts)


def assert_within(base: Path, target: Path) -> None:
    base_resolved = base.resolve()
    target_resolved = target.resolve(strict=False)
    if not target_resolved.is_relative_to(base_resolved):
        raise PayloadError(f"unsafe archive path escapes destination: {target}")


def safe_extract_tar(archive: Path, dest: Path, *, strip_prefix: str | None = None) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:*") as tf:
        for member in tf.getmembers():
            if member.isdir():
                continue
            if not member.isfile():
                raise PayloadError(f"unsafe archive member type: {member.name}")
            rel = safe_member_path(member.name, strip_prefix=strip_prefix)
            target = dest / rel
            assert_within(dest, target)
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tf.extractfile(member)
            if src is None:
                raise PayloadError(f"archive member has no bytes: {member.name}")
            with target.open("wb") as out:
                shutil.copyfileobj(src, out)


def safe_extract_zip(archive: Path, dest: Path, *, strip_prefix: str | None = None) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            rel = safe_member_path(info.filename, strip_prefix=strip_prefix)
            target = dest / rel
            assert_within(dest, target)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as out:
                shutil.copyfileobj(src, out)


def iter_selected_files(source: Path, include_paths: Iterable[str], exclude_patterns: Iterable[str] = ()) -> list[Path]:
    files: list[Path] = []
    for raw in include_paths:
        path = source / raw
        if not path.exists():
            raise PayloadError(f"selected source path missing: {raw}")
        if is_reparse_point(path):
            raise PayloadError(f"selected source path is a reparse point: {raw}")
        if path.is_file():
            files.append(path)
            continue
        for child in sorted(path.rglob("*")):
            if child.is_dir():
                continue
            if is_reparse_point(child):
                rel = child.relative_to(source).as_posix()
                raise PayloadError(f"selected source file is a reparse point: {rel}")
            files.append(child)
    excluded = set(exclude_patterns)
    selected = []
    for file_path in sorted(set(files), key=lambda p: p.relative_to(source).as_posix()):
        rel = file_path.relative_to(source).as_posix()
        if any(fnmatch.fnmatch(rel, pattern) for pattern in excluded):
            continue
        selected.append(file_path)
    return selected


def write_source_archive(source: Path, include_paths: Iterable[str], archive: Path, exclude_patterns: Iterable[str] = ()) -> str:
    reject_c_drive_source(source)
    files = iter_selected_files(source, include_paths, exclude_patterns)
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "w") as tf:
        for file_path in files:
            rel = file_path.relative_to(source).as_posix()
            data = file_path.read_bytes()
            info = tarfile.TarInfo(f"package/{rel}")
            info.size = len(data)
            info.mtime = 0
            info.mode = 0o644
            tf.addfile(info, fileobj=__import__("io").BytesIO(data))
    return sha256_file(archive)


def file_manifest(root: Path) -> dict[str, Any]:
    files = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if is_reparse_point(path):
            rel = path.relative_to(root).as_posix()
            raise PayloadError(f"payload file is a reparse point: {rel}")
        rel = path.relative_to(root).as_posix()
        files.append({"path": rel, "bytes": path.stat().st_size, "sha256": "sha256:" + sha256_file(path)})
    return {
        "algorithm": "sha256-canonical-source-manifest/v1",
        "file_count": len(files),
        "bytes": sum(item["bytes"] for item in files),
        "files": files,
        "manifest_sha256": "sha256:" + canonical_sha256(files),
    }


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as response, dest.open("wb") as fh:
        shutil.copyfileobj(response, fh)


def verify_integrity(data: bytes, integrity: str) -> None:
    algorithm, encoded = integrity.split("-", 1)
    if algorithm != "sha512":
        raise PayloadError(f"unsupported integrity algorithm: {algorithm}")
    actual = base64.b64encode(hashlib.sha512(data).digest()).decode("ascii")
    if actual != encoded:
        raise PayloadError("npm integrity mismatch")


def minimal_env() -> dict[str, str]:
    keep = {}
    for key in ("SystemRoot", "WINDIR", "TEMP", "TMP", "COMSPEC"):
        value = os.environ.get(key)
        if value:
            keep[key] = value
    return keep
