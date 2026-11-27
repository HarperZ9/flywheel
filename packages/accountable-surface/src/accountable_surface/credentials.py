"""The one door a credential enters through.

Secrets live only in the environment or an explicitly enrolled, namespace-scoped OS
keystore. They never appear in source, in a Plan, in an Observation, in the journal,
in action receipts, or in an error message: a raise names the handle that is missing
and never a value. An effector that needs auth calls `require_secret` or
`resolve_credential_handle` at the moment of the call and puts the result in a
request header or cryptographic signer, never in a URL or witnessed log.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from .keystore import secret_fingerprint

if TYPE_CHECKING:
    from .keystore import KeystoreProtocol


class MissingCredential(RuntimeError):
    """A required credential was not present in the environment or enrolled keystore."""


def _check_header_safe(label: str, value: str) -> str:
    if "\r" in value or "\n" in value:
        raise MissingCredential(f"credential {label} contains a newline")
    return value


def require_secret(name: str) -> str:
    """The named environment variable's value, or raise `MissingCredential`.

    Rejects a value carrying CR or LF: a stray newline (from `export TOKEN=$(cat
    file)`, say) would split or inject a request header.
    """
    value = os.environ.get(name)
    if not value or not value.strip():
        raise MissingCredential(f"missing required credential in environment: {name}")
    if "\r" in value or "\n" in value:
        raise MissingCredential(f"credential in environment variable {name} contains a newline")
    return value


def has_secret(name: str) -> bool:
    """Whether the named credential is present, without revealing it.

    Presence only. This is what a status surface is allowed to report; the value is
    not available to anything but the effector making the call.
    """
    return bool(os.environ.get(name))


def resolve_credential_handle(
    handle: str,
    *,
    keystore: KeystoreProtocol | None = None,
    env_fallback: bool = True,
) -> str:
    """Resolve an opaque credential handle from the enrolled OS keystore or env var."""
    if not handle or not handle.strip():
        raise MissingCredential("empty credential handle")
    if keystore is not None:
        stored = keystore.get(handle)
        if stored and stored.strip():
            return _check_header_safe(f"handle '{handle}'", stored)
    if env_fallback:
        env_val = os.environ.get(handle)
        if env_val and env_val.strip():
            return _check_header_safe(f"in environment variable {handle}", env_val)
    raise MissingCredential(f"missing required credential handle: {handle}")


def has_credential(
    handle: str,
    *,
    keystore: KeystoreProtocol | None = None,
    env_fallback: bool = True,
) -> bool:
    """Check whether a credential handle is enrolled without revealing its value."""
    if not handle or not handle.strip():
        return False
    if keystore is not None and keystore.has(handle):
        return True
    return bool(env_fallback and os.environ.get(handle))


def credential_fingerprint(
    handle: str,
    *,
    keystore: KeystoreProtocol | None = None,
    env_fallback: bool = True,
) -> str | None:
    """Return a non-reversible sha256 fingerprint for a handle, or None if missing."""
    try:
        val = resolve_credential_handle(handle, keystore=keystore, env_fallback=env_fallback)
    except MissingCredential:
        return None
    return secret_fingerprint(val)
