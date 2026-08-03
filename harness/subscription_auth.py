"""subscription_auth.py -- consume an already-authorized token, never mint one.

The router sometimes speaks to a provider through a subscription session the
human already opened out of band: a Claude Code login, a ChatGPT session, an
OpenRouter key. That login produced a token. This module is the seam that
READS that token and hands the router the right HTTP header. It is the whole
of the boundary, stated plainly:

  - it performs no OAuth login and no browser dance,
  - it prompts for no password and enters no credential into any form,
  - it never handles a credential in the clear beyond the one read needed to
    build a header, and it never writes, stores, or logs the value.

Every adapter here is read-only. A token arrives from an environment variable,
the OS credential store, or a file a CLI already wrote; presence is reported as
a label ("env:NAME", "keychain:NAME", "file:PATH"), never as the value. The
value appears in exactly one place, an outbound HTTP header, and nowhere else:
AuthToken.__repr__ redacts it to a sha256 prefix so a token cannot leak into a
log, a receipt, or a traceback.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

from . import keychain

_BEARER = "bearer"
_X_API_KEY = "x-api-key"
_SCHEMES = frozenset({_BEARER, _X_API_KEY})


@dataclass(frozen=True, repr=False)
class AuthToken:
    """An authorized token plus where it came from. The value is carried so a
    header can be built, and is redacted everywhere it could be observed."""

    scheme: str
    value: str
    source: str
    expires_at: Optional[int] = None

    def header(self) -> tuple[str, str]:
        """The HTTP header pair for this scheme. Bearer tokens go on
        Authorization; an x-api-key token is its own header."""
        if self.scheme == _BEARER:
            return ("Authorization", f"Bearer {self.value}")
        if self.scheme == _X_API_KEY:
            return ("x-api-key", self.value)
        raise ValueError(f"unknown auth scheme: {self.scheme!r}")

    def expired(self, now: Optional[int] = None) -> bool:
        """True only when an expiry is known and has passed. No expiry means
        this seam cannot judge it, so it does not pretend to (returns False)."""
        if self.expires_at is None:
            return False
        return int(now if now is not None else time.time()) >= self.expires_at

    def _fingerprint(self) -> str:
        return hashlib.sha256(self.value.encode("utf-8")).hexdigest()[:12]

    def __repr__(self) -> str:
        # The value never appears: only its source, scheme, and a short
        # sha256 prefix that identifies it without disclosing it.
        return (f"AuthToken(scheme={self.scheme!r}, source={self.source!r}, "
                f"sha256={self._fingerprint()})")

    __str__ = __repr__


@runtime_checkable
class AuthAdapter(Protocol):
    """A read-only source of an already-authorized token."""

    def resolve(self) -> Optional[AuthToken]:
        """The token if one is authorized and present, else None."""
        ...

    def source_label(self) -> str:
        """Where the token would come from, presence only, never the value."""
        ...


class EnvTokenAdapter:
    """Reads a token from an environment variable, with the OS credential
    store as the backing source (keychain.resolve_credential order: env wins,
    keychain backs it). Read-only: it never writes either surface."""

    def __init__(self, env_name: str, scheme: str = _BEARER):
        self.env_name = env_name
        self.scheme = scheme

    def resolve(self) -> Optional[AuthToken]:
        value = keychain.resolve_credential(self.env_name)
        if not value:
            return None
        src = keychain.credential_source(self.env_name)
        return AuthToken(self.scheme, value, f"{src}:{self.env_name}")

    def source_label(self) -> str:
        return f"{keychain.credential_source(self.env_name)}:{self.env_name}"


class KeychainTokenAdapter:
    """Reads a token straight from the OS credential store. Read-only."""

    def __init__(self, name: str, scheme: str = _BEARER):
        self.name = name
        self.scheme = scheme

    def resolve(self) -> Optional[AuthToken]:
        value = keychain.keychain_get(self.name)
        if not value:
            return None
        return AuthToken(self.scheme, value, f"keychain:{self.name}")

    def source_label(self) -> str:
        present = bool(keychain.keychain_get(self.name))
        return f"{'keychain' if present else 'absent'}:{self.name}"


class TokenFileAdapter:
    """Reads a token a CLI already wrote to a file. With `field`, the file is
    parsed as JSON and that field is read; without it, the whole file text is
    the token. A missing file is a quiet None. It never writes the file."""

    def __init__(self, path, field: Optional[str] = None,
                 scheme: str = _BEARER):
        self.path = Path(path)
        self.field = field
        self.scheme = scheme

    def _read_value(self) -> Optional[str]:
        try:
            text = self.path.read_text(encoding="utf-8")
        except (FileNotFoundError, NotADirectoryError, IsADirectoryError,
                PermissionError, OSError):
            return None
        if self.field is None:
            value = text.strip()
            return value or None
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            return None
        value = data.get(self.field) if isinstance(data, dict) else None
        if not isinstance(value, str) or not value:
            return None
        return value

    def resolve(self) -> Optional[AuthToken]:
        value = self._read_value()
        if not value:
            return None
        return AuthToken(self.scheme, value, f"file:{self.path}")

    def source_label(self) -> str:
        present = self._read_value() is not None
        return f"{'file' if present else 'absent'}:{self.path}"


class ChainAdapter:
    """Tries adapters in order and returns the first token one produces. The
    order encodes preference: a subscription session token before a raw key."""

    def __init__(self, adapters):
        self.adapters = list(adapters)

    def resolve(self) -> Optional[AuthToken]:
        for adapter in self.adapters:
            token = adapter.resolve()
            if token is not None:
                return token
        return None

    def source_label(self) -> str:
        for adapter in self.adapters:
            if adapter.resolve() is not None:
                return adapter.source_label()
        return "absent"


class AuthResolver:
    """Maps a provider name to the adapter that authenticates it. resolve
    hands back a token or None; source is the presence label for a receipt."""

    def __init__(self, adapters: Optional[dict] = None):
        self._adapters: dict = dict(adapters or {})

    def register(self, provider: str, adapter: AuthAdapter) -> "AuthResolver":
        self._adapters[provider] = adapter
        return self

    def resolve(self, provider: str) -> Optional[AuthToken]:
        adapter = self._adapters.get(provider)
        return adapter.resolve() if adapter is not None else None

    def source(self, provider: str) -> str:
        adapter = self._adapters.get(provider)
        return adapter.source_label() if adapter is not None else "absent"

    def providers(self) -> list:
        return sorted(self._adapters)


def default_auth_resolver() -> AuthResolver:
    """Wire the known subscription sources. Each provider prefers the token
    the user's authorized login produced, then falls back to a raw key.

      anthropic      CLAUDE_CODE_OAUTH_TOKEN (bearer) -> ANTHROPIC_API_KEY
      qwen-anthropic ANTHROPIC_AUTH_TOKEN (bearer)    -> DASHSCOPE_API_KEY
      openrouter     OPENROUTER_API_KEY (bearer)
    """
    return AuthResolver({
        "anthropic": ChainAdapter([
            EnvTokenAdapter("CLAUDE_CODE_OAUTH_TOKEN", _BEARER),
            EnvTokenAdapter("ANTHROPIC_API_KEY", _X_API_KEY),
        ]),
        "qwen-anthropic": ChainAdapter([
            EnvTokenAdapter("ANTHROPIC_AUTH_TOKEN", _BEARER),
            EnvTokenAdapter("DASHSCOPE_API_KEY", _BEARER),
        ]),
        "openrouter": EnvTokenAdapter("OPENROUTER_API_KEY", _BEARER),
    })
