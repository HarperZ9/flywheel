"""Gateway route helpers for native Bulletin identity setup."""
from __future__ import annotations

from importlib import import_module
from importlib.util import find_spec
from pathlib import Path
from typing import Any, Callable

from .bulletin_identity_contract import (
    BULLETIN_CREDENTIAL_NAME,
    DEFAULT_BASE_URL,
    DEFAULT_HANDLE,
    MAX_POW_BITS,
    BulletinIdentityError,
    error_body,
)

STATUS_SCHEMA = "flywheel.bulletin-identity-status/v1"
CREATE_REQUEST_SCHEMA = "flywheel.bulletin-identity-create-request/v1"
REGISTER_REQUEST_SCHEMA = "flywheel.bulletin-identity-register-request/v1"


def bulletin_identity_get(
        *, credential_source: Callable[[str], str] | None = None,
        keychain_available_fn: Callable[[], bool] | None = None,
        signing_available_fn: Callable[[], bool] | None = None) -> tuple[dict[str, Any], int]:
    """Local status only: source/capability facts, no board/network check."""
    source = _source(credential_source)
    keychain_available = _keychain_available(keychain_available_fn)
    signing_available = _signing_available(signing_available_fn)
    return _status(source, keychain_available, signing_available), 200


def bulletin_identity_create_post(
        req: dict[str, Any], flywheel_home: Path, *,
        credential_source: Callable[[str], str] | None = None,
        keychain_available_fn: Callable[[], bool] | None = None,
        signing_available_fn: Callable[[], bool] | None = None,
        create_identity: Callable[..., tuple[object, dict]] | None = None
) -> tuple[dict[str, Any], int]:
    if not _confirmed(req, CREATE_REQUEST_SCHEMA, "create", "confirm_create"):
        return error_body("INVALID_REQUEST"), 400
    source = _source(credential_source)
    unavailable = _unavailable(source, keychain_available_fn, signing_available_fn)
    if unavailable is not None:
        return error_body(unavailable), 400
    creator = create_identity or _create_identity
    try:
        _identity, keychain = creator(
            credential_source=credential_source,
            keychain_lock_root=flywheel_home / "state")
    except BulletinIdentityError as exc:
        return error_body(exc.code), 400
    return _status("keychain", True, True, action=str(keychain.get("action", "created"))), 200


def bulletin_identity_register_post(
        req: dict[str, Any], flywheel_home: Path, *,
        prepare: Callable[..., dict] | None = None,
        keychain_available_fn: Callable[[], bool] | None = None,
        signing_available_fn: Callable[[], bool] | None = None
) -> tuple[dict[str, Any], int]:
    if not _confirmed(req, REGISTER_REQUEST_SCHEMA, "register", "confirm_register"):
        return error_body("INVALID_REQUEST"), 400
    unavailable = _unavailable("keychain", keychain_available_fn, signing_available_fn)
    if unavailable is not None:
        return error_body(unavailable), 400
    preparer = prepare or _prepare_identity
    try:
        result = preparer(
            base_url=DEFAULT_BASE_URL,
            handle=DEFAULT_HANDLE,
            create=False,
            register=True,
            store_keychain=False,
            bind_owner=None,
            state_root=flywheel_home / "state",
            allow_loopback=False,
            max_pow_bits=MAX_POW_BITS,
            keychain_lock_root=flywheel_home / "state",
        )
    except BulletinIdentityError as exc:
        return error_body(exc.code), 400
    registration = _registration(result.get("registration"))
    board = _board(result.get("board"))
    action = registration.get("action") or "registered"
    body = _status("keychain", True, True, action=action)
    body["registration"] = registration
    body["board"] = board
    return body, 200


def _confirmed(req: dict[str, Any], schema: str, action: str, confirm: str) -> bool:
    return (
        isinstance(req, dict)
        and set(req) == {"schema", "action", confirm}
        and req.get("schema") == schema
        and req.get("action") == action
        and req.get(confirm) is True
    )


def _status(
        source: str, keychain_available: bool, signing_available: bool, *,
        action: str | None = None) -> dict[str, Any]:
    unavailable = _availability_reason(source, keychain_available, signing_available)
    body: dict[str, Any] = {
        "schema": STATUS_SCHEMA,
        "credential_name": BULLETIN_CREDENTIAL_NAME,
        "source": source,
        "keychain_available": keychain_available,
        "signing_available": signing_available,
        "create_available": unavailable is None and source == "absent",
        "register_available": unavailable is None and source == "keychain",
        "unavailable_reason": unavailable,
    }
    if action is not None:
        body["action"] = action
    return body


def _availability_reason(source: str, keychain_available: bool, signing_available: bool) -> str | None:
    if source == "env":
        return "ENV_CREDENTIAL_PRESENT"
    if not keychain_available:
        return "KEYCHAIN_UNAVAILABLE"
    if not signing_available:
        return "SIGNING_UNAVAILABLE"
    return None


def _unavailable(
        source: str, keychain_available_fn: Callable[[], bool] | None,
        signing_available_fn: Callable[[], bool] | None) -> str | None:
    return _availability_reason(
        source, _keychain_available(keychain_available_fn),
        _signing_available(signing_available_fn))


def _source(credential_source: Callable[[str], str] | None) -> str:
    source = credential_source
    if source is None:
        from .keychain import credential_source as source
    value = source(BULLETIN_CREDENTIAL_NAME)
    return value if value in {"env", "keychain", "absent"} else "absent"


def _keychain_available(fn: Callable[[], bool] | None) -> bool:
    if fn is not None:
        return bool(fn())
    from .keychain import keychain_available
    return bool(keychain_available())


def _signing_available(fn: Callable[[], bool] | None) -> bool:
    if fn is not None:
        return bool(fn())
    try:
        if find_spec("cryptography") is None:
            return False
        import_module("cryptography.hazmat.primitives.serialization")
        import_module("cryptography.hazmat.primitives.asymmetric.ed25519")
        return True
    except (ImportError, OSError, ValueError):
        return False


def _create_identity(**kwargs):
    from .bulletin_identity_store import create_identity_in_keychain
    return create_identity_in_keychain(**kwargs)


def _prepare_identity(**kwargs):
    from .bulletin_identity import prepare_identity
    return prepare_identity(**kwargs)


def _registration(value: object) -> dict[str, object]:
    src = value if isinstance(value, dict) else {}
    out: dict[str, object] = {}
    for key in ("requested", "registered"):
        if isinstance(src.get(key), bool):
            out[key] = src[key]
    for key in ("action", "handle", "tier"):
        if isinstance(src.get(key), str):
            out[key] = src[key]
    return out


def _board(value: object) -> dict[str, object]:
    src = value if isinstance(value, dict) else {}
    out: dict[str, object] = {}
    if isinstance(src.get("registered"), bool):
        out["registered"] = src["registered"]
    for key in ("handle", "tier"):
        if isinstance(src.get(key), str):
            out[key] = src[key]
    return out
