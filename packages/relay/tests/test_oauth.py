import pytest

from relay.oauth import (
    AuthCodeStore,
    InvalidToken,
    OAuthError,
    RegisteredClient,
    authorization_server_metadata,
    authorize,
    exchange_token,
    issue_access_token,
    issue_refresh_token,
    pkce_challenge,
    protected_resource_metadata,
    refresh_grant,
    verify_access_token,
    verify_pkce,
)

SECRET = "server-signing-secret"
VERIFIER = "a" * 64  # a high-entropy code_verifier
CLIENT = RegisteredClient(
    client_id="relay-connector",
    client_secret="client-shhh",
    redirect_uris=frozenset({"https://claude.ai/api/mcp/auth_callback"}),
)


# --- PKCE ---

def test_pkce_s256_roundtrip():
    challenge = pkce_challenge(VERIFIER)
    assert "=" not in challenge  # unpadded base64url
    assert verify_pkce(VERIFIER, challenge)
    assert not verify_pkce("wrong-verifier", challenge)


# --- access tokens ---

def test_token_roundtrip_and_expiry():
    tok = issue_access_token(subject="s", secret=SECRET, now=1000, ttl=3600, nonce="n1")
    claims = verify_access_token(tok, SECRET, now=1500)
    assert claims["sub"] == "s" and claims["scope"] == "mcp"
    with pytest.raises(InvalidToken):
        verify_access_token(tok, SECRET, now=1000 + 3600)  # exp is exclusive


def test_token_tamper_and_wrong_secret_rejected():
    tok = issue_access_token(subject="s", secret=SECRET, now=1000, nonce="n")
    body, sig = tok.split(".", 1)
    with pytest.raises(InvalidToken):
        verify_access_token(body + ".AAAA", SECRET, now=1001)  # bad signature
    with pytest.raises(InvalidToken):
        verify_access_token(tok, "other-secret", now=1001)  # wrong key
    with pytest.raises(InvalidToken):
        verify_access_token("no-dot-token", SECRET, now=1001)  # malformed


# --- full authorization-code + PKCE flow ---

def _authorize(**over):
    args = dict(
        response_type="code",
        redirect_uri="https://claude.ai/api/mcp/auth_callback",
        code_challenge=pkce_challenge(VERIFIER),
        code_challenge_method="S256",
        code="authcode-1",
        now=1000,
        state="xyz",
    )
    args.update(over)
    return authorize(CLIENT, **args)


def test_full_flow_issues_a_usable_token():
    store = AuthCodeStore()
    result = _authorize()
    assert result.redirect_url.startswith("https://claude.ai/api/mcp/auth_callback?code=authcode-1")
    assert "state=xyz" in result.redirect_url
    store.put(result.auth_code)

    resp = exchange_token(
        CLIENT, store,
        grant_type="authorization_code", code="authcode-1",
        redirect_uri="https://claude.ai/api/mcp/auth_callback",
        client_secret="client-shhh", code_verifier=VERIFIER,
        secret=SECRET, now=1100, nonce="tok-1",
    )
    assert resp["token_type"] == "Bearer" and resp["expires_in"] == 3600
    assert verify_access_token(resp["access_token"], SECRET, now=1200)["sub"] == "relay-connector"


def test_authorize_requires_s256_and_registered_redirect():
    with pytest.raises(OAuthError):
        _authorize(code_challenge_method="plain")
    with pytest.raises(OAuthError):
        _authorize(code_challenge="")
    with pytest.raises(OAuthError):
        _authorize(redirect_uri="https://evil.example/cb")
    with pytest.raises(OAuthError):
        _authorize(response_type="token")  # implicit grant not allowed


