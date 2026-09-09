"""Native keychain custody helpers for Bulletin identity setup."""
from __future__ import annotations

from contextlib import AbstractContextManager
import os
from pathlib import Path
from typing import Callable

from .bulletin_identity_contract import (
    BULLETIN_CREDENTIAL_NAME,
    BulletinIdentityError,
)
from .bulletin_identity_key import (
    BulletinIdentity,
    generate_identity_json,
    parse_identity_json,
)
from .journey_lock import JourneyLockBusy


def keychain_status(
        credential_source: Callable[[str], str] | None = None) -> dict:
    source = _credential_source(credential_source, BULLETIN_CREDENTIAL_NAME)
    return {"credential_name": BULLETIN_CREDENTIAL_NAME, "source": source,
            "action": "not_requested"}


def load_identity_from_keychain(
        *, credential_source: Callable[[str], str] | None = None,
        keychain_get: Callable[[str], str | None] | None = None
) -> tuple[BulletinIdentity, dict]:
    source = _credential_source(credential_source, BULLETIN_CREDENTIAL_NAME)
    if source == "env":
        raise BulletinIdentityError("ENV_CREDENTIAL_PRESENT")
    raw = _keychain_get(keychain_get, BULLETIN_CREDENTIAL_NAME)
    if not raw:
        raise BulletinIdentityError("NATIVE_IDENTITY_MISSING")
    identity = _parse_keychain_identity(raw)
    return identity, {"credential_name": BULLETIN_CREDENTIAL_NAME,
                      "source": "keychain", "action": "reused",
                      "thumbprint": identity.thumbprint}


def store_identity_in_keychain(
        identity: BulletinIdentity, *,
        credential_source: Callable[[str], str] | None = None,
        keychain_get: Callable[[str], str | None] | None = None,
        keychain_set: Callable[[str, str], dict] | None = None,
        keychain_lock: Callable[[str], AbstractContextManager] | None = None,
        keychain_lock_root: str | Path | None = None) -> dict:
    try:
        with _lock_context(BULLETIN_CREDENTIAL_NAME, keychain_lock, keychain_lock_root):
            _refuse_env_source(credential_source)
            existing = _keychain_get(keychain_get, BULLETIN_CREDENTIAL_NAME)
            if existing:
                current = _parse_keychain_identity(existing)
                if current.thumbprint == identity.thumbprint:
                    return _stored("already_present", identity.thumbprint)
                raise BulletinIdentityError("KEYCHAIN_VALUE_MISMATCH")
            _set_keychain_value(keychain_set, identity.raw_json)
            _verify_stored_identity(identity, keychain_get)
            return _stored("stored", identity.thumbprint)
    except JourneyLockBusy:
        raise BulletinIdentityError("STORE_BUSY") from None
    except OSError:
        raise BulletinIdentityError("KEYCHAIN_WRITE_FAILED") from None


def create_identity_in_keychain(
        *, credential_source: Callable[[str], str] | None = None,
        keychain_get: Callable[[str], str | None] | None = None,
        keychain_set: Callable[[str, str], dict] | None = None,
        keychain_lock: Callable[[str], AbstractContextManager] | None = None,
        keychain_lock_root: str | Path | None = None,
        generate_key_json: Callable[[], str] | None = None
) -> tuple[BulletinIdentity, dict]:
    try:
        with _lock_context(BULLETIN_CREDENTIAL_NAME, keychain_lock, keychain_lock_root):
            _refuse_env_source(credential_source)
            if _keychain_get(keychain_get, BULLETIN_CREDENTIAL_NAME):
                raise BulletinIdentityError("KEYCHAIN_VALUE_EXISTS")
            raw = (generate_key_json or generate_identity_json)()
            identity = parse_identity_json(raw, invalid_code="GENERATED_KEY_INVALID")
            _set_keychain_value(keychain_set, identity.raw_json)
            _verify_stored_identity(identity, keychain_get)
            return identity, _stored("created_stored", identity.thumbprint)
    except JourneyLockBusy:
        raise BulletinIdentityError("STORE_BUSY") from None
    except OSError:
        raise BulletinIdentityError("KEYCHAIN_WRITE_FAILED") from None


def delete_identity_keychain_slot(
        *, keychain_delete: Callable[[str], dict] | None = None,
        keychain_lock: Callable[[str], AbstractContextManager] | None = None,
        keychain_lock_root: str | Path | None = None) -> dict:
    try:
        with _lock_context(BULLETIN_CREDENTIAL_NAME, keychain_lock, keychain_lock_root):
            deleter = keychain_delete
            if deleter is None:
                from .keychain import keychain_delete as deleter
            out = deleter(BULLETIN_CREDENTIAL_NAME)
            if not isinstance(out, dict):
                return _delete_error("KEYCHAIN_DELETE_FAILED",
                                     "bulletin identity keychain delete failed")
            return out
    except JourneyLockBusy:
        return _delete_error("STORE_BUSY", "bulletin identity keychain slot is busy")
    except OSError:
        return _delete_error("KEYCHAIN_DELETE_FAILED",
                             "bulletin identity keychain delete failed")


