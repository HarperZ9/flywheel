"""gateway_auth.py -- the gateway is not public, and localhost is not a wall.

The gateway exposes routes that write keychain entries, register MCP servers by
argv, install packages, and run an edit-and-execute agent loop. Binding
127.0.0.1 stops remote hosts and nothing else: every local process reaches it,
and a browser that resolves a name to 127.0.0.1 reaches it too unless the Host
header is checked.

Three layers, all cheap:

  1. A bearer token the caller must know. Compared with compare_digest so the
     comparison time does not reveal how much of a guess was right.
  2. A Host allowlist. This is what defeats DNS rebinding, and it does not
     assume the token stayed secret.
  3. A JSON content-type requirement on state-changing methods. A form-encoded
     or text/plain body is a CORS-simple request that any page can send without
     a preflight; requiring application/json forces one.
"""
from __future__ import annotations

import os
import secrets
from hmac import compare_digest
from pathlib import Path
from typing import Mapping

from .operation_grants import load_or_create_owner_ref

TOKEN_FILENAME = "gateway.token"
DEFAULT_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]"})
STATE_CHANGING = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def load_or_create_token(home: Path) -> str:
    """Read the gateway token, minting one on first use. Owner-readable only."""
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    path = home / TOKEN_FILENAME
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    token = secrets.token_urlsafe(32)
    path.write_text(token, encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)
    return token


def _host_of(headers: Mapping) -> str:
    """The host without its port. A bracketed IPv6 literal keeps its brackets."""
    raw = headers.get("Host", "") or ""
    if raw.startswith("["):
        return raw.split("]", 1)[0] + "]"
    return raw.split(":", 1)[0]


def check(headers: Mapping, method: str, token: str, *,
          allowed_hosts: frozenset[str] = DEFAULT_HOSTS) -> tuple[bool, str]:
    """Return (ok, reason). The reason is a stable code, never a secret and
    never an echo of what the caller sent."""
    if _host_of(headers) not in allowed_hosts:
        return False, "bad_host"
    auth = headers.get("Authorization", "") or ""
    if not auth.startswith("Bearer "):
        return False, "no_token"
    if not compare_digest(auth[7:], token):
        return False, "bad_token"
    if method.upper() in STATE_CHANGING:
        ctype = (headers.get("Content-Type", "") or "").split(";", 1)[0].strip()
        if ctype != "application/json":
            return False, "bad_content_type"
    return True, "ok"


def authenticate_owner(headers: Mapping, method: str, token: str, home: Path, *,
                       allowed_hosts: frozenset[str] = DEFAULT_HOSTS
                       ) -> tuple[str | None, str]:
    """Authenticate first, then load token-independent private owner custody."""
    ok, reason = check(
        headers, method, token, allowed_hosts=allowed_hosts)
    if not ok:
        return None, reason
    try:
        return load_or_create_owner_ref(home), "ok"
    except (OSError, PermissionError, TypeError, ValueError):
        return None, "owner_unavailable"
