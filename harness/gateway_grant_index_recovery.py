"""Recovery marker for the gateway grant proposal listing index."""
from __future__ import annotations

from pathlib import Path
import os
from uuid import uuid4

from .evidence_json import canonical_bytes, strict_load_json
from .journey_lock import fsync_directory
from .operation_grants import _secure_owner_only

RECOVERY_FILENAME = "proposal-index-recovery.marker"
RECOVERY_MARKER_SCHEMA = "flywheel.gateway-grant-index-recovery/v1"


def _recovery_path(owner_dir: Path) -> Path:
    return Path(owner_dir) / RECOVERY_FILENAME


def recovery_required(owner_dir: Path) -> str | None:
    path = _recovery_path(owner_dir)
    if not path.exists():
        return None
    try:
        with path.open("rb") as stream:
            data = stream.read(4097)
        if len(data) > 4096:
            return "RECOVERY_MARKER_INVALID"
        value = strict_load_json(data)
        if (type(value) is dict and value.get("schema") == RECOVERY_MARKER_SCHEMA
                and type(value.get("reason")) is str):
            return value["reason"]
    except Exception:
        pass
    return "RECOVERY_MARKER_INVALID"


def mark_recovery_required(owner_dir: Path, reason: str, now_text: str) -> None:
    value = {"schema": RECOVERY_MARKER_SCHEMA, "reason": reason,
             "observed_at": now_text}
    path = _recovery_path(owner_dir)
    temporary = path.with_name(f".{RECOVERY_FILENAME}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            _secure_owner_only(temporary, directory=False)
            stream.write(canonical_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _secure_owner_only(path, directory=False)
        fsync_directory(owner_dir)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def clear_recovery_required(owner_dir: Path) -> None:
    try:
        _recovery_path(owner_dir).unlink()
    except FileNotFoundError:
        pass
    fsync_directory(owner_dir)