def bind_identity_handle(
        identity: BulletinIdentity, owner_ref: str, *,
        state_root: str | Path | None = None,
        keychain_get: Callable[[str], str | None] | None = None,
        token_hex: Callable[[int], str] | None = None) -> dict:
    require_keychain_thumbprint(identity, keychain_get=keychain_get)
    if state_root is None:
        state_root = Path.home() / ".flywheel" / "state"
    try:
        from .credential_handles import CredentialHandleError, CredentialHandleStore
        kwargs = {"keychain_get": _getter(keychain_get)}
        if token_hex is not None:
            kwargs["token_hex"] = token_hex
        handle = CredentialHandleStore(Path(state_root), **kwargs).bind(
            owner_ref, BULLETIN_CREDENTIAL_NAME)
    except CredentialHandleError as exc:
        raise BulletinIdentityError(exc.code) from None
    except (OSError, TypeError, ValueError):
        raise BulletinIdentityError("CREDENTIAL_HANDLE_UNAVAILABLE") from None
    return {"credential_ref": handle.credential_ref,
            "credential_name": handle.credential_name}


def require_keychain_thumbprint(
        identity: BulletinIdentity, *,
        keychain_get: Callable[[str], str | None] | None = None) -> None:
    raw = _keychain_get(keychain_get, BULLETIN_CREDENTIAL_NAME)
    if not raw:
        raise BulletinIdentityError("NATIVE_IDENTITY_MISSING")
    stored = _parse_keychain_identity(raw)
    if stored.thumbprint != identity.thumbprint:
        raise BulletinIdentityError("KEYCHAIN_VALUE_MISMATCH")


def _verify_stored_identity(
        identity: BulletinIdentity,
        keychain_get: Callable[[str], str | None] | None) -> None:
    raw = _keychain_get(keychain_get, BULLETIN_CREDENTIAL_NAME)
    if not raw:
        raise BulletinIdentityError("KEYCHAIN_WRITE_FAILED")
    stored = _parse_keychain_identity(raw)
    if stored.thumbprint != identity.thumbprint:
        raise BulletinIdentityError("KEYCHAIN_VALUE_MISMATCH")


def _parse_keychain_identity(raw: str) -> BulletinIdentity:
    try:
        return parse_identity_json(raw, invalid_code="KEYCHAIN_VALUE_INVALID")
    except BulletinIdentityError as exc:
        if exc.code == "SIGNING_UNAVAILABLE":
            raise
        raise BulletinIdentityError("KEYCHAIN_VALUE_INVALID") from None


def _set_keychain_value(
        keychain_set: Callable[[str, str], dict] | None, value: str) -> None:
    setter = keychain_set
    if setter is None:
        from .keychain import keychain_set as setter
    out = setter(BULLETIN_CREDENTIAL_NAME, value)
    if not isinstance(out, dict) or out.get("stored") != BULLETIN_CREDENTIAL_NAME:
        raise BulletinIdentityError("KEYCHAIN_WRITE_FAILED")


def _refuse_env_source(credential_source: Callable[[str], str] | None) -> None:
    if _credential_source(credential_source, BULLETIN_CREDENTIAL_NAME) == "env":
        raise BulletinIdentityError("ENV_CREDENTIAL_PRESENT")


def _credential_source(
        credential_source: Callable[[str], str] | None, name: str) -> str:
    source = credential_source
    if source is None:
        from .keychain import credential_source as source
    value = source(name)
    return value if value in {"env", "keychain", "absent"} else "absent"


def _keychain_get(
        keychain_get: Callable[[str], str | None] | None, name: str) -> str | None:
    return _getter(keychain_get)(name)


def _getter(keychain_get: Callable[[str], str | None] | None):
    if keychain_get is not None:
        return keychain_get
    from .keychain import keychain_get as getter
    return getter


def _lock_context(
        name: str, keychain_lock: Callable[[str], AbstractContextManager] | None,
        root: str | Path | None) -> AbstractContextManager:
    if keychain_lock is not None:
        return keychain_lock(name)
    from .journey_lock import ExclusiveJourneyLock
    base = Path(root) if root is not None else Path(
        os.environ.get("FLYWHEEL_HOME", str(Path.home() / ".flywheel"))) / "state"
    return ExclusiveJourneyLock.acquire(base / "credential-locks" / f"{name}.lock")


def _stored(action: str, thumbprint: str) -> dict:
    return {"credential_name": BULLETIN_CREDENTIAL_NAME, "source": "keychain",
            "action": action, "thumbprint": thumbprint}


def _delete_error(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}
