"""Safe local file reads for cross-harness post-run validation."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


class DuplicateKey(ValueError):
    pass


def _pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in rows:
        if key in out:
            raise DuplicateKey(key)
        out[key] = value
    return out


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json_file(path: Path) -> tuple[dict[str, Any] | None, str]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_pairs)
    except FileNotFoundError:
        return None, "missing"
    except (OSError, UnicodeError, json.JSONDecodeError, DuplicateKey, TypeError):
        return None, "malformed"
    return (value, "") if isinstance(value, dict) else (None, "malformed")


def _is_link(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())


def _norm(path: Path) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(str(path))))


def _inside(root: Path, candidate: Path) -> bool:
    try:
        return os.path.commonpath((_norm(root), _norm(candidate))) == _norm(root)
    except ValueError:
        return False


def _lexical_parts(root: Path, candidate: Path) -> list[str] | None:
    if not _inside(root, candidate):
        return None
    rel = os.path.relpath(_norm(candidate), _norm(root))
    return [] if rel == "." else list(Path(rel).parts)


def _has_link_component(root: Path, candidate: Path) -> bool:
    if _is_link(root):
        return True
    parts = _lexical_parts(root, candidate)
    if parts is None:
        return False
    cursor = root
    for part in parts:
        cursor = cursor / part
        if cursor.exists() and _is_link(cursor):
            return True
    return False


def _has_submitted_link_component(candidate: Path) -> bool:
    parts = candidate.parts
    if not parts:
        return False
    cursor = Path(parts[0])
    for part in parts[1:]:
        if part in {"", "."}:
            continue
        cursor = cursor / part
        try:
            if _is_link(cursor):
                return True
        except OSError:
            return False
    return False


def safe_run_root(value: str | os.PathLike[str]) -> tuple[Path | None, str]:
    if not isinstance(value, (str, os.PathLike)) or not str(value):
        return None, "run_root_missing"
    raw = Path(value)
    candidate = raw if raw.is_absolute() else Path.cwd() / raw
    if _has_submitted_link_component(candidate):
        return None, "linked_run_root"
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        return None, "run_root_missing"
    if not resolved.is_dir():
        return None, "run_root_missing"
    return resolved, ""


def safe_existing_path(root: Path, value: str, *, kind: str = "file") -> tuple[Path | None, str]:
    if not isinstance(value, str) or not value:
        return None, "path_missing"
    base = Path(root).resolve(strict=True)
    raw = Path(value)
    candidate = raw if raw.is_absolute() else base / raw
    if _has_submitted_link_component(candidate):
        return None, "linked_artifact_path"
    candidate = Path(os.path.abspath(str(candidate)))
    if not _inside(base, candidate):
        return None, "path_outside"
    if _has_link_component(base, candidate):
        return None, "linked_artifact_path"
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        return None, "path_missing"
    if not _inside(base, resolved):
        return None, "path_outside"
    if kind == "file" and not resolved.is_file():
        return None, "path_outside"
    if kind == "dir" and not resolved.is_dir():
        return None, "path_outside"
    return resolved, ""


def safe_read_json(root: Path, value: str) -> tuple[dict[str, Any] | None, str, Path | None]:
    path, error = safe_existing_path(root, value, kind="file")
    if error:
        return None, error, None
    data, read_error = read_json_file(path)
    return data, read_error, path
