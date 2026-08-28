"""Owner-private opaque handles for secrets held only by the OS keychain."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import secrets
from typing import Callable, Mapping
from uuid import uuid4

from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json
from .journey_lock import ExclusiveJourneyLock, JourneyLockBusy, fsync_directory
from .operation_grants import _secure_owner_only, _validate_owner_ref

HANDLE_SCHEMA = "flywheel.credential-handle/v1"
CREDENTIAL_REF_PATTERN = re.compile(r"cred_[0-9a-f]{32}\Z")
_SLOT_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}\Z")
_EXECUTION_NAMES = frozenset((
    "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP",
    "HOME", "TMPDIR", "LANG", "LC_ALL",
))
_RECORD_FIELDS = frozenset((
    "schema", "credential_ref", "credential_name", "owner_ref",
    "record_sha256",
))


class CredentialHandleError(RuntimeError):
    """A fixed, non-enumerating credential-custody failure."""

    def __init__(self, code: str = "PERMISSION_REQUIRED") -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class CredentialHandle:
    credential_ref: str
    credential_name: str


class CredentialBindings:
    """Ephemeral values that redact their representation."""

    def __init__(self, values: Mapping[str, str]) -> None:
        self._values = dict(values)

    def __repr__(self) -> str:
        return "CredentialBindings(<redacted>)"

    def value_for(self, credential_name: str) -> str:
        try:
            return self._values[credential_name]
        except KeyError:
            raise CredentialHandleError() from None

    def child_environment(
            self, source_env: Mapping[str, str], *, platform: str) -> dict[str, str]:
        allowed = (("PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC",
                    "TEMP", "TMP") if platform == "windows" else
                   ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL")
                   if platform == "posix" else ())
        if not allowed:
            raise CredentialHandleError()
        result = {name: source_env[name] for name in allowed
                  if type(source_env.get(name)) is str}
        result.update(self._values)
        return result

    def redact(self, text: str) -> str:
        """Scrub every bound credential value out of `text`.

        Longer values are redacted first so that one bound value which is a
        substring of another (e.g. "abc" and "abcdef") can't leave a
        fragment of the longer value behind after the shorter value's pass
        has already carved a "[REDACTED]" hole out of it.
        """
        for value in sorted((v for v in self._values.values() if v),
                            key=len, reverse=True):
            text = text.replace(value, "[REDACTED]")
        return text


class CredentialHandleStore:
    """Metadata-only persistent handles with explicit keychain resolution."""

    def __init__(
            self, state_root: Path, *, keychain_get: Callable[[str], str | None],
            token_hex: Callable[[int], str] = secrets.token_hex) -> None:
        self.state_root = Path(state_root)
        self._keychain_get = keychain_get
        self._token_hex = token_hex

    def bind(self, owner_ref: str, credential_name: str) -> CredentialHandle:
        try:
            self._validate_slot(credential_name)
            _validate_owner_ref(owner_ref)
            self._keychain_value(credential_name)
            owner_dir = self._owner_dir(owner_ref, create=True)
            with ExclusiveJourneyLock.acquire(owner_dir / ".lock"):
                credential_ref = self._new_ref(owner_dir)
                record = self._record(owner_ref, credential_ref, credential_name)
                self._replace(self._path(owner_dir, credential_ref), record)
                for path in (owner_dir, owner_dir.parent, self.state_root):
                    fsync_directory(path)
            return CredentialHandle(credential_ref, credential_name)
        except CredentialHandleError:
            raise
        except JourneyLockBusy:
            raise CredentialHandleError("STORE_BUSY") from None
        except (OSError, TypeError, ValueError):
            raise CredentialHandleError() from None

    def list_handles(self, owner_ref: str) -> tuple[CredentialHandle, ...]:
        try:
            owner_dir = self._owner_dir(owner_ref, create=False)
            if not owner_dir.is_dir():
                return ()
            _secure_owner_only(owner_dir.parent, directory=True)
            _secure_owner_only(owner_dir, directory=True)
            handles = [self._read(path, owner_ref) for path in owner_dir.glob("*.json")]
            return tuple(sorted(handles, key=lambda item: (
                item.credential_name, item.credential_ref)))
        except CredentialHandleError:
            raise
        except (OSError, TypeError, ValueError):
            raise CredentialHandleError() from None

    def resolve_exact(
            self, owner_ref: str, refs: list[str] | tuple[str, ...],
            required_slots: list[str] | tuple[str, ...]) -> CredentialBindings:
        try:
            slot_values = tuple(required_slots)
            if (len(set(slot_values)) != len(slot_values)
                    or any(not self._valid_slot(slot) for slot in slot_values)):
                raise CredentialHandleError()
            resolved_slots = self.slot_names_exact(owner_ref, refs)
            if set(resolved_slots) != set(slot_values):
                raise CredentialHandleError()
            values = {name: self._keychain_value(name) for name in resolved_slots}
            return CredentialBindings(values)
        except CredentialHandleError:
            raise
        except (OSError, TypeError, ValueError):
            raise CredentialHandleError() from None

    def slot_names_exact(
            self, owner_ref: str,
            refs: list[str] | tuple[str, ...]) -> tuple[str, ...]:
        """Return validated slot metadata in ref order without secret access."""
        try:
            _validate_owner_ref(owner_ref)
            ref_values = tuple(refs)
            if (len(set(ref_values)) != len(ref_values)
                    or any(not self._valid_ref(ref) for ref in ref_values)):
                raise CredentialHandleError()
            if not ref_values:
                return ()
            owner_dir = self._owner_dir(owner_ref, create=False)
            if not owner_dir.is_dir():
                raise CredentialHandleError()
            _secure_owner_only(owner_dir.parent, directory=True)
            _secure_owner_only(owner_dir, directory=True)
            handles = tuple(self._read(self._path(owner_dir, ref), owner_ref)
                            for ref in ref_values)
            if tuple(item.credential_ref for item in handles) != ref_values:
                raise CredentialHandleError()
            return tuple(item.credential_name for item in handles)
        except CredentialHandleError:
            raise
        except (OSError, TypeError, ValueError):
            raise CredentialHandleError() from None

    @staticmethod
    def _valid_ref(value: object) -> bool:
        return type(value) is str and CREDENTIAL_REF_PATTERN.fullmatch(value) is not None

    @staticmethod
    def _valid_slot(value: object) -> bool:
        return (type(value) is str and _SLOT_PATTERN.fullmatch(value) is not None
                and value.upper() not in _EXECUTION_NAMES)

    @classmethod
    def _validate_slot(cls, value: object) -> str:
        if not cls._valid_slot(value):
            raise CredentialHandleError("INVALID_REQUEST")
        return value

    def _owner_dir(self, owner_ref: str, *, create: bool) -> Path:
        _validate_owner_ref(owner_ref)
        root = self.state_root / "credential-handles"
        owner = root / owner_ref
        if create:
            root.mkdir(parents=True, exist_ok=True)
            _secure_owner_only(root, directory=True)
            owner.mkdir(exist_ok=True)
            _secure_owner_only(owner, directory=True)
        return owner

    @staticmethod
    def _path(owner_dir: Path, credential_ref: str) -> Path:
        if not CredentialHandleStore._valid_ref(credential_ref):
            raise CredentialHandleError()
        return owner_dir / f"{canonical_sha256(credential_ref)}.json"

    def _new_ref(self, owner_dir: Path) -> str:
        for _ in range(16):
            try:
                value = f"cred_{self._token_hex(16)}"
            except Exception:
                raise CredentialHandleError() from None
            if self._valid_ref(value) and not self._path(owner_dir, value).exists():
                return value
        raise CredentialHandleError()

    @staticmethod
    def _record(owner_ref: str, credential_ref: str, credential_name: str) -> dict:
        value = {"schema": HANDLE_SCHEMA, "credential_ref": credential_ref,
                 "credential_name": credential_name, "owner_ref": owner_ref}
        value["record_sha256"] = canonical_sha256(value)
        return value

    def _read(self, path: Path, owner_ref: str) -> CredentialHandle:
        if not path.is_file():
            raise CredentialHandleError()
        _secure_owner_only(path, directory=False)
        value = strict_load_json(path.read_bytes(), max_depth=4)
        digest = canonical_sha256({key: item for key, item in value.items()
                                   if key != "record_sha256"})
        if (set(value) != _RECORD_FIELDS or value.get("schema") != HANDLE_SCHEMA
                or value.get("owner_ref") != owner_ref
                or not self._valid_ref(value.get("credential_ref"))
                or not self._valid_slot(value.get("credential_name"))
                or value.get("record_sha256") != digest):
            raise CredentialHandleError()
        return CredentialHandle(value["credential_ref"], value["credential_name"])

    def _keychain_value(self, credential_name: str) -> str:
        try:
            value = self._keychain_get(credential_name)
        except Exception:
            raise CredentialHandleError() from None
        if type(value) is not str or not value:
            raise CredentialHandleError()
        return value

    @staticmethod
    def _replace(path: Path, value: dict) -> None:
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as stream:
                _secure_owner_only(temporary, directory=False)
                stream.write(canonical_bytes(value))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            _secure_owner_only(path, directory=False)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
