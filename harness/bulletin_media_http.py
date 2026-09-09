"""Small public media read helper for Bulletin loopback verification."""
from __future__ import annotations

from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, build_opener

from .bulletin_signed_transport import BulletinSignedTransportError, bulletin_request


def read_public_bytes(
        url: str, timeout: int, headers: dict[str, str] | None = None,
        max_bytes: int = 10 * 1024 * 1024,
) -> tuple[int, bytes, dict[str, str]]:
    if type(max_bytes) is not int or max_bytes < 0:
        raise BulletinSignedTransportError("READBACK_UNAVAILABLE")
    try:
        with _NO_REDIRECT.open(
                bulletin_request(url, method="GET", headers=headers or {}),
                timeout=timeout) as response:
            return response.status, response.read(max_bytes + 1), {
                key.lower(): value for key, value in response.headers.items()}
    except HTTPError as exc:
        if 300 <= exc.code < 400:
            raise BulletinSignedTransportError("READBACK_UNAVAILABLE") from None
        return exc.code, exc.read(min(max_bytes + 1, 1_048_576)), {
            key.lower(): value for key, value in exc.headers.items()}
    except (OSError, URLError, ValueError):
        raise BulletinSignedTransportError("READBACK_UNAVAILABLE") from None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


_NO_REDIRECT = build_opener(_NoRedirect)
