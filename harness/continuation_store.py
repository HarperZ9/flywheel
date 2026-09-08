"""Private local storage for provider-neutral continuation previews."""
from __future__ import annotations

import os
import re
from pathlib import Path
from uuid import uuid4

from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json
from .evidence_public import TransportError, public_metadata
from .journey_lock import fsync_directory

PREVIEW_REF_PATTERN = re.compile(r"cpv_[0-9a-f]{32}\Z")


def _preview_dir(state_root: Path) -> Path:
    root = Path(state_root) / "continuation" / "previews"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _artifact_root(state_root: Path) -> Path:
    root = Path(state_root) / "artifacts" / "continuation"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _atomic_json(path: Path, value: dict) -> None:
    data = canonical_bytes(value)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        with path.open("r+b") as stream:
            os.fsync(stream.fileno())
        fsync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _validate_ref(preview_ref: object) -> str:
    if type(preview_ref) is not str or PREVIEW_REF_PATTERN.fullmatch(preview_ref) is None:
        raise TransportError("INVALID_CONTINUATION", "continuation preview is invalid", 422)
    return preview_ref


def write_preview(state_root: Path, preview: dict, intake: dict) -> dict:
    preview_ref = _validate_ref(preview.get("preview_ref"))
    if preview.get("preview_sha256") != canonical_sha256({
            key: value for key, value in preview.items()
            if key != "preview_sha256"}):
        raise TransportError("INVALID_CONTINUATION", "continuation preview is invalid", 422)
    public_metadata(intake)
    _atomic_json(_preview_dir(state_root) / f"{preview_ref}.json", preview)
    _atomic_json(_artifact_root(state_root) / f"{preview_ref}.intake.json", intake)
    return preview


def load_preview(state_root: Path, preview_ref: object) -> dict:
    ref = _validate_ref(preview_ref)
    path = _preview_dir(state_root) / f"{ref}.json"
    if not path.exists():
        raise TransportError("PREVIEW_NOT_FOUND", "continuation preview was not found", 404)
    try:
        value = strict_load_json(path.read_bytes(), max_bytes=1_048_576, max_depth=32)
    except (OSError, TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise TransportError("INVALID_CONTINUATION", "continuation preview is invalid", 422) from exc
    if type(value) is not dict or value.get("preview_ref") != ref:
        raise TransportError("INVALID_CONTINUATION", "continuation preview is invalid", 422)
    expected = canonical_sha256({key: item for key, item in value.items()
                                 if key != "preview_sha256"})
    if value.get("preview_sha256") != expected:
        raise TransportError("INVALID_CONTINUATION", "continuation preview is invalid", 422)
    return value


def intake_ref(preview_ref: object) -> str:
    return f"continuation/{_validate_ref(preview_ref)}.intake.json"
