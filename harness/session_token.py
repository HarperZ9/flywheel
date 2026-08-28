"""Session tokens: scoped, time-bounded credential derivation.

An agent session gets a token that resolves to real credentials only within
its TTL and only for the bound session. The raw credential value never
appears in the token, its repr, or any error message. Expired tokens are
reaped lazily on list/reap calls.
"""
from __future__ import annotations

import secrets
import time
import threading
from dataclasses import dataclass

from .credential_handles import (
    CredentialBindings, CredentialHandleStore, CredentialHandleError,
)

TOKEN_REF_PREFIX = "stok_"


class SessionTokenError(RuntimeError):
    def __init__(self, code: str = "INVALID_TOKEN") -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class SessionToken:
    token_ref: str
    credential_refs: tuple[str, ...]
    required_slots: tuple[str, ...]
    owner_ref: str
    session_ref: str
    created_at: float
    expires_at: float
    revoked: bool = False

    def __repr__(self) -> str:
        state = "revoked" if self.revoked else (
            "expired" if time.time() > self.expires_at else "active")
        return (f"SessionToken({self.token_ref!r}, session={self.session_ref!r}, "
                f"state={state}, slots={len(self.required_slots)})")

    def active(self) -> bool:
        return not self.revoked and time.time() <= self.expires_at


class SessionTokenStore:
    def __init__(self, handle_store: CredentialHandleStore) -> None:
        self._handle_store = handle_store
        self._tokens: dict[str, SessionToken] = {}
        self._lock = threading.Lock()

    def mint(
        self,
        owner_ref: str,
        session_ref: str,
        credential_refs: list[str] | tuple[str, ...],
        required_slots: list[str] | tuple[str, ...],
        ttl_seconds: int,
    ) -> SessionToken:
        try:
            actual_slots = self._handle_store.slot_names_exact(
                owner_ref, list(credential_refs))
        except CredentialHandleError:
            raise SessionTokenError("INVALID_CREDENTIAL") from None
        required_set = set(required_slots)
        actual_set = set(actual_slots)
        if not required_set.issubset(actual_set):
            raise SessionTokenError("SLOT_MISMATCH")
        now = time.time()
        token_ref = f"{TOKEN_REF_PREFIX}{secrets.token_hex(16)}"
        token = SessionToken(
            token_ref=token_ref,
            credential_refs=tuple(credential_refs),
            required_slots=tuple(required_slots),
            owner_ref=owner_ref,
            session_ref=session_ref,
            created_at=now,
            expires_at=now + ttl_seconds,
        )
        with self._lock:
            self._tokens[token_ref] = token
        return token

    def resolve(
        self, token_ref: str, owner_ref: str, session_ref: str,
    ) -> CredentialBindings:
        with self._lock:
            token = self._tokens.get(token_ref)
        if token is None:
            raise SessionTokenError("INVALID_TOKEN")
        if token.owner_ref != owner_ref:
            raise SessionTokenError("INVALID_TOKEN")
        if token.session_ref != session_ref:
            raise SessionTokenError("SESSION_MISMATCH")
        if token.revoked:
            raise SessionTokenError("REVOKED")
        if time.time() > token.expires_at:
            raise SessionTokenError("EXPIRED")
        try:
            return self._handle_store.resolve_exact(
                owner_ref, list(token.credential_refs),
                list(token.required_slots))
        except CredentialHandleError:
            raise SessionTokenError("CREDENTIAL_UNAVAILABLE") from None

    def revoke(self, token_ref: str, owner_ref: str) -> bool:
        with self._lock:
            token = self._tokens.get(token_ref)
            if token is None or token.owner_ref != owner_ref:
                return False
            revoked = SessionToken(
                token_ref=token.token_ref,
                credential_refs=token.credential_refs,
                required_slots=token.required_slots,
                owner_ref=token.owner_ref,
                session_ref=token.session_ref,
                created_at=token.created_at,
                expires_at=token.expires_at,
                revoked=True,
            )
            self._tokens[token_ref] = revoked
            return True

    def list_active(self, owner_ref: str) -> tuple[SessionToken, ...]:
        now = time.time()
        with self._lock:
            return tuple(
                t for t in self._tokens.values()
                if t.owner_ref == owner_ref and not t.revoked
                and now <= t.expires_at
            )

    def reap(self) -> int:
        now = time.time()
        with self._lock:
            expired = [ref for ref, t in self._tokens.items()
                       if t.revoked or now > t.expires_at]
            for ref in expired:
                del self._tokens[ref]
            return len(expired)
