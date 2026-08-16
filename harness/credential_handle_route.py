"""Always-private transport helpers for opaque credential handles."""
from __future__ import annotations

from pathlib import Path
import secrets
from typing import Callable

from .credential_handles import (
    HANDLE_SCHEMA, CredentialHandleError, CredentialHandleStore,
)
from .evidence_json import strict_load_json
from .evidence_public import TransportError, error_response
from .keychain import keychain_get as os_keychain_get

BIND_SCHEMA = "flywheel.credential-handle-bind/v1"
LIST_SCHEMA = "flywheel.credential-handle-list/v1"


def _response_error(exc: Exception) -> tuple[dict, int]:
    code = getattr(exc, "code", "PERMISSION_REQUIRED")
    if code == "INVALID_REQUEST":
        return error_response(TransportError(
            code, "credential handle request is invalid", 422))
    if code == "STORE_BUSY":
        return error_response(TransportError(
            code, "credential handle store is unavailable", 503))
    if code == "NOT_FOUND":
        return error_response(TransportError(
            code, "credential handle route was not found", 404))
    return error_response(TransportError(
        "PERMISSION_REQUIRED", "credential handle is unavailable", 403))


def credential_handle_post(
        path: str, raw: bytes | str, *, owner_ref: str, state_root: Path,
        keychain_get: Callable[[str], str | None] = os_keychain_get,
        token_hex: Callable[[int], str] = secrets.token_hex) -> tuple[dict, int]:
    """Bind one safe slot name to a new owner-scoped opaque handle."""
    try:
        if path != "/api/credential-handles/bind":
            raise CredentialHandleError("NOT_FOUND")
        body = strict_load_json(raw, max_bytes=16_384, max_depth=4)
        if (set(body) != {"schema", "credential_name"}
                or body.get("schema") != BIND_SCHEMA):
            raise CredentialHandleError("INVALID_REQUEST")
        handle = CredentialHandleStore(
            state_root, keychain_get=keychain_get, token_hex=token_hex,
        ).bind(owner_ref, body.get("credential_name"))
        return {"schema": HANDLE_SCHEMA,
                "credential_ref": handle.credential_ref,
                "credential_name": handle.credential_name}, 200
    except CredentialHandleError as exc:
        return _response_error(exc)
    except (OSError, TypeError, ValueError, UnicodeError, RecursionError):
        return _response_error(CredentialHandleError("INVALID_REQUEST"))


def credential_handle_get(
        path: str, *, owner_ref: str, state_root: Path) -> tuple[dict, int]:
    """List only opaque refs and safe labels for the authenticated owner."""
    try:
        if path != "/api/credential-handles":
            raise CredentialHandleError("NOT_FOUND")
        handles = CredentialHandleStore(
            state_root, keychain_get=lambda _name: None,
        ).list_handles(owner_ref)
        return {"schema": LIST_SCHEMA, "handles": [
            {"credential_ref": item.credential_ref,
             "credential_name": item.credential_name}
            for item in handles
        ]}, 200
    except CredentialHandleError as exc:
        return _response_error(exc)
    except (OSError, TypeError, ValueError):
        return _response_error(CredentialHandleError())
