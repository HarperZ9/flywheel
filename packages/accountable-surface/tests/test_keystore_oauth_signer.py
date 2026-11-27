"""Known-answer and planted-failure tests for Wave 34C keystore, OAuth broker, and request signer."""
from __future__ import annotations

import ast
import hashlib
import hmac
import json
import sys
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from accountable_surface.action_receipt import verify_receipts
from accountable_surface.credentials import (
    MissingCredential,
    credential_fingerprint,
    has_credential,
    resolve_credential_handle,
)
from accountable_surface.keystore import (
    EncryptedFileKeystore,
    KeystoreScopeError,
    KeystoreTamperError,
    MemoryKeystore,
    Win32CredentialKeystore,
    dpapi_protect,
    dpapi_unprotect,
    scoped_target_name,
    validate_scoped_target,
)
from accountable_surface.oauth_broker import (
    DeviceFlowSession,
    OAuthBrokerError,
    OAuthTokenBroker,
    build_authorization_url,
    compute_pkce_s256,
    generate_pkce_pair,
    redact_secrets,
)
from accountable_surface.request_signer import (
    AccountableRequestSigner,
    build_oauth1_authorization_header,
    sign_http_request_rfc9421,
    verify_http_request_rfc9421,
)

SRC_DIR = Path(__file__).resolve().parents[1] / "src" / "accountable_surface"
WAVE34C_FILES = ("keystore.py", "credentials.py", "oauth_broker.py", "request_signer.py")


def test_wave34c_module_size_function_budgets_and_hygiene():
    for name in WAVE34C_FILES:
        text = (SRC_DIR / name).read_text(encoding="utf-8")
        assert len(text.splitlines()) <= 280, f"{name} exceeded 280 LOC ({len(text.splitlines())})"
        assert "\u2014" not in text, f"em dash found in {name}"
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                span = (node.end_lineno or node.lineno) - node.lineno + 1
                assert span <= 50, f"{name}:{node.name} exceeded 50 lines ({span})"


def test_keystore_namespace_isolation_encrypted_file_and_credentials(tmp_path, monkeypatch):
    for bad_target in (
        "LegacyGeneric:target=Chrome",
        "WindowsLive:target=virtualapp/didlogical",
        "accountable-surface:../escape:tok",
        "accountable-surface:onlyone",
        "accountable-surface:a:b:c",
    ):
        with pytest.raises(KeystoreScopeError):
            validate_scoped_target(bad_target)

    with pytest.raises(KeystoreScopeError):
        scoped_target_name("../bad", "tok")
    with pytest.raises(KeystoreScopeError):
        scoped_target_name("good", "bad:colon")
    assert scoped_target_name("ops", "api_key") == "accountable-surface:ops:api_key"

    vault_file = tmp_path / "vault.json"
    ks = EncryptedFileKeystore(vault_file, master_key="test-master-key-32-bytes-minimum!", namespace="ops")
    fp = ks.put("service_key", "s3cr3t-value-xyz")
    assert fp.startswith("sha256:") and ks.has("service_key")
    assert ks.get("service_key") == "s3cr3t-value-xyz"
    assert resolve_credential_handle("service_key", keystore=ks) == "s3cr3t-value-xyz"
    assert has_credential("service_key", keystore=ks)
    assert credential_fingerprint("service_key", keystore=ks) == fp
    assert "s3cr3t-value-xyz" not in vault_file.read_text(encoding="utf-8")

    # 1-byte ciphertext tamper must fail MAC verification
    doc = json.loads(vault_file.read_text(encoding="utf-8"))
    rec = doc["records"]["accountable-surface:ops:service_key"]
    rec["ct"] = ("A" if rec["ct"][0] != "A" else "B") + rec["ct"][1:]
    vault_file.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(KeystoreTamperError):
        ks.get("service_key")

    # Env fallback and newline guard
    monkeypatch.setenv("WAVE34C_ENV_TOK", "env-token-ok")
    assert resolve_credential_handle("WAVE34C_ENV_TOK", keystore=MemoryKeystore()) == "env-token-ok"
    monkeypatch.setenv("WAVE34C_BAD_TOK", "line1\nline2")
    with pytest.raises(MissingCredential):
        resolve_credential_handle("WAVE34C_BAD_TOK", keystore=MemoryKeystore())


