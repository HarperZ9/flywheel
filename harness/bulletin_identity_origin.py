"""Bulletin origin admission for native identity setup."""
from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

from .bulletin_identity_contract import (
    DEFAULT_BASE_URL,
    BulletinIdentityError,
)

ALLOWED_BULLETIN_ORIGINS = (DEFAULT_BASE_URL,)


def validate_bulletin_base_url(
        value: str | None = None, *, allow_loopback: bool = False,
        allowed_origins: tuple[str, ...] | None = None) -> str:
    raw = (value or DEFAULT_BASE_URL).strip()
    if not raw or "\\" in raw or any(ch.isspace() for ch in raw):
        raise BulletinIdentityError("BASE_URL_UNAVAILABLE")
    try:
        parsed = urlsplit(raw)
    except ValueError:
        raise BulletinIdentityError("BASE_URL_UNAVAILABLE") from None
    if (parsed.username is not None or parsed.password is not None
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment
            or not parsed.netloc or not parsed.hostname):
        raise BulletinIdentityError("BASE_URL_UNAVAILABLE")
    netloc = parsed.netloc.lower()
    origin = f"{parsed.scheme.lower()}://{netloc}"
    allowed = set(allowed_origins or ALLOWED_BULLETIN_ORIGINS)
    if parsed.scheme == "https" and origin in allowed:
        return origin
    if (allow_loopback and parsed.scheme == "http"
            and _loopback_host(parsed.hostname)):
        return origin
    if _blocked_ip_literal(parsed.hostname):
        raise BulletinIdentityError("BASE_URL_UNAVAILABLE")
    raise BulletinIdentityError("BASE_URL_UNAVAILABLE")


def _loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _blocked_ip_literal(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (ip.is_loopback or ip.is_private or ip.is_link_local
            or ip.is_multicast or ip.is_reserved or ip.is_unspecified)
