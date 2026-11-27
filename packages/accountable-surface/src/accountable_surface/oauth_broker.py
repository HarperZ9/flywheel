"""Standard OAuth 2.0 PKCE (RFC 7636), Device Flow (RFC 8628), and grant-gated token broker."""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlencode, urlparse

from .keystore import KeystoreProtocol, secret_fingerprint

_PKCE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
_LOOPBACK_HOSTS = frozenset(("localhost", "127.0.0.1", "::1"))


class OAuthBrokerError(RuntimeError):
    """Fail-closed OAuth error that never embeds raw tokens or client secrets."""


def _b64url_nopad(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def compute_pkce_s256(verifier: str) -> str:
    """Compute RFC 7636 S256 code_challenge = BASE64URL-ENCODE(SHA256(ASCII(verifier)))."""
    if not (43 <= len(verifier) <= 128) or any(ch not in _PKCE_ALPHABET for ch in verifier):
        raise ValueError("PKCE code_verifier must be 43..128 unreserved ASCII characters")
    return _b64url_nopad(hashlib.sha256(verifier.encode("ascii")).digest())


@dataclass(frozen=True)
class PKCEPair:
    """RFC 7636 PKCE verifier/challenge pair with redacted repr."""

    code_verifier: str
    code_challenge: str
    method: str = "S256"

    def __repr__(self) -> str:
        return f"PKCEPair(method={self.method!r}, challenge={self.code_challenge[:10]}...)"


def generate_pkce_pair(length: int = 64) -> PKCEPair:
    """Generate a cryptographically random RFC 7636 S256 PKCE verifier/challenge pair."""
    if not (43 <= length <= 128):
        raise ValueError("PKCE verifier length must be between 43 and 128")
    verifier = "".join(secrets.choice(_PKCE_ALPHABET) for _ in range(length))
    return PKCEPair(code_verifier=verifier, code_challenge=compute_pkce_s256(verifier), method="S256")


def _validate_endpoint_url(url: str, *, allow_loopback_http: bool = False) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme == "https" and host:
        return url
    if allow_loopback_http and parsed.scheme == "http" and host in _LOOPBACK_HOSTS:
        return url
    raise OAuthBrokerError(f"endpoint URL rejected by transport policy: {parsed.scheme}://{host}")


def build_authorization_url(
    authorize_endpoint: str,
    *,
    client_id: str,
    redirect_uri: str,
    scope: str,
    state: str,
    pkce_pair: PKCEPair,
    extra_params: Mapping[str, str] | None = None,
) -> str:
    """Build a standard RFC 7636 OAuth 2.0 authorization URL without embedding secrets."""
    base = _validate_endpoint_url(authorize_endpoint, allow_loopback_http=False)
    _validate_endpoint_url(redirect_uri, allow_loopback_http=True)
    if not client_id.strip() or not state.strip():
        raise OAuthBrokerError("client_id and state are required")
    params: dict[str, str] = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        "code_challenge": pkce_pair.code_challenge,
        "code_challenge_method": pkce_pair.method,
    }
    for k, v in (extra_params or {}).items():
        if any(bad in k.lower() for bad in ("secret", "password", "token")):
            raise OAuthBrokerError(f"refused secret-bearing parameter in authorization URL: {k}")
        params[str(k)] = str(v)
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}{urlencode(params)}"


class DeviceFlowSession:
    """RFC 8628 Device Authorization Grant state machine for remote-friendly sign-in."""

    def __init__(
        self,
        *,
        device_code: str,
        user_code: str,
        verification_uri: str,
        expires_in: int,
        interval: int = 5,
        token_handle: str = "oauth_device_token",
        keystore: KeystoreProtocol | None = None,
        verification_uri_complete: str | None = None,
        started_at: float | None = None,
    ) -> None:
        _validate_endpoint_url(verification_uri, allow_loopback_http=False)
        self._device_code = device_code
        self.user_code = user_code
        self.verification_uri = verification_uri
        self.verification_uri_complete = verification_uri_complete
        self.started_at = float(time.time() if started_at is None else started_at)
        self.expires_at = self.started_at + max(int(expires_in), 1)
        self.interval = max(int(interval), 1)
        self.token_handle = token_handle
        self._keystore = keystore
        self.state = "pending"
        self.token_fingerprint: str | None = None

    def __repr__(self) -> str:
        return f"DeviceFlowSession(state={self.state!r}, user_code={self.user_code!r}, handle={self.token_handle!r})"

    def to_public_dict(self) -> dict[str, Any]:
        """Return safe status metadata (never exposes device_code or OAuth tokens)."""
        return {
            "state": self.state,
            "user_code": self.user_code,
            "verification_uri": self.verification_uri,
            "verification_uri_complete": self.verification_uri_complete,
            "interval": self.interval,
            "expires_at": self.expires_at,
            "token_handle": self.token_handle,
            "token_fingerprint": self.token_fingerprint,
        }

    def poll_once(self, poll_fn: Callable[[str], Mapping[str, Any]], *, now: float | None = None) -> dict[str, Any]:
        """Advance one RFC 8628 polling step and persist approved tokens into keystore."""
        ts = float(time.time() if now is None else now)
        if self.state in ("approved", "access_denied", "expired_token", "cancelled"):
            return self.to_public_dict()
        if ts >= self.expires_at:
            self.state = "expired_token"
            return self.to_public_dict()
        resp = dict(poll_fn(self._device_code))
        err = str(resp.get("error", "")).strip()
        if err == "authorization_pending":
            self.state = "pending"
            return self.to_public_dict()
        if err == "slow_down":
            self.interval += 5
            self.state = "slow_down"
            return self.to_public_dict()
        if err in ("access_denied", "expired_token"):
            self.state = err
            return self.to_public_dict()
        if err:
            raise OAuthBrokerError(f"device flow token endpoint error: {err}")
        access_token = str(resp.get("access_token", "")).strip()
        if not access_token:
            raise OAuthBrokerError("device flow response missing access_token")
        record = {
            "access_token": access_token,
            "refresh_token": str(resp.get("refresh_token", "")),
            "token_type": str(resp.get("token_type", "Bearer")),
            "scope": str(resp.get("scope", "")),
            "expires_at": ts + int(resp.get("expires_in", 3600)),
        }
        if self._keystore is not None:
            self._keystore.put(self.token_handle, json.dumps(record, sort_keys=True, separators=(",", ":")))
        self.token_fingerprint = secret_fingerprint(access_token)
        self.state = "approved"
        return self.to_public_dict()


