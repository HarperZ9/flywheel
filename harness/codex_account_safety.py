"""Sanitizers and trust checks for Codex account route helpers."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

SCHEMA = "flywheel.codex-account-route/v1"
PROVIDER = "codex"
TRANSPORT = "codex-app-server"
DEFAULT_ALLOWED_LOGIN_HOSTS = ("openai.com", "chatgpt.com")
_FORBIDDEN_QUERY_NAMES = ("token", "secret", "password", "credential", "api_key")
_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{8,}", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{8,}", re.IGNORECASE),
    re.compile(r"(access|refresh|id)[_-]?token=[^&\s]+", re.IGNORECASE),
)


def route_payload() -> dict:
    return {"schema": SCHEMA, "provider": PROVIDER, "transport": TRANSPORT}


def redact(value: str) -> str:
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub("[redacted]", value)
    return value


def secret_shaped(value: str) -> bool:
    return any(pattern.search(value) for pattern in _SECRET_PATTERNS)


def public_string(value: Any, *, limit: int = 240) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = "".join(
        " " if (ch.isspace() or ord(ch) < 32 or ord(ch) == 127) else ch
        for ch in value)
    return redact(cleaned.strip())[:limit]


def safe_error(exc: BaseException | str) -> str:
    if isinstance(exc, BaseException):
        return type(exc).__name__
    return public_string(exc, limit=160) or "unknown"


def owner_ref(value: Any) -> str:
    owner = public_string(value, limit=128)
    if not owner:
        raise ValueError("owner required")
    return owner


def login_id(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("login id required")
    if len(value) > 256 or "\\" in value:
        raise ValueError("login id invalid")
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError("login id invalid")
    if secret_shaped(value):
        raise ValueError("login id invalid")
    return value


def _host_allowed(hostname: str, allowed_hosts: tuple[str, ...]) -> bool:
    host = hostname.lower().rstrip(".")
    for allowed in allowed_hosts:
        base = allowed.lower().rstrip(".")
        if host == base or host.endswith("." + base):
            return True
    return False


def trusted_login_url(value: Any, allowed_hosts: tuple[str, ...]) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("missing login URL")
    if "\\" in value:
        raise ValueError("login URL invalid")
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError("login URL invalid")
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise ValueError("login URL invalid") from exc
    if parsed.scheme != "https" or parsed.username or parsed.password:
        raise ValueError("login URL invalid")
    if not parsed.hostname or not _host_allowed(parsed.hostname, allowed_hosts):
        raise ValueError("login URL host not allowed")
    if secret_shaped(value):
        raise ValueError("login URL contains credential-shaped data")
    query = parsed.query.lower()
    if any(name in query for name in _FORBIDDEN_QUERY_NAMES):
        raise ValueError("login URL contains credential-shaped data")
    return value
