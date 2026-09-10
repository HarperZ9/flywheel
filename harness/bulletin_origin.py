"""Explicit plaintext Bulletin destination binding, independent of credentials."""
from __future__ import annotations

import ipaddress
import os
import re
from urllib.parse import urlsplit

PUBLIC_BULLETIN_ORIGIN = "https://bulletin.zaindharper.workers.dev"


class BulletinOriginError(ValueError):
    """Fixed, non-echoing destination failure."""
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def canonical_bulletin_origin(value: object, *, allow_loopback: bool = False) -> str:
    """Normalize a selected origin; no credentials, paths or implicit config."""
    try:
        if (type(value) is not str or not value or len(value) > 300
                or not value.isascii() or any(ord(c) <= 32 or ord(c) == 127 for c in value)
                or any(c in value for c in "\\%?#@")):
            raise ValueError
        parsed = urlsplit(value)
        host, port = parsed.hostname, parsed.port
        if (not host or parsed.path not in ("", "/") or parsed.username is not None
                or parsed.password is not None or parsed.netloc.endswith(":")
                or parsed.netloc.startswith("[") and ":" not in host
                or port is not None and not 1 <= port <= 65535):
            raise ValueError
        if ":" in host:
            host = "[" + ipaddress.IPv6Address(host).compressed + "]"
        elif (len(host) > 253 or any(not re.fullmatch(
                r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in host.split("."))):
            raise ValueError
        if parsed.scheme != "https" and not (
                allow_loopback and parsed.scheme == "http"
                and host in {"127.0.0.1", "localhost", "[::1]"}):
            raise ValueError
        default = 443 if parsed.scheme == "https" else 80
        suffix = "" if port is None or port == default else f":{port}"
        return f"{parsed.scheme}://{host}{suffix}"
    except (TypeError, ValueError, UnicodeError):
        raise BulletinOriginError("BULLETIN_ORIGIN_INVALID") from None


def operation_bulletin_origin(operation) -> str:
    """Require a canonical field; legacy approved operations cannot gain one."""
    if "bulletin_base_url" not in operation:
        raise BulletinOriginError("BULLETIN_ORIGIN_REQUIRED")
    value = operation["bulletin_base_url"]
    # Loopback syntax may be approved explicitly; runtime opt-in is separate.
    canonical = canonical_bulletin_origin(value, allow_loopback=True)
    if value != canonical:
        raise BulletinOriginError("BULLETIN_ORIGIN_INVALID")
    return canonical


def checked_bulletin_origin(operation, *, configured: str | None = None,
                            allow_loopback: bool = False) -> str:
    """Compare before secrets and return the exact approved transport target."""
    approved = operation_bulletin_origin(operation)
    canonical_bulletin_origin(approved, allow_loopback=allow_loopback)
    raw = os.environ.get("FLYWHEEL_BULLETIN_BASE_URL", "") if configured is None else configured
    current = canonical_bulletin_origin(raw, allow_loopback=allow_loopback)
    if approved != current:
        raise BulletinOriginError("BULLETIN_ORIGIN_MISMATCH")
    return approved