class OAuthTokenBroker:
    """Grant-gated OAuth token broker enforcing host/scope boundaries and zero leakage."""

    def __init__(
        self,
        keystore: KeystoreProtocol,
        *,
        allowed_hosts: Iterable[str],
        allowed_scopes: Iterable[str],
        allowed_actions: Iterable[str] = ("oauth.use_token", "oauth.refresh_token"),
        expiry_skew_seconds: int = 30,
    ) -> None:
        self._keystore = keystore
        self.allowed_hosts = frozenset(h.strip().lower() for h in allowed_hosts if h.strip())
        self.allowed_scopes = frozenset(s.strip() for s in allowed_scopes if s.strip())
        self.allowed_actions = frozenset(a.strip() for a in allowed_actions if a.strip())
        self.expiry_skew_seconds = max(int(expiry_skew_seconds), 0)

    def store_token_record(
        self,
        handle: str,
        *,
        access_token: str,
        expires_at: float,
        scopes: Iterable[str] = (),
        refresh_token: str = "",
        token_type: str = "Bearer",
    ) -> dict[str, Any]:
        """Store an owner-enrolled OAuth token record inside the scoped keystore."""
        scope_list = sorted({s.strip() for s in scopes if s.strip()})
        payload = {
            "access_token": access_token, "refresh_token": refresh_token,
            "token_type": token_type, "scope": " ".join(scope_list), "expires_at": float(expires_at),
        }
        self._keystore.put(handle, json.dumps(payload, sort_keys=True, separators=(",", ":")))
        return {"handle": handle, "token_fingerprint": secret_fingerprint(access_token), "expires_at": float(expires_at), "scopes": scope_list}

    def get_valid_access_token(
        self,
        handle: str,
        *,
        host: str,
        required_scopes: Iterable[str] = (),
        now: float | None = None,
        refresh_fn: Callable[[str, str, tuple[str, ...]], Mapping[str, Any]] | None = None,
    ) -> str:
        """Return a valid access token if host, scopes, and grant actions pass; refresh if expired."""
        norm_host = host.strip().lower()
        req_scopes = tuple(sorted({s.strip() for s in required_scopes if s.strip()}))
        if "oauth.use_token" not in self.allowed_actions:
            raise PermissionError("grant does not authorize oauth.use_token")
        if norm_host not in self.allowed_hosts:
            raise PermissionError(f"OAuth token refused for unauthorized host: {norm_host}")
        if not set(req_scopes).issubset(self.allowed_scopes):
            raise PermissionError("requested OAuth scopes exceed grant allowed_scopes")

        raw = self._keystore.get(handle)
        if not raw:
            raise OAuthBrokerError(f"no OAuth token stored under handle: {handle}")
        rec = json.loads(raw)
        ts = float(time.time() if now is None else now)
        if ts < float(rec.get("expires_at", 0.0)) - self.expiry_skew_seconds:
            return str(rec["access_token"])

        if "oauth.refresh_token" not in self.allowed_actions:
            raise PermissionError("expired token cannot refresh: grant lacks oauth.refresh_token")
        refresh_tok = str(rec.get("refresh_token", "")).strip()
        if not refresh_tok or refresh_fn is None:
            raise OAuthBrokerError(f"token expired and cannot be refreshed for handle: {handle}")
        refreshed = dict(refresh_fn(refresh_tok, norm_host, req_scopes))
        new_access = str(refreshed.get("access_token", "")).strip()
        if not new_access:
            raise OAuthBrokerError(f"refresh response missing access_token for handle: {handle}")
        new_exp = ts + int(refreshed.get("expires_in", 3600))
        new_refresh = str(refreshed.get("refresh_token", refresh_tok))
        new_scopes = str(refreshed.get("scope", rec.get("scope", ""))).split()
        self.store_token_record(handle, access_token=new_access, expires_at=new_exp, scopes=new_scopes, refresh_token=new_refresh)
        return new_access


def redact_secrets(text: str, secret_values: Iterable[str]) -> str:
    """Replace any non-empty secret value in text with [REDACTED] for logging hygiene."""
    out = text
    for sec in secret_values:
        if sec and len(sec) >= 4:
            out = out.replace(sec, "[REDACTED]")
    return out