def test_win32_dpapi_and_credential_manager_live_roundtrip_on_windows():
    if sys.platform != "win32":
        return
    plain = b"dpapi-live-test-payload-wave34c"
    entropy = b"accountable-surface:dpapi-test"
    protected = dpapi_protect(plain, entropy=entropy)
    assert protected != plain
    assert dpapi_unprotect(protected, entropy=entropy) == plain
    tampered = bytes([protected[0] ^ 0xFF]) + protected[1:]
    with pytest.raises(KeystoreTamperError):
        dpapi_unprotect(tampered, entropy=entropy)

    ks = Win32CredentialKeystore(namespace="selftest", wrap_dpapi=True)
    with pytest.raises(KeystoreScopeError):
        ks.read_scoped_target("LegacyGeneric:target=OtherApp")

    handle = f"wave34c_{uuid.uuid4().hex[:12]}"
    try:
        fp = ks.put(handle, "win32-cred-roundtrip-value")
        assert fp.startswith("sha256:")
        assert ks.has(handle)
        assert ks.get(handle) == "win32-cred-roundtrip-value"
    finally:
        ks.delete(handle)
    assert not ks.has(handle)


def test_rfc7636_pkce_vector_and_authorization_url():
    # Official RFC 7636 Appendix B test vector
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    expected_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    assert compute_pkce_s256(verifier) == expected_challenge

    pair = generate_pkce_pair(64)
    assert len(pair.code_verifier) == 64 and pair.code_challenge == compute_pkce_s256(pair.code_verifier)
    assert pair.code_verifier not in repr(pair)

    url = build_authorization_url(
        "https://auth.example.org/oauth/authorize",
        client_id="client-123",
        redirect_uri="http://127.0.0.1:8765/callback",
        scope="read write",
        state="state-abc",
        pkce_pair=pair,
    )
    qs = parse_qs(urlparse(url).query)
    assert qs["code_challenge"] == [pair.code_challenge]
    assert qs["code_challenge_method"] == ["S256"]

    with pytest.raises(OAuthBrokerError):
        build_authorization_url(
            "http://insecure.example.org/oauth",
            client_id="c", redirect_uri="https://app.example.org/cb", scope="read", state="s", pkce_pair=pair,
        )
    with pytest.raises(OAuthBrokerError):
        build_authorization_url(
            "https://auth.example.org/oauth",
            client_id="c", redirect_uri="https://app.example.org/cb", scope="read", state="s",
            pkce_pair=pair, extra_params={"client_secret": "nope"},
        )


def test_rfc8628_device_flow_transitions_and_oauth_token_broker():
    ks = MemoryKeystore(namespace="oauth")
    session = DeviceFlowSession(
        device_code="dev-code-secret-999",
        user_code="WDJB-MJHT",
        verification_uri="https://auth.example.org/device",
        expires_in=600,
        interval=5,
        token_handle="remote_tok",
        keystore=ks,
        started_at=1000.0,
    )
    replies = iter([
        {"error": "authorization_pending"},
        {"error": "slow_down"},
        {"access_token": "tok-access-initial", "refresh_token": "tok-refresh-1", "expires_in": 120, "scope": "repo.read"},
    ])
    s1 = session.poll_once(lambda _dc: next(replies), now=1005.0)
    assert s1["state"] == "pending" and s1["interval"] == 5
    s2 = session.poll_once(lambda _dc: next(replies), now=1010.0)
    assert s2["state"] == "slow_down" and s2["interval"] == 10
    s3 = session.poll_once(lambda _dc: next(replies), now=1020.0)
    assert s3["state"] == "approved" and s3["token_fingerprint"] is not None
    assert "tok-access-initial" not in json.dumps(s3) and "dev-code-secret-999" not in json.dumps(s3)

    expired_sess = DeviceFlowSession(
        device_code="dev-exp", user_code="AAAA-BBBB",
        verification_uri="https://auth.example.org/device", expires_in=10, started_at=1000.0,
    )
    s_exp = expired_sess.poll_once(lambda _dc: {"error": "authorization_pending"}, now=1015.0)
    assert s_exp["state"] == "expired_token"

    broker = OAuthTokenBroker(ks, allowed_hosts=("api.example.org",), allowed_scopes=("repo.read",))
    tok = broker.get_valid_access_token("remote_tok", host="api.example.org", required_scopes=("repo.read",), now=1050.0)
    assert tok == "tok-access-initial"

    with pytest.raises(PermissionError):
        broker.get_valid_access_token("remote_tok", host="evil.example.net", required_scopes=("repo.read",), now=1050.0)
    with pytest.raises(PermissionError):
        broker.get_valid_access_token("remote_tok", host="api.example.org", required_scopes=("admin.delete",), now=1050.0)

    refreshed = broker.get_valid_access_token(
        "remote_tok",
        host="api.example.org",
        required_scopes=("repo.read",),
        now=1200.0,
        refresh_fn=lambda rt, h, sc: {"access_token": "tok-access-rotated", "refresh_token": "tok-refresh-2", "expires_in": 3600, "scope": "repo.read"},
    )
    assert refreshed == "tok-access-rotated"


