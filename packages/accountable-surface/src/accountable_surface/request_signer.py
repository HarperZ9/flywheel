"""Grant-gated RFC 9421 HTTP Message Signatures and OAuth 1.0a HMAC-SHA256 request signer."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import parse_qsl, quote, urlparse

from .action_receipt import ActionReceiptReceptor, receipt_from_outcome
from .credentials import resolve_credential_handle
from .keystore import KeystoreProtocol, secret_fingerprint

_RFC9421_COMPONENTS = ("@method", "@authority", "@path", "content-digest")


def _rfc3986_quote(value: str) -> str:
    return quote(str(value), safe="-._~")


def compute_content_digest(body: bytes) -> str:
    """Compute RFC 9530 Content-Digest header value (sha-256=:<base64>:)."""
    b64 = base64.b64encode(hashlib.sha256(body).digest()).decode("ascii")
    return f"sha-256=:{b64}:"


def build_rfc9421_signature_base(
    *,
    method: str,
    authority: str,
    path: str,
    content_digest: str,
    key_id: str,
    alg: str,
    created: int,
) -> tuple[str, str]:
    """Construct canonical RFC 9421 signature-params and signature base string."""
    comp_list = " ".join(f'"{c}"' for c in _RFC9421_COMPONENTS)
    sig_params = f'({comp_list});created={int(created)};keyid="{key_id}";alg="{alg}"'
    lines = [
        f'"@method": {method.upper()}',
        f'"@authority": {authority.lower()}',
        f'"@path": {path or "/"}',
        f'"content-digest": {content_digest}',
        f'"@signature-params": {sig_params}',
    ]
    return sig_params, "\n".join(lines)


def sign_http_request_rfc9421(
    *,
    method: str,
    url: str,
    body: bytes = b"",
    key_id: str,
    signing_key: bytes | str | None = None,
    alg: str = "hmac-sha256",
    created: int | None = None,
    ed25519_signer: Callable[[bytes], bytes] | None = None,
    label: str = "sig1",
) -> dict[str, str]:
    """Sign an HTTP request per RFC 9421 using hmac-sha256 or a pluggable Ed25519 callback."""
    parsed = urlparse(url)
    authority = (parsed.netloc or "").lower()
    path = parsed.path or "/"
    if not authority:
        raise ValueError("URL must include host/authority")
    ts = int(time.time() if created is None else created)
    digest_hdr = compute_content_digest(body)
    sig_params, base = build_rfc9421_signature_base(
        method=method, authority=authority, path=path,
        content_digest=digest_hdr, key_id=key_id, alg=alg, created=ts,
    )
    base_bytes = base.encode("ascii")
    if alg == "hmac-sha256":
        if signing_key is None:
            raise ValueError("signing_key is required for hmac-sha256")
        key_bytes = signing_key.encode("utf-8") if isinstance(signing_key, str) else bytes(signing_key)
        sig_bytes = hmac.new(key_bytes, base_bytes, hashlib.sha256).digest()
    elif alg == "ed25519":
        if ed25519_signer is None:
            raise ValueError("ed25519_signer callback is required for ed25519")
        sig_bytes = bytes(ed25519_signer(base_bytes))
    else:
        raise ValueError(f"unsupported RFC 9421 algorithm: {alg}")
    sig_b64 = base64.b64encode(sig_bytes).decode("ascii")
    return {
        "Content-Digest": digest_hdr,
        "Signature-Input": f"{label}={sig_params}",
        "Signature": f"{label}=:{sig_b64}:",
    }


def _parse_sig_header(sig_input: str, sig_header: str) -> tuple[str, str, int, str, bytes]:
    label, params = sig_input.split("=", 1)
    s_label, s_val = sig_header.split("=", 1)
    if label != s_label or not (s_val.startswith(":") and s_val.endswith(":")):
        raise ValueError("mismatched RFC 9421 signature label or framing")
    parts = dict(item.split("=", 1) for item in params.split(";")[1:] if "=" in item)
    created = int(parts["created"])
    key_id = parts["keyid"].strip('"')
    alg = parts["alg"].strip('"')
    return label, key_id, created, alg, base64.b64decode(s_val[1:-1])


def verify_http_request_rfc9421(
    *,
    method: str,
    url: str,
    body: bytes,
    headers: Mapping[str, str],
    signing_key: bytes | str | None = None,
    ed25519_verifier: Callable[[bytes, bytes], bool] | None = None,
) -> tuple[bool, str]:
    """Verify RFC 9421 Content-Digest, Signature-Input, and Signature headers."""
    try:
        expected_digest = compute_content_digest(body)
        if not hmac.compare_digest(headers.get("Content-Digest", ""), expected_digest):
            return False, "Content-Digest mismatch"
        _, key_id, created, alg, sig_bytes = _parse_sig_header(headers["Signature-Input"], headers["Signature"])
        parsed = urlparse(url)
        _, base = build_rfc9421_signature_base(
            method=method, authority=(parsed.netloc or "").lower(), path=parsed.path or "/",
            content_digest=expected_digest, key_id=key_id, alg=alg, created=created,
        )
        base_bytes = base.encode("ascii")
        if alg == "hmac-sha256":
            if signing_key is None:
                return False, "missing signing_key for hmac-sha256"
            key_bytes = signing_key.encode("utf-8") if isinstance(signing_key, str) else bytes(signing_key)
            expected_sig = hmac.new(key_bytes, base_bytes, hashlib.sha256).digest()
            return (True, "MATCH") if hmac.compare_digest(expected_sig, sig_bytes) else (False, "signature mismatch")
        if alg == "ed25519":
            if ed25519_verifier is None:
                return False, "missing ed25519_verifier callback"
            return (True, "MATCH") if ed25519_verifier(base_bytes, sig_bytes) else (False, "ed25519 signature mismatch")
        return False, f"unsupported alg: {alg}"
    except (KeyError, ValueError) as exc:
        return False, f"invalid signature headers: {exc}"


def build_oauth1_authorization_header(
    *,
    method: str,
    url: str,
    consumer_key: str,
    consumer_secret: str,
    token: str = "",
    token_secret: str = "",
    timestamp: int | None = None,
    nonce: str | None = None,
    extra_params: Mapping[str, str] | None = None,
) -> str:
    """Build an OAuth 1.0a (RFC 5849) Authorization header using HMAC-SHA256."""
    parsed = urlparse(url)
    base_url = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path or '/'}"
    oauth_params: dict[str, str] = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": nonce or secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA256",
        "oauth_timestamp": str(int(time.time() if timestamp is None else timestamp)),
        "oauth_version": "1.0",
    }
    if token:
        oauth_params["oauth_token"] = token
    all_pairs = list(parse_qsl(parsed.query, keep_blank_values=True))
    all_pairs.extend((str(k), str(v)) for k, v in (extra_params or {}).items())
    all_pairs.extend(oauth_params.items())
    encoded = sorted((_rfc3986_quote(k), _rfc3986_quote(v)) for k, v in all_pairs)
    param_str = "&".join(f"{k}={v}" for k, v in encoded)
    sig_base = "&".join((method.upper(), _rfc3986_quote(base_url), _rfc3986_quote(param_str)))
    signing_key = f"{_rfc3986_quote(consumer_secret)}&{_rfc3986_quote(token_secret)}".encode("ascii")
    sig = base64.b64encode(hmac.new(signing_key, sig_base.encode("ascii"), hashlib.sha256).digest()).decode("ascii")
    oauth_params["oauth_signature"] = sig
    fields = ", ".join(f'{_rfc3986_quote(k)}="{_rfc3986_quote(v)}"' for k, v in sorted(oauth_params.items()))
    return f"OAuth {fields}"


class _SignerOutcome:
    def __init__(self, *, acted: bool, verified: bool, decision: str, before_digest: str, after_digest: str) -> None:
        self.acted, self.verified, self.decision = acted, verified, decision
        self.verdict = "verified" if verified else "unverifiable"
        self.before_digest, self.after_digest = before_digest, after_digest
        self.certificate = {"signer": "rfc9421"}


class AccountableRequestSigner:
    """Grant-gated request signer that checks host/method/action grants and emits zero-leakage receipts."""

    def __init__(
        self,
        *,
        keystore: KeystoreProtocol | None = None,
        allowed_hosts: Iterable[str],
        allowed_methods: Iterable[str] = ("GET", "POST"),
        allowed_actions: Iterable[str] = ("oauth.sign_request",),
        receipts_path: str | None = None,
    ) -> None:
        self._keystore = keystore
        self.allowed_hosts = frozenset(h.strip().lower() for h in allowed_hosts if h.strip())
        self.allowed_methods = frozenset(m.strip().upper() for m in allowed_methods if m.strip())
        self.allowed_actions = frozenset(a.strip() for a in allowed_actions if a.strip())
        self._receptor = ActionReceiptReceptor(receipts_path) if receipts_path else None

    def _check_grant(self, method: str, url: str) -> tuple[str, str]:
        if "oauth.sign_request" not in self.allowed_actions:
            raise PermissionError("grant does not authorize oauth.sign_request")
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        up_method = method.upper()
        if host not in self.allowed_hosts:
            raise PermissionError(f"request signing refused for unauthorized host: {host}")
        if up_method not in self.allowed_methods:
            raise PermissionError(f"request signing refused for unauthorized method: {up_method}")
        return up_method, host

    def sign_rfc9421(
        self,
        *,
        method: str,
        url: str,
        body: bytes = b"",
        key_id: str,
        key_handle: str,
        alg: str = "hmac-sha256",
        created: int | None = None,
        ed25519_signer: Callable[[bytes], bytes] | None = None,
        created_at: str = "2026-11-26T00:00:00Z",
    ) -> dict[str, Any]:
        """Sign an HTTP request under grant enforcement and optionally append an action-receipt/v1 record."""
        up_method, host = self._check_grant(method, url)
        signing_key = None if alg == "ed25519" else resolve_credential_handle(key_handle, keystore=self._keystore)
        headers = sign_http_request_rfc9421(
            method=up_method, url=url, body=body, key_id=key_id,
            signing_key=signing_key, alg=alg, created=created, ed25519_signer=ed25519_signer,
        )
        sig_digest = secret_fingerprint(headers["Signature"])
        receipt_meta: dict[str, Any] | None = None
        if self._receptor is not None:
            args_hash = secret_fingerprint(f"{up_method}|{host}|{key_id}|{headers['Content-Digest']}")
            outcome = _SignerOutcome(acted=True, verified=True, decision="allow", before_digest=headers["Content-Digest"], after_digest=sig_digest)
            event = receipt_from_outcome(
                outcome, action_kind="oauth.sign_request", target=f"https://{host}",
                args_hash=args_hash, principal="agent:accountable-surface.request-signer",
                intent_ref=f"intent:sign:{key_id}", idempotency_key=f"sign:{key_id}:{sig_digest}",
                created_at=created_at, side_effect_class="sign",
            )
            receipt_meta = self._receptor.emit(event)
        return {"headers": headers, "key_id": key_id, "alg": alg, "signature_digest": sig_digest, "receipt": receipt_meta}
