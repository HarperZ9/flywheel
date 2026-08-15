"""Strict, provenance-bound migration for legacy Journeys and packets."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import tempfile
from uuid import uuid4

from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json
from .evidence_journey import verify_journey
from .journey_lock import fsync_directory
from .journey_store import (
    VERSION_SCHEMA, JourneyStore, JourneyStoreError, MutationAck, MutationCommand,
)


MIGRATION_SCHEMA = "flywheel.evidence-journey-migration/v1"
PACKET_MIGRATION_SCHEMA = "flywheel.evidence-packet-migration/v1"
_LEGACY_REF_KINDS = frozenset(("chats", "workspaces", "settings", "receipts"))


def _safe_ref(value: object) -> str:
    if type(value) is not str or not value or "\\" in value or "\x00" in value:
        raise ValueError("reference must be safe relative")
    posix, windows = PurePosixPath(value), PureWindowsPath(value)
    if (posix.is_absolute() or windows.is_absolute() or windows.drive
            or value == "." or ".." in posix.parts or any(not part for part in posix.parts)):
        raise ValueError("reference must be safe relative")
    return posix.as_posix()


def _source_path(root: Path, ref: str) -> Path:
    root = Path(root).resolve(strict=True)
    candidate = (root / Path(*PurePosixPath(_safe_ref(ref)).parts)).resolve(strict=True)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("reference must be safe relative") from exc
    if not candidate.is_file():
        raise ValueError("snapshot_ref must identify a file")
    return candidate


def _validated_legacy_refs(value: object) -> dict:
    if type(value) is not dict or not set(value) <= _LEGACY_REF_KINDS:
        raise ValueError("legacy_refs has invalid fields")
    result = {}
    for kind, refs in value.items():
        if type(refs) is not list:
            raise ValueError("legacy_refs values must be lists")
        result[kind] = [_safe_ref(ref) for ref in refs]
        if len(result[kind]) != len(set(result[kind])):
            raise ValueError("legacy_refs must not contain duplicates")
    return result


def _snapshot_parts(value: object, root: Path) -> tuple[dict, str, bytes, dict]:
    if type(value) is not dict or not {"snapshot_ref", "snapshot"} <= set(value):
        raise ValueError("snapshot requires snapshot_ref and snapshot")
    if not set(value) <= {"snapshot_ref", "snapshot", "legacy_refs"}:
        raise ValueError("snapshot import has invalid fields")
    ref = _safe_ref(value["snapshot_ref"])
    raw = _source_path(root, ref).read_bytes()
    parsed = strict_load_json(raw)
    if type(value["snapshot"]) is not dict or parsed != value["snapshot"]:
        raise ValueError("snapshot bytes do not match supplied snapshot")
    if verify_journey(parsed).get("verdict") != "PASS":
        raise ValueError("snapshot is not a valid v1 Journey")
    return parsed, ref, raw, _validated_legacy_refs(value.get("legacy_refs", {}))


def import_v1_snapshot(snapshot: dict, *, actor_id: str, store: JourneyStore,
                       created_at: str) -> MutationAck:
    """Import one immutable v1 snapshot as a custody-honest v2 genesis."""
    if not isinstance(store, JourneyStore):
        raise TypeError("store must be JourneyStore")
    legacy, ref, raw, legacy_refs = _snapshot_parts(snapshot, store.state_root)
    digest = hashlib.sha256(raw).hexdigest()
    legacy_times = {
        "created_at": legacy["created_at"],
        "event_occurred_at": [event["occurred_at"] for event in legacy["events"]],
    }
    intake = {
        "snapshot_ref": ref, "snapshot_sha256": digest,
        "custody_before_import": False, "legacy_timestamp_facts": legacy_times,
        "legacy_refs": legacy_refs,
    }
    command = MutationCommand(
        owner_ref=actor_id, journey_ref=f"jrn_{digest[:32]}", expected_event_head=None,
        client_request_id=f"import-v1:{digest}", operation="intake",
        body={"legacy_label": legacy["journey_id"], "goal": legacy["goal"],
              "intake": intake, "occurred_at": created_at},
    )
    return store.create(command)


def _atomic_replace(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        with path.open("r+b") as stream:
            os.fsync(stream.fileno())
        fsync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _version(pointer: Path) -> tuple[int, bytes | None]:
    if not pointer.exists():
        inferred = 2 if (pointer.parent / "v2").exists() and not (pointer.parent / "v1").exists() else 1
        return inferred, None
    raw = pointer.read_bytes()
    value = strict_load_json(raw)
    if (set(value) != {"schema", "version"} or value.get("schema") != VERSION_SCHEMA
            or type(value.get("version")) is not int or value["version"] < 1):
        raise JourneyStoreError("STORE_COMMIT_FAILED")
    return value["version"], raw


def _migration_result(*, current: int, target: int, migrated: bool,
                      read_only: bool, directory: Path | None = None) -> dict:
    result = {"from_version": current, "version": target, "migrated": migrated,
              "read_only": read_only, "mutation_error": "VERSION_MISMATCH" if read_only else None}
    if directory is not None:
        base = directory.as_posix()
        result.update({"backup_ref": f"{base}/version.backup.json",
                       "journal_ref": f"{base}/journal.json"})
    return result


def _prior_migration(root: Path, target: int) -> Path | None:
    base = root / "journeys" / "migrations"
    if not base.exists():
        return None
    candidates = [path for path in base.glob(f"v*-to-v{target}")
                  if (path / "version.backup.json").is_file()
                  and (path / "journal.json").is_file()]
    if len(candidates) != 1:
        return None
    return candidates[0].relative_to(root)


def migrate_store(store_root: Path, *, target_version: int) -> dict:
    """Move the version pointer only after a durable backup and journal exist."""
    if type(target_version) is not int or target_version < 1:
        raise ValueError("target_version must be a positive integer")
    root, pointer = Path(store_root), Path(store_root) / "journeys" / "version.json"
    current, original = _version(pointer)
    if current > target_version:
        return _migration_result(current=current, target=target_version,
                                 migrated=False, read_only=True)
    if current == target_version:
        return _migration_result(current=current, target=target_version,
                                 migrated=False, read_only=False,
                                 directory=_prior_migration(root, target_version))
    relative = Path("journeys") / "migrations" / f"v{current}-to-v{target_version}"
    directory = root / relative
    backup = original if original is not None else canonical_bytes({"pointer_present": False})
    _atomic_replace(directory / "version.backup.json", backup)
    journal = {"schema": MIGRATION_SCHEMA, "from_version": current,
               "target_version": target_version, "status": "prepared"}
    _atomic_replace(directory / "journal.json", canonical_bytes(journal))
    try:
        _atomic_replace(pointer, canonical_bytes({"schema": VERSION_SCHEMA,
                                                  "version": target_version}))
    except OSError:
        if original is None:
            try:
                pointer.unlink()
            except FileNotFoundError:
                pass
        else:
            _atomic_replace(pointer, original)
        journal["status"] = "rolled_back"
        _atomic_replace(directory / "journal.json", canonical_bytes(journal))
        raise JourneyStoreError("STORE_COMMIT_FAILED") from None
    return _migration_result(current=current, target=target_version,
                             migrated=True, read_only=False, directory=relative)


def _packet_inventory(root: Path) -> tuple[list[tuple[str, bytes]], str]:
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            if path.is_symlink():
                raise ValueError("packet symlinks are not admitted")
            continue
        ref, raw = path.relative_to(root).as_posix(), path.read_bytes()
        files.append((ref, raw))
    manifest = [{"ref": ref, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
                for ref, raw in files]
    return files, canonical_sha256(manifest)


def _is_link(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def _verified_output_root(path: Path) -> Path:
    candidate = Path(path).absolute()
    for component in (*reversed(candidate.parents), candidate):
        if _is_link(component):
            raise ValueError("derived packet path contains a link")
    candidate.mkdir(parents=True, exist_ok=True)
    if _is_link(candidate) or not candidate.is_dir():
        raise ValueError("derived packet output root must be a plain directory")
    return candidate.resolve(strict=True)


def _write_exclusive(root: Path, relative: Path, raw: bytes) -> None:
    parent = root
    for part in relative.parent.parts:
        parent /= part
        try:
            parent.mkdir()
        except FileExistsError:
            pass
        if _is_link(parent) or not parent.is_dir():
            raise ValueError("derived packet destination contains a link")
    path = parent / relative.name
    if _is_link(path):
        raise ValueError("derived packet destination contains a link")
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _stage_packet(out: Path, ref: str, files: list[tuple[str, bytes]], descriptor: dict) -> Path:
    staging = Path(tempfile.mkdtemp(prefix=f".{ref}.", dir=out))
    try:
        for relative, raw in files:
            _write_exclusive(staging, Path(*PurePosixPath(relative).parts), raw)
        _write_exclusive(staging, Path("migration.json"), canonical_bytes(descriptor))
        for directory in sorted({path.parent for path in staging.rglob("*") if path.is_file()},
                                key=lambda path: len(path.parts), reverse=True):
            fsync_directory(directory)
        fsync_directory(staging)
        return staging
    except Exception:
        shutil.rmtree(staging)
        raise


def migrate_packet(packet_root: Path, *, target_schema: str, out_root: Path) -> dict:
    """Create a derived packet bound to the exact immutable source tree."""
    source, out_path = Path(packet_root).resolve(strict=True), Path(out_root).absolute()
    if type(target_schema) is not str or not target_schema.strip() or not source.is_dir():
        raise ValueError("packet root and target_schema are required")
    if out_path == source or source in out_path.parents:
        raise ValueError("derived packet must be outside the source packet")
    out = _verified_output_root(out_path)
    files, digest = _packet_inventory(source)
    ref = f"packet-{digest[:16]}"
    target = out / ref
    if target.exists() or _is_link(target):
        raise ValueError("derived packet target exists or is a link")
    descriptor = {"schema": PACKET_MIGRATION_SCHEMA, "target_schema": target_schema,
                  "source_sha256": digest}
    staging = _stage_packet(out, ref, files, descriptor)
    try:
        os.replace(staging, target)
        fsync_directory(out)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return {"derived_packet_ref": ref, "source_sha256": digest,
            "target_schema": target_schema}
