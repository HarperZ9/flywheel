"""Shared Bulletin identity setup constants and fixed errors."""
from __future__ import annotations

from .key_roster import BULLETIN_CREDENTIAL_NAME

DEFAULT_HANDLE = "flywheel"
DEFAULT_BASE_URL = "https://bulletin.zaindharper.workers.dev"
PREPARE_SCHEMA = "flywheel.bulletin-identity-prepare/v1"
IDENTITY_SCHEMA = "flywheel.bulletin-identity/v1"
ERROR_SCHEMA = "flywheel.bulletin-identity-error/v1"
MAX_KEY_BYTES = 16_384
MAX_POW_BITS = 24
DEFAULT_TIMEOUT = 20


class BulletinIdentityError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class BulletinIdentityHttpError(RuntimeError):
    def __init__(self, status: int, body: dict | None = None) -> None:
        self.status = status
        self.body = body or {}
        super().__init__(f"http status {status}")


def error_body(code: str) -> dict:
    return {
        "schema": ERROR_SCHEMA,
        "ok": False,
        "error": {
            "code": code,
            "message": "bulletin identity setup could not complete",
        },
    }
