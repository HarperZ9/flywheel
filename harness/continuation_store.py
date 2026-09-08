"""Private local storage for provider-neutral continuation previews."""
from __future__ import annotations

from contextlib import contextmanager
import os
import re
from pathlib import Path
from uuid import uuid4

from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json
from .evidence_public import TransportError, public_metadata
from .journey_lock import ExclusiveJourneyLock, JourneyLockBusy, fsync_directory
from .journey_types import JOURNEY_REF_PATTERN, SHA256_PATTERN

PREVIEW_REF_PATTERN = re.compile(r"cpv_[0-9a-f]{32}\Z")
START_BINDING_SCHEMA = "flywheel.native-continuation-start-binding/v1"
_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


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


def _validate_owner(owner_ref: object) -> str:
    if type(owner_ref) is not str or _ID_PATTERN.fullmatch(owner_ref) is None:
        raise TransportError(
            "INVALID_CONTINUATION", "continuation owner is invalid", 422)
    return owner_ref


def _start_dir(state_root: Path) -> Path:
    root = Path(state_root) / "continuation" / "starts"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _owner_start_dir(state_root: Path, owner_ref: object) -> Path:
    root = _start_dir(state_root) / _validate_owner(owner_ref)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _binding_sha(value: dict) -> str:
    return canonical_sha256({k: v for k, v in value.items()
                             if k != "binding_sha256"})


def _validate_start_binding(value: object, preview_ref: object) -> dict:
    ref = _validate_ref(preview_ref)
    expected = {"schema", "owner_ref", "preview_ref", "preview_sha256",
                "source_state_sha256", "journey_ref", "start_client_request_id",
                "recovery_client_request_id", "recovery_event_sha256",
                "recovery_event_head_sha256", "recovery_action_id",
                "binding_sha256"}
    if (type(value) is not dict or set(value) != expected
            or value.get("schema") != START_BINDING_SCHEMA
            or value.get("preview_ref") != ref
            or SHA256_PATTERN.fullmatch(value.get("preview_sha256", "")) is None
            or SHA256_PATTERN.fullmatch(
                value.get("source_state_sha256", "")) is None
            or JOURNEY_REF_PATTERN.fullmatch(value.get("journey_ref", "")) is None
            or _ID_PATTERN.fullmatch(value.get("owner_ref", "")) is None
            or _ID_PATTERN.fullmatch(
                value.get("start_client_request_id", "")) is None
            or _ID_PATTERN.fullmatch(
                value.get("recovery_client_request_id", "")) is None
            or SHA256_PATTERN.fullmatch(
                value.get("recovery_event_sha256", "")) is None
            or SHA256_PATTERN.fullmatch(
                value.get("recovery_event_head_sha256", "")) is None
            or value.get("recovery_action_id") != "continue-" + ref
            or value.get("binding_sha256") != _binding_sha(value)):
        raise TransportError(
            "CONTINUATION_BINDING_DRIFT",
            "continuation start binding changed", 409)
    return value


@contextmanager
def start_lock(state_root: Path, owner_ref: str, preview_ref: object,
               client_request_id: object):
    ref = _validate_ref(preview_ref)
    owner = _validate_owner(owner_ref)
    if (type(client_request_id) is not str or not client_request_id.strip()):
        raise TransportError(
            "INVALID_CONTINUATION", "continuation start is invalid", 422)
    key = canonical_sha256({"owner_ref": owner, "preview_ref": ref})
    try:
        with ExclusiveJourneyLock.acquire(
                _start_dir(state_root) / "locks" / f"{key}.lock"):
            yield
    except JourneyLockBusy as exc:
        raise TransportError(
            "STORE_BUSY", "continuation start is busy", 503) from exc


def write_start_binding(state_root: Path, preview: dict, owner_ref: str,
                        journey: dict, start_request: str,
                        recovery_request: str) -> dict:
    ref = _validate_ref(preview.get("preview_ref"))
    value = {"schema": START_BINDING_SCHEMA, "owner_ref": owner_ref,
             "preview_ref": ref, "preview_sha256": preview["preview_sha256"],
             "source_state_sha256": preview["source_state_sha256"],
             "journey_ref": journey["journey_ref"],
             "start_client_request_id": start_request,
             "recovery_client_request_id": recovery_request,
             "recovery_event_sha256": journey["event_sha256"],
             "recovery_event_head_sha256": journey["event_head_sha256"],
             "recovery_action_id": "continue-" + ref}
    value["binding_sha256"] = _binding_sha(value)
    path = _owner_start_dir(state_root, owner_ref) / f"{ref}.json"
    if path.exists() and load_start_binding(state_root, owner_ref, ref) != value:
        raise TransportError(
            "CONTINUATION_BINDING_DRIFT",
            "continuation start binding changed", 409)
    _atomic_json(path, value)
    return value


def load_start_binding(state_root: Path, owner_ref: str, preview_ref: object) -> dict:
    ref = _validate_ref(preview_ref)
    path = _owner_start_dir(state_root, owner_ref) / f"{ref}.json"
    if not path.exists():
        raise TransportError(
            "CONTINUATION_NOT_STARTED",
            "continuation has not been started", 409)
    try:
        return _validate_start_binding(strict_load_json(
            path.read_bytes(), max_bytes=16384, max_depth=8), ref)
    except TransportError:
        raise
    except (OSError, TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise TransportError(
            "CONTINUATION_BINDING_DRIFT",
            "continuation start binding changed", 409) from exc


def intake_ref(preview_ref: object) -> str:
    return f"continuation/{_validate_ref(preview_ref)}.intake.json"
