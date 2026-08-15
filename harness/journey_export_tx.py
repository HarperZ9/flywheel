"""Private durable transaction and target-lock substrate for Journey export."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
from uuid import uuid4

from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json
from .journey_lock import ExclusiveJourneyLock, JourneyLockBusy, fsync_directory
from .journey_store import JourneyStoreError
from .journey_types import JOURNEY_REF_PATTERN, SHA256_PATTERN
from .operation_grants import _secure_owner_only, _validate_owner_ref

TX_SCHEMA = "flywheel.evidence-journey-export-transaction/v1"
PHASES = frozenset(("prepared", "authorized", "packed", "published",
                    "quarantine_pending", "committed", "quarantined"))
TX_FIELDS = frozenset(("schema", "owner_ref", "client_request_sha256",
    "request_sha256", "journey_ref", "source_event_head_sha256",
    "source_projection_sha256", "artifact_root_ref", "packet_ref",
    "packet_profile", "internal_request_id", "grant_record_ref",
    "grant_ref_sha256", "grant_request_sha256", "phase", "packet_digest",
    "final_event_head_sha256", "final_projection_sha256",
    "transaction_sha256"))

def _canonical_ref(value: object, *, allow_dot: bool) -> str:
    if type(value) is not str or not value or "\\" in value or "\x00" in value:
        raise ValueError("artifact reference is invalid")
    posix, windows = PurePosixPath(value), PureWindowsPath(value)
    if (value.lower().startswith("file:") or posix.is_absolute()
            or windows.is_absolute() or windows.drive or ".." in posix.parts
            or value != posix.as_posix() or not allow_dot and value == "."):
        raise ValueError("artifact reference is invalid")
    return value
def _is_reparse(path: Path) -> bool:
    return path.is_symlink() or bool(
        getattr(path.lstat(), "st_file_attributes", 0) & 0x400)
def path_present(path: Path) -> bool:
    """Report directory entries without following a broken reparse target."""
    return os.path.lexists(path)
def _check_ancestors(root: Path, relative: str) -> None:
    current = root
    for part in PurePosixPath(relative).parts:
        current = current / part
        if not path_present(current):
            continue
        if _is_reparse(current):
            raise ValueError("artifact path contains a link or reparse point")
def artifact_root_path(state_root: Path, root_ref: object) -> tuple[Path, str]:
    """Admit one existing artifact directory beneath state custody."""
    ref = _canonical_ref(root_ref, allow_dot=True)
    state = Path(state_root).resolve(strict=True)
    if _is_reparse(state):
        raise ValueError("state root is a link or reparse point")
    _check_ancestors(state, ref)
    root = (state / Path(ref)).resolve(strict=True)
    try:
        contained = os.path.commonpath((os.path.normcase(str(state)),
            os.path.normcase(str(root)))) == os.path.normcase(str(state))
    except ValueError:
        contained = False
    if not contained or not root.is_dir() or _is_reparse(root):
        raise ValueError("artifact root is invalid")
    return root, ref
def packet_target_path(root: Path, packet_ref: object) -> tuple[Path, str]:
    """Admit an absent-or-owned packet selector without following links."""
    ref = _canonical_ref(packet_ref, allow_dot=False)
    _check_ancestors(root, ref)
    target = root.joinpath(*PurePosixPath(ref).parts)
    try:
        candidate = target.resolve(strict=False)
        contained = os.path.commonpath((os.path.normcase(str(root)),
            os.path.normcase(str(candidate)))) == os.path.normcase(str(root))
    except (OSError, RuntimeError, ValueError):
        contained = False
    if not contained:
        raise ValueError("packet target escapes artifact root")
    return target, ref
def prepare_target_parent(root: Path, target: Path) -> None:
    """Create and flush only missing ancestors of one admitted target."""
    current = root
    for part in target.relative_to(root).parts[:-1]:
        parent, current = current, current / part
        if path_present(current):
            if not current.is_dir() or _is_reparse(current):
                raise ValueError("packet target ancestor is invalid")
            continue
        current.mkdir(); _secure_owner_only(current, directory=True)
        fsync_directory(parent)
def request_digest(*, owner_ref: str, journey_ref: str, expected_event_head: str,
                   client_request_id: str, body: dict) -> str:
    return canonical_sha256({"owner_ref": owner_ref, "journey_ref": journey_ref,
        "expected_event_head": expected_event_head,
        "client_request_id": client_request_id, "body": body})

def _tx_root(state_root: Path) -> Path:
    return Path(state_root) / "journey-exports" / "v2"

def _prepare_private(path: Path, state_root: Path) -> None:
    state = Path(os.path.abspath(state_root)); target = Path(os.path.abspath(path))
    try:
        contained = os.path.commonpath((os.path.normcase(str(state)),
            os.path.normcase(str(target)))) == os.path.normcase(str(state))
        relative = target.relative_to(state)
    except ValueError:
        contained = False
    if (not contained or not path_present(state) or _is_reparse(state)
            or not state.is_dir()):
        raise ValueError("private export path escapes state custody")
    current = state
    for part in relative.parts:
        parent, current, created = current, current / part, False
        if not path_present(current):
            try: current.mkdir(); created = True
            except FileExistsError: pass
        if (not path_present(current) or _is_reparse(current)
                or not current.is_dir()):
            raise ValueError("private export path contains a reparse point")
        _secure_owner_only(current, directory=True)
        if created: fsync_directory(parent)

def owner_transaction_dir(state_root: Path, owner_ref: str) -> Path:
    _validate_owner_ref(owner_ref)
    path = _tx_root(state_root) / "owners" / owner_ref
    _prepare_private(path, state_root)
    return path

def transaction_path(state_root: Path, owner_ref: str,
                     client_request_id: str) -> Path:
    return owner_transaction_dir(state_root, owner_ref) / (
        canonical_sha256(client_request_id) + ".json")

def _self_hash(value: dict) -> str:
    return canonical_sha256({key: item for key, item in value.items()
                             if key != "transaction_sha256"})

def validate_transaction(value: object) -> dict:
    if (type(value) is not dict or set(value) != TX_FIELDS
            or value.get("schema") != TX_SCHEMA
            or value.get("phase") not in PHASES
            or value.get("transaction_sha256") != _self_hash(value)):
        raise JourneyStoreError("STORE_COMMIT_FAILED")
    try:
        _validate_owner_ref(value["owner_ref"])
        if JOURNEY_REF_PATTERN.fullmatch(value["journey_ref"]) is None:
            raise ValueError("journey_ref")
        for name in ("client_request_sha256", "request_sha256",
                     "source_event_head_sha256", "source_projection_sha256",
                     "grant_ref_sha256", "grant_request_sha256"):
            if SHA256_PATTERN.fullmatch(value[name]) is None:
                raise ValueError(name)
        for name in ("packet_digest", "final_event_head_sha256",
                     "final_projection_sha256"):
            item = value[name]
            if (item is not None and (type(item) is not str
                    or SHA256_PATTERN.fullmatch(item.removeprefix("sha256:")) is None)):
                raise ValueError(name)
        _canonical_ref(value["artifact_root_ref"], allow_dot=True)
        _canonical_ref(value["packet_ref"], allow_dot=False)
        _canonical_ref(value["grant_record_ref"], allow_dot=False)
        if (value["packet_profile"] != "flywheel.evidence-journey-custody/v2"
                or type(value["internal_request_id"]) is not str
                or not value["internal_request_id"]):
            raise ValueError("transaction identity")
    except (KeyError, TypeError, ValueError):
        raise JourneyStoreError("STORE_COMMIT_FAILED") from None
    return value

def replace_transaction(path: Path, value: dict) -> dict:
    sealed = dict(value); sealed["transaction_sha256"] = _self_hash(sealed)
    validate_transaction(sealed)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            _secure_owner_only(temporary, directory=False)
            stream.write(canonical_bytes(sealed)); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path); _secure_owner_only(path, directory=False)
        with path.open("r+b") as stream:
            os.fsync(stream.fileno())
        for directory in (path.parent, path.parent.parent, path.parent.parent.parent,
                          path.parent.parent.parent.parent):
            fsync_directory(directory)
        return sealed
    finally:
        try: temporary.unlink()
        except FileNotFoundError: pass

def load_transaction(path: Path) -> dict | None:
    if not path_present(path):
        return None
    try:
        _secure_owner_only(path, directory=False)
        return validate_transaction(strict_load_json(path.read_bytes()))
    except JourneyStoreError:
        raise
    except (OSError, TypeError, ValueError):
        raise JourneyStoreError("STORE_COMMIT_FAILED") from None

def load_or_create(path: Path, template: dict) -> tuple[dict, bool]:
    try:
        with ExclusiveJourneyLock.acquire(path.parent / ".lock"):
            current = load_transaction(path)
            if current is not None:
                if current["request_sha256"] != template["request_sha256"]:
                    raise JourneyStoreError("IDEMPOTENCY_MISMATCH")
                return current, True
            return replace_transaction(path, template), False
    except JourneyLockBusy:
        raise JourneyStoreError("STORE_BUSY") from None

def update_phase(path: Path, value: dict, phase: str, **changes) -> dict:
    if phase not in PHASES:
        raise JourneyStoreError("STORE_COMMIT_FAILED")
    return replace_transaction(path, {**value, **changes, "phase": phase})

def target_lock_path(state_root: Path, artifact_ref: str,
                     packet_ref: str) -> Path:
    root = _tx_root(state_root) / "target-locks"
    _prepare_private(root, state_root)
    return root / (canonical_sha256(
        {"artifact_root_ref": artifact_ref, "packet_ref": packet_ref}) + ".lock")

def staging_path(state_root: Path, value: dict) -> Path:
    _validate_owner_ref(value["owner_ref"])
    root = _tx_root(state_root) / "staging" / value["owner_ref"]
    _prepare_private(root, state_root)
    return root / value["client_request_sha256"]

def quarantine_path(state_root: Path, value: dict) -> Path:
    _validate_owner_ref(value["owner_ref"])
    root = _tx_root(state_root) / "quarantine" / value["owner_ref"]
    _prepare_private(root, state_root)
    suffix = (value.get("packet_digest") or "unsealed").removeprefix("sha256:")[:16]
    return root / f"{value['client_request_sha256']}-{suffix}"

def grant_record_ref(owner_ref: str, grant_ref: str) -> tuple[str, str]:
    name = hashlib.sha256(grant_ref.encode("ascii")).hexdigest() + ".json"
    return f"grants/{owner_ref}/{name}", canonical_sha256(grant_ref)

def consumed_grant_matches(state_root: Path, value: dict) -> bool:
    try:
        ref = _canonical_ref(value["grant_record_ref"], allow_dot=False)
        path = Path(state_root).joinpath(*PurePosixPath(ref).parts)
        record = strict_load_json(path.read_bytes())
        fields = {"schema", "grant_sha256", "request_sha256", "expires_at",
                  "consumed", "consumed_at"}
        return (set(record) == fields
            and record.get("schema") == "flywheel.operation-grant/v1"
            and record.get("grant_sha256") == value["grant_ref_sha256"]
            and record.get("request_sha256") == value["grant_request_sha256"]
            and record.get("consumed") is True
            and type(record.get("consumed_at")) is str)
    except (OSError, TypeError, ValueError):
        return False

def iter_transactions(state_root: Path) -> list[tuple[Path, dict]]:
    owners = _tx_root(state_root) / "owners"
    if not path_present(owners):
        return []
    _prepare_private(owners, state_root)
    output = []
    for path in sorted(owners.glob("*/*.json")):
        _prepare_private(path.parent, state_root)
        value = load_transaction(path)
        if value is not None:
            output.append((path, value))
    return output
def recover_export_transactions(state_root: Path, *, now: str) -> tuple[int, int, list[str]]:
    """Advance consumed exact transactions or quarantine their one owned target."""
    from .journey_export import JourneyExportService
    from .journey_service import JourneyService
    from .journey_store import JourneyStore
    from .operation_grants import GrantStore
    completed, quarantined, diagnostics = 0, 0, []
    for path, value in iter_transactions(state_root):
        if value["phase"] in {"committed", "quarantined"}:
            continue
        service = JourneyService(owner_ref=value["owner_ref"],
            store=JourneyStore(state_root),
            grants=GrantStore(state_root, clock=lambda: now), clock=lambda: now)
        exporter = JourneyExportService(journey=service,
            artifact_root_ref=value["artifact_root_ref"])
        try:
            root, artifact_ref = artifact_root_path(state_root,
                value["artifact_root_ref"])
            target, packet_ref = packet_target_path(root, value["packet_ref"])
            lock = target_lock_path(state_root, artifact_ref, packet_ref)
            with (service._operation_guard(value["journey_ref"], "export-admission"),
                  ExclusiveJourneyLock.acquire(lock, service.store.lock_timeout_s)):
                result = exporter._advance(path, value, root, target)
            completed += int(result is not None)
        except JourneyStoreError as exc:
            current = load_transaction(path)
            if exc.code == "HEAD_CONFLICT" and current["phase"] == "quarantined":
                quarantined += 1
            diagnostics.append(path.relative_to(Path(state_root)).as_posix())
        except (JourneyLockBusy, OSError, TypeError, ValueError):
            diagnostics.append(path.relative_to(Path(state_root)).as_posix())
    return completed, quarantined, diagnostics
