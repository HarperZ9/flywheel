"""Fail-closed JSON parsing and artifact-reference admission for evidence."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path, PureWindowsPath


def _object_without_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _reject_nonfinite_number(token: str) -> object:
    raise ValueError(f"non-finite JSON number: {token}")


def _depth(value: object) -> int:
    if isinstance(value, dict):
        return 1 + max((_depth(item) for item in value.values()), default=0)
    if isinstance(value, list):
        return 1 + max((_depth(item) for item in value), default=0)
    return 0


def _has_nonfinite_number(value: object) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, dict):
        return any(_has_nonfinite_number(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_nonfinite_number(item) for item in value)
    return False


def strict_load_json(raw: bytes | str, *, max_bytes: int = 1_048_576,
                     max_depth: int = 32) -> object:
    """Load one bounded evidence object without JSON parser permissiveness."""
    if max_bytes < 0 or max_depth < 0:
        raise ValueError("JSON limits must not be negative")
    if isinstance(raw, str):
        data = raw.encode("utf-8", "strict")
    elif isinstance(raw, bytes):
        data = raw
    else:
        raise TypeError("JSON input must be bytes or str")
    if len(data) > max_bytes:
        raise ValueError("JSON exceeds byte limit")
    try:
        value = json.loads(
            data.decode("utf-8", "strict"),
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_nonfinite_number,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("invalid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("evidence JSON top-level must be an object")
    if _has_nonfinite_number(value):
        raise ValueError("non-finite JSON number")
    if _depth(value) > max_depth:
        raise ValueError("JSON exceeds depth limit")
    return value


def canonical_bytes(value: object) -> bytes:
    """Return compact, key-sorted UTF-8 JSON bytes for a JSON-compatible value."""
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ValueError("value is not canonical JSON") from exc


def canonical_sha256(value: object) -> str:
    """Return the SHA-256 digest of ``canonical_bytes(value)``."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _reject_unsafe_ref(ref: str) -> None:
    if not ref:
        raise ValueError("artifact reference must not be empty")
    windows = PureWindowsPath(ref)
    if Path(ref).is_absolute() or windows.is_absolute() or windows.drive or windows.root:
        raise ValueError("artifact reference must be relative")
    if ".." in windows.parts:
        raise ValueError("artifact reference must not traverse")


def _case_normalized(path: Path) -> str:
    return os.path.normcase(str(path)).casefold()


def _is_contained(root: Path, candidate: Path) -> bool:
    root_name, candidate_name = _case_normalized(root), _case_normalized(candidate)
    try:
        return os.path.commonpath((root_name, candidate_name)) == root_name
    except ValueError:
        return False


def admit_artifact_ref(root: Path, ref: str, *, must_exist: bool = True) -> Path:
    """Admit a relative evidence file only when its resolved target stays in ``root``."""
    if not isinstance(ref, str):
        raise TypeError("artifact reference must be str")
    _reject_unsafe_ref(ref)
    try:
        resolved_root = Path(root).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError("artifact root is unavailable") from exc
    if not resolved_root.is_dir():
        raise ValueError("artifact root must be a directory")
    try:
        candidate = (resolved_root / Path(ref)).resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise ValueError("artifact reference is invalid") from exc
    if not _is_contained(resolved_root, candidate):
        raise ValueError("artifact reference escapes root")
    if must_exist and not candidate.exists():
        raise ValueError("artifact does not exist")
    if candidate.exists() and not candidate.is_file():
        raise ValueError("artifact must be a regular file")
    return candidate
