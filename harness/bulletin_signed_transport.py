"""Signed Bulletin transport for reviewed public outcome projections."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .bulletin_readback import post_matches
from .credential_handles import CredentialHandleError, CredentialHandleStore
from .evidence_json import canonical_sha256, strict_load_json
from .evidence_public import public_result
from .gateway_operation import thaw_operation
from .outcome_bulletin import PREVIEW_SCHEMA

BULLETIN_KEY_SLOT = "BULLETIN_AGENT_JWK"
BULLETIN_USER_AGENT = (
    "Flywheel-native-client/1 (+https://github.com/HarperZ9/flywheel)")
_PUBLICATION_SCHEMA = "flywheel.outcome-bulletin-publication/v1"


class BulletinSignedTransportError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def bulletin_request(
        url: str, *, method: str, data: bytes | None = None,
        headers: dict[str, str] | None = None) -> Request:
    request_headers = {"User-Agent": BULLETIN_USER_AGENT}
    if headers:
        request_headers.update(headers)
    return Request(url, data=data, method=method, headers=request_headers)


def publish_authorized_preview(
        authorized, preview: dict, *, state_root: Path,
        keychain_get: Callable[[str], str | None] | None = None,
        credential_bindings: object | None = None,
        base_url: str | None = None, timeout: int = 20,
        allow_loopback: bool = False,
        now: Callable[[], int] | None = None,
        nonce_bytes: Callable[[int], bytes] | None = None) -> dict:
    """Post only the exact preview authorized by a consumed gateway grant."""
    problem = _grant_problem(authorized, preview)
    if problem is not None:
        return _publication(problem, preview,
                            does_not_prove=["a signed Bulletin write ran"])
    try:
        base = _configured_base_url(base_url, allow_loopback=allow_loopback)
        key = _key_from_bindings(credential_bindings) if credential_bindings else (
            _resolve_key(authorized, state_root, keychain_get))
    except BulletinSignedTransportError:
        return _publication(
            "publish_unavailable", preview,
            does_not_prove=["a signed Bulletin write was attempted"])
    client = _SignedClient(
        base, key, timeout=timeout, now=now, nonce_bytes=nonce_bytes)
    try:
        posted = client.post_json("/v1/posts", preview["post"])
    except BulletinSignedTransportError as exc:
        if exc.code == "WRITE_RESPONSE_LOST":
            return _publication(
                "post_write_unverified", preview,
                does_not_prove=["Bulletin accepted or rejected the write"])
        return _publication("publish_failed", preview)
    post_id = _post_id(posted)
    if not post_id or posted.get("ok") is not True:
        return _publication("publish_failed", preview)
    try:
        seen = _read_json(f"{base}/v1/posts/{quote(post_id, safe='')}", timeout)
    except BulletinSignedTransportError:
        return _publication(
            "posted_readback_unavailable", preview, post_id=post_id,
            does_not_prove=["public board readback matched the requested post"])
    post = seen.get("post") if type(seen) is dict else None
    if post_matches(post, preview["post"]):
        return _publication("posted_readback_match", preview, post_id=post_id)
    return _publication(
        "posted_readback_drift", preview, post_id=post_id,
        does_not_prove=["public board readback matched the requested post"])


def _grant_problem(authorized, preview: dict) -> str | None:
    if type(preview) is not dict or preview.get("schema") != PREVIEW_SCHEMA:
        return "grant_binding_mismatch"
    if (getattr(authorized, "action", None) != "lane.call"
            or getattr(authorized, "tool", None) != "board_write_post"
            or dict(getattr(authorized, "destination", {})) != {
                "kind": "lane", "ref": "bulletin"}):
        return "grant_binding_mismatch"
    op = thaw_operation(getattr(authorized, "operation", {}))
    expected = {"name": "bulletin", "tool": "board_write_post",
                "args": preview["post"], "governance_tier": "T2"}
    for key, value in expected.items():
        if op.get(key) != value:
            return "grant_binding_mismatch"
    refs = getattr(authorized, "credential_refs", ())
    if len(refs) != 1:
        return "publish_unavailable"
    if tuple(op.get("credential_refs", ())) != tuple(refs):
        return "grant_binding_mismatch"
    if getattr(authorized, "data_refs", ()) or op.get("data_refs", ()):
        return "grant_binding_mismatch"
    return None


def _resolve_key(authorized, state_root: Path, keychain_get):
    getter = keychain_get
    if getter is None:
        from .keychain import keychain_get as getter
    refs = list(getattr(authorized, "credential_refs", ()))
    try:
        bindings = CredentialHandleStore(
            Path(state_root), keychain_get=getter).resolve_exact(
                authorized.owner_ref, refs, [BULLETIN_KEY_SLOT])
        return _parse_key(bindings.value_for(BULLETIN_KEY_SLOT))
    except (CredentialHandleError, AttributeError, TypeError, ValueError,
            UnicodeError, RecursionError):
        raise BulletinSignedTransportError("CREDENTIAL_UNAVAILABLE") from None


def _key_from_bindings(bindings: object):
    try:
        return _parse_key(bindings.value_for(BULLETIN_KEY_SLOT))
    except (CredentialHandleError, AttributeError, TypeError, ValueError, UnicodeError,
            RecursionError):
        raise BulletinSignedTransportError("CREDENTIAL_UNAVAILABLE") from None


def _parse_key(raw: str):
    try:
        value = strict_load_json(raw.encode(), max_bytes=16_384, max_depth=8)
        private = value.get("private") if type(value) is dict else None
        public = value.get("public") if type(value) is dict else None
        if type(private) is not dict or type(public) is not dict:
            raise ValueError
        if private.get("kty") != "OKP" or private.get("crv") != "Ed25519":
            raise ValueError
        d, x = _b64ud(private.get("d")), _b64ud(public.get("x"))
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )
        key = Ed25519PrivateKey.from_private_bytes(d)
        actual = key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        if actual != x:
            raise ValueError
        return {"key": key, "thumbprint": _thumbprint(public)}
    except ImportError:
        raise BulletinSignedTransportError("SIGNING_UNAVAILABLE") from None
    except Exception:
        raise BulletinSignedTransportError("CREDENTIAL_UNAVAILABLE") from None


def configured_bulletin_base_url(
        value: str | None = None, *, allow_loopback: bool = False) -> str:
    return _configured_base_url(value, allow_loopback=allow_loopback)


def _configured_base_url(value: str | None, *, allow_loopback: bool) -> str:
    raw = (value or os.environ.get("FLYWHEEL_BULLETIN_BASE_URL") or "").strip()
    if not raw or "\\" in raw or any(ch.isspace() for ch in raw):
        raise BulletinSignedTransportError("BASE_URL_UNAVAILABLE")
    try:
        parsed = urlsplit(raw)
    except ValueError:
        raise BulletinSignedTransportError("BASE_URL_UNAVAILABLE") from None
    if parsed.username is not None or parsed.password is not None:
        raise BulletinSignedTransportError("BASE_URL_UNAVAILABLE")
    loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise BulletinSignedTransportError("BASE_URL_UNAVAILABLE")
    if parsed.scheme == "https" and parsed.netloc:
        return f"https://{parsed.netloc}"
    if allow_loopback and parsed.scheme == "http" and parsed.netloc and loopback:
        return f"http://{parsed.netloc}"
    raise BulletinSignedTransportError("BASE_URL_UNAVAILABLE")


class _SignedClient:
    def __init__(
            self, base_url: str, key, *, timeout: int,
            now: Callable[[], int] | None,
            nonce_bytes: Callable[[int], bytes] | None) -> None:
        self.base_url = base_url
        self.key = key
        self.timeout = timeout
        self.now = now or (lambda: int(time.time()))
        self.nonce_bytes = nonce_bytes or secrets.token_bytes

    def post_json(self, path: str, payload: dict) -> dict:
        body = json.dumps(
            payload, sort_keys=True, separators=(",", ":")).encode()
        url = self.base_url + path
        digest = "sha-256=:" + base64.b64encode(
            hashlib.sha256(body).digest()).decode() + ":"
        parsed = urlsplit(url)
        created = int(self.now())
        nonce = _b64u(self.nonce_bytes(16))
        params = (
            '("@method" "@authority" "@path" "content-digest")'
            f';created={created};expires={created + 120}'
            f';keyid="{self.key["thumbprint"]}";nonce="{nonce}"'
            ';tag="web-bot-auth";alg="ed25519"')
        base = "\n".join([
            '"@method": POST',
            f'"@authority": {parsed.netloc.lower()}',
            f'"@path": {parsed.path}',
            f'"content-digest": {digest}',
            f'"@signature-params": {params}',
        ])
        signature = self.key["key"].sign(base.encode())
        request = bulletin_request(url, data=body, method="POST", headers={
            "content-type": "application/json",
            "content-digest": digest,
            "signature-input": f"sig1={params}",
            "signature": "sig1=:" + base64.b64encode(signature).decode() + ":",
        })
        return _open_json(request, self.timeout, write=True)


def _read_json(url: str, timeout: int) -> dict:
    return _open_json(bulletin_request(url, method="GET"), timeout, write=False)


def _open_json(request: Request, timeout: int, *, write: bool) -> dict:
    try:
        with _NO_REDIRECT.open(request, timeout=timeout) as response:
            raw = response.read(1_048_576)
        value = strict_load_json(raw, max_bytes=1_048_576, max_depth=16)
        if type(value) is not dict:
            raise ValueError
        return value
    except HTTPError as exc:
        if 300 <= exc.code < 400:
            if write:
                return {"ok": False}
            raise BulletinSignedTransportError("READBACK_UNAVAILABLE")
        try:
            raw = exc.read(1_048_576)
            value = strict_load_json(raw, max_bytes=1_048_576, max_depth=16)
            return value if type(value) is dict else {"ok": False}
        except Exception:
            return {"ok": False}
    except (OSError, URLError, ValueError, UnicodeError, RecursionError):
        code = "WRITE_RESPONSE_LOST" if write else "READBACK_UNAVAILABLE"
        raise BulletinSignedTransportError(code) from None


def _post_id(value: object) -> str | None:
    post = value.get("post") if type(value) is dict else None
    post_id = post.get("id") if type(post) is dict else None
    return post_id if type(post_id) is str and post_id.strip() else None


def _publication(status: str, preview: dict, **extra) -> dict:
    body = {"schema": _PUBLICATION_SCHEMA, "status": status,
            "post_payload_sha256": preview.get("post_payload_sha256", ""),
            **extra}
    return public_result("outcome-bulletin-publication", body)


def _thumbprint(public: dict) -> str:
    canonical = json.dumps(
        {"crv": public.get("crv"), "kty": public.get("kty"),
         "x": public.get("x")}, sort_keys=True, separators=(",", ":"))
    return _b64u(hashlib.sha256(canonical.encode()).digest())


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64ud(value: object) -> bytes:
    if type(value) is not str:
        raise ValueError
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


_NO_REDIRECT = build_opener(_NoRedirect)