def test_exchange_rejects_bad_secret_bad_pkce_and_replay():
    store = AuthCodeStore()
    store.put(_authorize().auth_code)
    base = dict(
        grant_type="authorization_code", code="authcode-1",
        redirect_uri="https://claude.ai/api/mcp/auth_callback",
        client_secret="client-shhh", code_verifier=VERIFIER,
        secret=SECRET, now=1100, nonce="t",
    )
    with pytest.raises(OAuthError) as e:
        exchange_token(CLIENT, store, **{**base, "client_secret": "wrong"})
    assert e.value.code == "invalid_client"

    store.put(_authorize().auth_code)
    with pytest.raises(OAuthError) as e:
        exchange_token(CLIENT, store, **{**base, "code_verifier": "wrong"})
    assert e.value.code == "invalid_grant"

    # first exchange consumes the code; a replay fails
    store.put(_authorize().auth_code)
    exchange_token(CLIENT, store, **base)
    with pytest.raises(OAuthError) as e:
        exchange_token(CLIENT, store, **{**base, "nonce": "t2"})
    assert e.value.code == "invalid_grant"


def test_expired_code_cannot_be_exchanged():
    store = AuthCodeStore()
    store.put(_authorize(now=1000).auth_code)  # ttl 600 -> exp 1600
    with pytest.raises(OAuthError):
        exchange_token(
            CLIENT, store, grant_type="authorization_code", code="authcode-1",
            redirect_uri="https://claude.ai/api/mcp/auth_callback",
            client_secret="client-shhh", code_verifier=VERIFIER,
            secret=SECRET, now=1601, nonce="t",
        )


def test_unsupported_grant_type_rejected():
    with pytest.raises(OAuthError) as e:
        exchange_token(
            CLIENT, AuthCodeStore(), grant_type="password", code="x",
            redirect_uri="https://claude.ai/api/mcp/auth_callback",
            client_secret="client-shhh", code_verifier=VERIFIER,
            secret=SECRET, now=1, nonce="t",
        )
    assert e.value.code == "unsupported_grant_type"


# --- discovery metadata ---

def test_protected_resource_metadata_shape():
    md = protected_resource_metadata("https://pc.example/mcp", "https://pc.example")
    assert md["resource"] == "https://pc.example/mcp"
    assert md["authorization_servers"] == ["https://pc.example"]


def test_authorization_server_metadata_advertises_s256_code_only():
    md = authorization_server_metadata("https://pc.example/")
    assert md["issuer"] == "https://pc.example"
    assert md["authorization_endpoint"] == "https://pc.example/authorize"
    assert md["token_endpoint"] == "https://pc.example/token"
    assert md["code_challenge_methods_supported"] == ["S256"]
    assert md["grant_types_supported"] == ["authorization_code", "refresh_token"]
    assert md["response_types_supported"] == ["code"]


# --- refresh tokens ---

def test_exchange_returns_a_refresh_token():
    store = AuthCodeStore()
    store.put(_authorize().auth_code)
    resp = exchange_token(
        CLIENT, store, grant_type="authorization_code", code="authcode-1",
        redirect_uri="https://claude.ai/api/mcp/auth_callback", client_secret="client-shhh",
        code_verifier=VERIFIER, secret=SECRET, now=1100, nonce="tok")
    assert resp["access_token"] and resp["refresh_token"]


def test_refresh_grant_issues_new_rotated_access():
    rt = issue_refresh_token(subject="cid", secret=SECRET, now=1000, nonce="r0")
    resp = refresh_grant(rt, secret=SECRET, now=2000, nonce="r1")
    assert resp["token_type"] == "Bearer"
    assert verify_access_token(resp["access_token"], SECRET, now=2100)["sub"] == "cid"
    assert resp["refresh_token"] != rt  # rotated on use


def test_access_and_refresh_tokens_are_not_interchangeable():
    at = issue_access_token(subject="s", secret=SECRET, now=1000, nonce="a")
    with pytest.raises(OAuthError):
        refresh_grant(at, secret=SECRET, now=1100, nonce="x")  # access used as a refresh
    rt = issue_refresh_token(subject="s", secret=SECRET, now=1000, nonce="r")
    with pytest.raises(InvalidToken):
        verify_access_token(rt, SECRET, now=1100)  # refresh used as an access token


def test_expired_or_tampered_refresh_is_invalid_grant():
    rt = issue_refresh_token(subject="s", secret=SECRET, now=1000, ttl=10, nonce="r")
    with pytest.raises(OAuthError):
        refresh_grant(rt, secret=SECRET, now=1011, nonce="x")  # expired
    with pytest.raises(OAuthError):
        refresh_grant(rt + "junk", secret=SECRET, now=1005, nonce="x")  # bad signature
