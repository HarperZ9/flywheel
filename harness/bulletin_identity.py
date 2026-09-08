"""Native-custody setup helpers for the Bulletin signing identity."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .bulletin_identity_contract import (
    BULLETIN_CREDENTIAL_NAME,
    DEFAULT_BASE_URL,
    DEFAULT_HANDLE,
    DEFAULT_TIMEOUT,
    ERROR_SCHEMA,
    IDENTITY_SCHEMA,
    MAX_KEY_BYTES,
    MAX_POW_BITS,
    PREPARE_SCHEMA,
    BulletinIdentityError,
    BulletinIdentityHttpError,
    error_body,
)
from .bulletin_identity_key import (
    BulletinIdentity,
    generate_identity_json,
    load_identity_file,
    normalize_handle,
    parse_identity_json,
)
from .bulletin_identity_network import agent_status, register_or_reuse
from .bulletin_identity_origin import (
    ALLOWED_BULLETIN_ORIGINS,
    validate_bulletin_base_url,
)
from .bulletin_identity_store import (
    bind_identity_handle,
    create_identity_in_keychain,
    keychain_status,
    load_identity_from_keychain,
    store_identity_in_keychain,
)


def prepare_identity(
        key_path: str | Path | None = None, *, base_url: str = DEFAULT_BASE_URL,
        handle: str = DEFAULT_HANDLE, create: bool = False,
        register: bool = False, store_keychain: bool = False,
        bind_owner: str | None = None, state_root: str | Path | None = None,
        allow_loopback: bool = False, timeout: int = DEFAULT_TIMEOUT,
        max_pow_bits: int = MAX_POW_BITS,
        http_get_json: Callable[..., dict] | None = None,
        signed_post_json: Callable[[str, dict], dict] | None = None,
        credential_source: Callable[[str], str] | None = None,
        keychain_get: Callable[[str], str | None] | None = None,
        keychain_set: Callable[[str, str], dict] | None = None,
        token_hex: Callable[[int], str] | None = None,
        generate_key_json: Callable[[], str] | None = None,
        keychain_lock: Callable[[str], object] | None = None,
        keychain_lock_root: str | Path | None = None) -> dict:
    base = validate_bulletin_base_url(base_url, allow_loopback=allow_loopback)
    clean_handle = normalize_handle(handle)
    identity, keychain = _identity_and_keychain(
        key_path, create=create, store_keychain=store_keychain,
        credential_source=credential_source, keychain_get=keychain_get,
        keychain_set=keychain_set, generate_key_json=generate_key_json,
        keychain_lock=keychain_lock, keychain_lock_root=keychain_lock_root)
    credential_handle = None
    if bind_owner:
        credential_handle = bind_identity_handle(
            identity, bind_owner, state_root=state_root, keychain_get=keychain_get,
            token_hex=token_hex)
    board = agent_status(
        base, identity.thumbprint, http_get_json=http_get_json, timeout=timeout)
    registration = {"requested": bool(register), "action": "not_requested"}
    if register:
        registration = register_or_reuse(
            identity, base, clean_handle, known_status=board,
            http_get_json=http_get_json, signed_post_json=signed_post_json,
            timeout=timeout, max_pow_bits=max_pow_bits)
        if registration.get("registered"):
            board = {"registered": True,
                     "handle": registration.get("handle", clean_handle),
                     "tier": registration.get("tier", "")}
    result = identity.public_summary(handle=clean_handle)
    result.update({"schema": PREPARE_SCHEMA, "base_url": base, "board": board,
                   "registration": registration, "keychain": keychain})
    if credential_handle is not None:
        result["credential_handle"] = credential_handle
    return result


def _identity_and_keychain(
        key_path: str | Path | None, *, create: bool, store_keychain: bool,
        credential_source: Callable[[str], str] | None,
        keychain_get: Callable[[str], str | None] | None,
        keychain_set: Callable[[str, str], dict] | None,
        generate_key_json: Callable[[], str] | None,
        keychain_lock: Callable[[str], object] | None,
        keychain_lock_root: str | Path | None) -> tuple[BulletinIdentity, dict]:
    if create and key_path is not None:
        raise BulletinIdentityError("CREATE_WITH_KEY_UNSUPPORTED")
    if create and not store_keychain:
        raise BulletinIdentityError("CREATE_REQUIRES_STORE")
    if create:
        return create_identity_in_keychain(
            credential_source=credential_source, keychain_get=keychain_get,
            keychain_set=keychain_set, keychain_lock=keychain_lock,
            keychain_lock_root=keychain_lock_root,
            generate_key_json=generate_key_json)
    if key_path is None:
        return load_identity_from_keychain(
            credential_source=credential_source, keychain_get=keychain_get)
    identity = load_identity_file(key_path)
    if store_keychain:
        keychain = store_identity_in_keychain(
            identity, credential_source=credential_source,
            keychain_get=keychain_get, keychain_set=keychain_set,
            keychain_lock=keychain_lock, keychain_lock_root=keychain_lock_root)
    else:
        keychain = keychain_status(credential_source)
    return identity, keychain