def test_rfc9421_oauth1_signer_tamper_grant_and_zero_secret_leakage(tmp_path):
    canary_key = "CANARY_SECRET_994_DO_NOT_LEAK_7711"
    ks = MemoryKeystore(namespace="signing")
    ks.put("api_hmac_key", canary_key)
    receipts_file = tmp_path / "signer_receipts.jsonl"

    signer = AccountableRequestSigner(
        keystore=ks,
        allowed_hosts=("api.example.org",),
        allowed_methods=("POST",),
        allowed_actions=("oauth.sign_request",),
        receipts_path=str(receipts_file),
    )
    body = b'{"action":"deploy-check"}'
    signed = signer.sign_rfc9421(
        method="POST", url="https://api.example.org/v1/checks",
        body=body, key_id="key-2026", key_handle="api_hmac_key", created=1764200000,
    )
    ok, detail = verify_http_request_rfc9421(
        method="POST", url="https://api.example.org/v1/checks",
        body=body, headers=signed["headers"], signing_key=canary_key,
    )
    assert ok and detail == "MATCH"

    # 1-byte body, path, and signature tamper checks
    ok_body, _ = verify_http_request_rfc9421(
        method="POST", url="https://api.example.org/v1/checks",
        body=b'{"action":"deploy-checX"}', headers=signed["headers"], signing_key=canary_key,
    )
    assert not ok_body
    ok_path, _ = verify_http_request_rfc9421(
        method="POST", url="https://api.example.org/v1/checkX",
        body=body, headers=signed["headers"], signing_key=canary_key,
    )
    assert not ok_path
    bad_hdrs = dict(signed["headers"])
    bad_hdrs["Signature"] = bad_hdrs["Signature"][:-3] + ("A" if bad_hdrs["Signature"][-3] != "A" else "B") + ":"
    ok_sig, _ = verify_http_request_rfc9421(
        method="POST", url="https://api.example.org/v1/checks",
        body=body, headers=bad_hdrs, signing_key=canary_key,
    )
    assert not ok_sig

    # Pluggable Ed25519 callback path
    ed_hdrs = sign_http_request_rfc9421(
        method="POST", url="https://api.example.org/v1/checks", body=body, key_id="ed-key-1",
        alg="ed25519", created=1764200000,
        ed25519_signer=lambda msg: hmac.new(b"ed25519-mock-priv", msg, hashlib.sha256).digest(),
    )
    ok_ed, _ = verify_http_request_rfc9421(
        method="POST", url="https://api.example.org/v1/checks", body=body, headers=ed_hdrs,
        ed25519_verifier=lambda msg, sig: hmac.compare_digest(hmac.new(b"ed25519-mock-priv", msg, hashlib.sha256).digest(), sig),
    )
    assert ok_ed

    # OAuth 1.0a HMAC-SHA256 header builder
    oauth1 = build_oauth1_authorization_header(
        method="POST", url="https://api.example.org/v1/status?mode=dry",
        consumer_key="ck-pub", consumer_secret=canary_key,
        token="tk-pub", token_secret="CANARY_TOK_SECRET_8822",
        timestamp=1764200000, nonce="fixednonce123",
    )
    assert oauth1.startswith("OAuth ") and 'oauth_signature_method="HMAC-SHA256"' in oauth1
    assert canary_key not in oauth1 and "CANARY_TOK_SECRET_8822" not in oauth1

    # Unauthorized host/method/action refusals
    with pytest.raises(PermissionError) as exc_host:
        signer.sign_rfc9421(method="POST", url="https://untrusted.example.net/x", key_id="k", key_handle="api_hmac_key")
    with pytest.raises(PermissionError) as exc_method:
        signer.sign_rfc9421(method="DELETE", url="https://api.example.org/v1/checks", key_id="k", key_handle="api_hmac_key")
    no_grant_signer = AccountableRequestSigner(keystore=ks, allowed_hosts=("api.example.org",), allowed_actions=("fs.read",))
    with pytest.raises(PermissionError):
        no_grant_signer.sign_rfc9421(method="POST", url="https://api.example.org/v1/checks", key_id="k", key_handle="api_hmac_key")

    # Verify action-receipt/v1 stream offline AND assert zero secret leakage everywhere
    receipts_text = receipts_file.read_text(encoding="utf-8")
    r_label, _ = verify_receipts(receipts_text)
    assert r_label == "MATCH"
    for surface in (
        receipts_text,
        json.dumps(signed),
        repr(ks),
        str(exc_host.value),
        str(exc_method.value),
        redact_secrets(f"debug {canary_key} done", (canary_key,)),
    ):
        assert canary_key not in surface
