"""remote_oauth.py — HTTP-shaped OAuth 2.1 endpoints for the remote MCP surface.

Wraps the transport-free ``oauth`` core in the four HTTP endpoints a phone MCP
connector discovers and drives:

- ``GET /.well-known/oauth-protected-resource`` (RFC 9728) -> which AS guards /mcp;
- ``GET /.well-known/oauth-authorization-server`` (RFC 8414) -> the endpoints + S256;
- ``GET /authorize`` -> operator approves (HTTP Basic, the approval password), a
  PKCE-bound code is minted and the browser is 302'd back to the connector;
- ``POST /token`` -> the connector exchanges code + verifier + client secret for a
  signed access token.

Each function is transport-free: it returns ``(status, headers, body)`` so the
HTTP handler in ``remote_mcp`` is a thin router. Determinism is by injection
(clock + id source on OAuthSettings).
"""
from __future__ import annotations

import base64
import hmac
import json
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from .oauth import (
    AuthCodeStore,
    InvalidToken,
    OAuthError,
    RegisteredClient,
    authorization_server_metadata,
    authorize,
    exchange_token,
    protected_resource_metadata,
    refresh_grant,
    verify_access_token,
)


def _hex_id() -> str:
    return os.urandom(16).hex()


@dataclass
class OAuthSettings:
    """The remote surface's OAuth configuration and issued-code state."""

    client: RegisteredClient
    signing_secret: str
    base_url: str  # public origin, e.g. https://agent.example (no trailing slash)
    authorize_password: str  # operator approval secret (HTTP Basic on /authorize)
    store: AuthCodeStore = field(default_factory=AuthCodeStore)
    access_ttl: int = 3600
    clock: Callable[[], int] = lambda: int(time.time())
    id_source: Callable[[], str] = _hex_id

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")

    @property
    def resource_metadata_url(self) -> str:
        return f"{self.base_url}/.well-known/oauth-protected-resource"


def _json(status: int, obj) -> tuple[int, dict, bytes]:
    return status, {"Content-Type": "application/json"}, json.dumps(obj).encode("utf-8")


def _oauth_error(exc: OAuthError) -> tuple[int, dict, bytes]:
    status = 401 if exc.code == "invalid_client" else 400
    body = {"error": exc.code}
    if exc.description:
        body["error_description"] = exc.description
    return _json(status, body)


def _basic_password_ok(authorization: str | None, password: str) -> bool:
    """The operator approves at /authorize with HTTP Basic; any username, the
    configured password. Constant-time on the password."""
    prefix = "Basic "
    if not authorization or not authorization.startswith(prefix):
        return False
    try:
        decoded = base64.b64decode(authorization[len(prefix):].strip()).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False
    _, _, presented = decoded.partition(":")
    return hmac.compare_digest(presented, password)


def _basic_client_secret(authorization: str | None) -> str | None:
    """Extract a client_secret sent via HTTP Basic (client_secret_basic)."""
    prefix = "Basic "
    if not authorization or not authorization.startswith(prefix):
        return None
    try:
        decoded = base64.b64decode(authorization[len(prefix):].strip()).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    _, _, secret = decoded.partition(":")
    return secret or None


def protected_resource_endpoint(oauth: OAuthSettings) -> tuple[int, dict, bytes]:
    return _json(200, protected_resource_metadata(f"{oauth.base_url}/mcp", oauth.base_url))


def authorization_server_endpoint(oauth: OAuthSettings) -> tuple[int, dict, bytes]:
    return _json(200, authorization_server_metadata(oauth.base_url))


def authorize_endpoint(
    oauth: OAuthSettings, headers: Mapping[str, str], query: Mapping[str, str]
) -> tuple[int, dict, bytes]:
    """The authorization endpoint. The operator approves via HTTP Basic (the
    browser prompts); on approval a PKCE-bound one-time code is minted and the
    browser is redirected back to the connector's redirect_uri."""
    if not _basic_password_ok(headers.get("authorization"), oauth.authorize_password):
        return 401, {"WWW-Authenticate": 'Basic realm="relay remote agent"'}, b"authorization required"
    try:
        result = authorize(
            oauth.client,
            response_type=query.get("response_type", ""),
            redirect_uri=query.get("redirect_uri", ""),
            code_challenge=query.get("code_challenge", ""),
            code_challenge_method=query.get("code_challenge_method", ""),
            code=oauth.id_source(),
            now=oauth.clock(),
            state=query.get("state", ""),
        )
    except OAuthError as exc:
        return _oauth_error(exc)
    oauth.store.put(result.auth_code)
    return 302, {"Location": result.redirect_url}, b""


def token_endpoint(
    oauth: OAuthSettings, headers: Mapping[str, str], form: Mapping[str, str]
) -> tuple[int, dict, bytes]:
    """The token endpoint. The connector exchanges its code + PKCE verifier +
    client secret for a signed access token (grant_type=authorization_code), or a
    refresh token for a fresh access token (grant_type=refresh_token). The client
    secret may arrive in the form body or via HTTP Basic."""
    client_secret = form.get("client_secret") or _basic_client_secret(headers.get("authorization")) or ""
    if form.get("grant_type") == "refresh_token":
        if not hmac.compare_digest(client_secret, oauth.client.client_secret):
            return _oauth_error(OAuthError("invalid_client"))
        try:
            refreshed = refresh_grant(
                form.get("refresh_token", ""), secret=oauth.signing_secret,
                now=oauth.clock(), nonce=oauth.id_source(), ttl=oauth.access_ttl,
            )
        except OAuthError as exc:
            return _oauth_error(exc)
        return _json(200, refreshed)
    try:
        response = exchange_token(
            oauth.client,
            oauth.store,
            grant_type=form.get("grant_type", ""),
            code=form.get("code", ""),
            redirect_uri=form.get("redirect_uri", ""),
            client_secret=client_secret,
            code_verifier=form.get("code_verifier", ""),
            secret=oauth.signing_secret,
            now=oauth.clock(),
            nonce=oauth.id_source(),
            ttl=oauth.access_ttl,
        )
    except OAuthError as exc:
        return _oauth_error(exc)
    return _json(200, response)


def access_token_ok(oauth: OAuthSettings, bearer: str) -> bool:
    """True when ``bearer`` is a valid, unexpired access token this server issued."""
    try:
        verify_access_token(bearer, oauth.signing_secret, now=oauth.clock())
        return True
    except InvalidToken:
        return False
