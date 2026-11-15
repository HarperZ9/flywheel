import base64
import itertools
import json

from relay.oauth import RegisteredClient, pkce_challenge
from relay.remote_mcp import RemoteMcpConfig, process
from relay.remote_oauth import (
    OAuthSettings,
    access_token_ok,
    authorization_server_endpoint,
    authorize_endpoint,
    protected_resource_endpoint,
    token_endpoint,
)

VERIFIER = "v" * 64
REDIRECT = "https://claude.ai/api/mcp/auth_callback"
CLIENT = RegisteredClient("cid", "csecret", frozenset({REDIRECT}))


def _oauth(now=1000):
    ids = itertools.count(1)
    return OAuthSettings(
        client=CLIENT, signing_secret="sign", base_url="https://pc.example/",
        authorize_password="approve", clock=lambda: now, id_source=lambda: f"id{next(ids)}",
    )


def _basic(user, pw):
    return "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()


def _authorize(o, **over):
    q = {"response_type": "code", "redirect_uri": REDIRECT,
         "code_challenge": pkce_challenge(VERIFIER), "code_challenge_method": "S256"}
    q.update(over)
    return authorize_endpoint(o, {"authorization": _basic("op", "approve")}, q)


def _code_from(location):
    return location.split("code=", 1)[1].split("&", 1)[0]


# --- discovery metadata ---

def test_metadata_endpoints():
    o = _oauth()
    s, _, b = protected_resource_endpoint(o)
    assert s == 200 and json.loads(b)["resource"] == "https://pc.example/mcp"
    s, _, b = authorization_server_endpoint(o)
    md = json.loads(b)
    assert md["token_endpoint"] == "https://pc.example/token"
    assert md["code_challenge_methods_supported"] == ["S256"]


# --- /authorize operator gate ---

def test_authorize_requires_operator_basic():
    s, h, _ = authorize_endpoint(
        _oauth(), {}, {"response_type": "code", "redirect_uri": REDIRECT,
                       "code_challenge": pkce_challenge(VERIFIER), "code_challenge_method": "S256"})
    assert s == 401 and "Basic" in h["WWW-Authenticate"]


def test_authorize_wrong_password_is_401():
    s, _, _ = authorize_endpoint(
        _oauth(), {"authorization": _basic("op", "nope")},
        {"response_type": "code", "redirect_uri": REDIRECT,
         "code_challenge": pkce_challenge(VERIFIER), "code_challenge_method": "S256"})
    assert s == 401


def test_authorize_approved_redirects_with_code():
    s, h, _ = _authorize(_oauth(), state="st")
    assert s == 302
    assert h["Location"].startswith(REDIRECT + "?code=") and "state=st" in h["Location"]


# --- full flow: authorize -> token -> access token accepted by /mcp ---

def test_full_flow_token_is_accepted_by_mcp():
    o = _oauth()
    _, h, _ = _authorize(o)
    code = _code_from(h["Location"])
    s, _, b = token_endpoint(o, {}, {
        "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
        "client_secret": "csecret", "code_verifier": VERIFIER})
    assert s == 200
    access = json.loads(b)["access_token"]
    assert access_token_ok(o, access)

    cfg = RemoteMcpConfig(token="static-admin", oauth=o)
    status, _, _ = process(
        cfg, "POST", {"authorization": f"Bearer {access}"},
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode())
    assert status == 200  # the OAuth-issued token drives /mcp


def test_token_endpoint_rejects_bad_client_secret():
    o = _oauth()
    _, h, _ = _authorize(o)
    code = _code_from(h["Location"])
    s, _, b = token_endpoint(o, {}, {
        "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
        "client_secret": "WRONG", "code_verifier": VERIFIER})
    assert s == 401 and json.loads(b)["error"] == "invalid_client"


def test_client_secret_via_http_basic_is_accepted():
    o = _oauth()
    _, h, _ = _authorize(o)
    code = _code_from(h["Location"])
    s, _, _ = token_endpoint(
        o, {"authorization": _basic("cid", "csecret")},
        {"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
         "code_verifier": VERIFIER})
    assert s == 200  # client_secret_basic auth method


# --- /mcp OAuth integration ---

def test_mcp_401_points_at_resource_metadata_when_oauth_on():
    cfg = RemoteMcpConfig(token="static-admin", oauth=_oauth())
    status, headers, _ = process(cfg, "POST", {}, b"{}")
    assert status == 401
    assert 'resource_metadata="https://pc.example/.well-known/oauth-protected-resource"' in headers["WWW-Authenticate"]


def test_static_bearer_still_works_with_oauth_on():
    # the local PC / Flywheel path keeps using the static admin token
    cfg = RemoteMcpConfig(token="static-admin", oauth=_oauth())
    status, _, _ = process(
        cfg, "POST", {"authorization": "Bearer static-admin"},
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}).encode())
    assert status == 200


def test_handler_routes_discovery_and_mcp_401_over_socket():
    import threading
    import urllib.error
    import urllib.request

    from relay.remote_mcp import RemoteMcpConfig, serve

    server = serve(RemoteMcpConfig(token="static-admin", oauth=_oauth()), host="127.0.0.1", port=0)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        for path in ("/.well-known/oauth-protected-resource", "/.well-known/oauth-protected-resource/mcp"):
            with urllib.request.urlopen(base + path, timeout=5) as r:
                assert r.status == 200 and json.loads(r.read())["resource"] == "https://pc.example/mcp"
        with urllib.request.urlopen(base + "/.well-known/oauth-authorization-server", timeout=5) as r:
            assert json.loads(r.read())["code_challenge_methods_supported"] == ["S256"]
        req = urllib.request.Request(base + "/mcp", method="POST", data=b"{}")
        try:
            urllib.request.urlopen(req, timeout=5)
            raise AssertionError("expected 401")
        except urllib.error.HTTPError as e:
            assert e.code == 401 and "resource_metadata" in e.headers.get("WWW-Authenticate", "")
    finally:
        server.shutdown()
        server.server_close()
        t.join(timeout=5)


def test_token_endpoint_refresh_grant_and_client_auth():
    o = _oauth()
    _, h, _ = _authorize(o)
    code = _code_from(h["Location"])
    _, _, b = token_endpoint(o, {}, {
        "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
        "client_secret": "csecret", "code_verifier": VERIFIER})
    refresh = json.loads(b)["refresh_token"]

    s, _, b2 = token_endpoint(o, {}, {
        "grant_type": "refresh_token", "refresh_token": refresh, "client_secret": "csecret"})
    assert s == 200 and json.loads(b2)["access_token"]

    s2, _, b3 = token_endpoint(o, {}, {
        "grant_type": "refresh_token", "refresh_token": refresh, "client_secret": "WRONG"})
    assert s2 == 401 and json.loads(b3)["error"] == "invalid_client"
