"""Falsifiers for OAuth sign-in to HTTP MCP servers, against a loopback fake.

The fake plays the MCP server and its authorization server: a 401 with
resource metadata, RFC 8414 metadata, dynamic registration, an authorize
endpoint that redirects with a code, and a token endpoint that checks the PKCE
verifier against the challenge it was given.
"""
import base64
import hashlib
import json
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from harness import keychain
from harness.code_session import mcp_oauth
from harness.code_session.mcp_config import ServerSpec, connect

STATE = {}


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, obj, extra=None):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        base = STATE["base"]
        u = urllib.parse.urlparse(self.path)
        if u.path == "/.well-known/oauth-protected-resource":
            return self._json(200, {"resource": base + "/mcp", "authorization_servers": [base]})
        if u.path == "/.well-known/oauth-authorization-server":
            return self._json(200, {"issuer": base, "authorization_endpoint": base + "/authorize",
                                    "token_endpoint": base + "/token",
                                    "registration_endpoint": base + "/register",
                                    "code_challenge_methods_supported": ["S256"]})
        if u.path == "/authorize":
            q = dict(urllib.parse.parse_qsl(u.query))
            STATE["authorize"] = q
            loc = q["redirect_uri"] + "?" + urllib.parse.urlencode(
                {"code": "code-123", "state": q["state"]})
            self.send_response(302)
            self.send_header("Location", loc)
            self.end_headers()
            return
        self._json(404, {})

    def do_POST(self):
        base = STATE["base"]
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n).decode()
        if self.path == "/register":
            STATE["register"] = json.loads(raw)
            return self._json(201, {"client_id": "client-1"})
        if self.path == "/token":
            form = dict(urllib.parse.parse_qsl(raw))
            STATE.setdefault("token", []).append(form)
            if form["grant_type"] == "authorization_code":
                digest = hashlib.sha256(form["code_verifier"].encode()).digest()
                challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
                if challenge != STATE["authorize"]["code_challenge"] or form["code"] != "code-123":
                    return self._json(400, {"error": "invalid_grant"})
                return self._json(200, {"access_token": "tok-1", "refresh_token": "r-1",
                                        "expires_in": 3600})
            return self._json(200, {"access_token": "tok-2", "expires_in": 3600})
        if self.path == "/mcp":
            auth = self.headers.get("Authorization", "")
            if auth not in ("Bearer tok-1", "Bearer tok-2"):
                meta = base + "/.well-known/oauth-protected-resource"
                return self._json(401, {"error": "unauthorized"}, {
                    "WWW-Authenticate": f'Bearer resource_metadata="{meta}"'})
            msg = json.loads(raw)
            STATE.setdefault("mcp_auth", []).append(auth)
            if "id" not in msg:
                self.send_response(202)
                self.end_headers()
                return
            res = {"initialize": {"protocolVersion": "2025-06-18", "capabilities": {},
                                  "serverInfo": {"name": "fake"}},
                   "tools/list": {"tools": [{"name": "ping", "inputSchema": {}}]}}.get(
                msg["method"], {})
            return self._json(200, {"jsonrpc": "2.0", "id": msg["id"], "result": res})
        self._json(404, {})


@pytest.fixture
def fake():
    STATE.clear()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    STATE["base"] = f"http://127.0.0.1:{srv.server_address[1]}"
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield STATE["base"]
    srv.shutdown()


def _browser(url):
    urllib.request.urlopen(url, timeout=10).read()


def test_login_runs_the_whole_flow_with_pkce_and_resource(fake):
    record = mcp_oauth.login(fake + "/mcp", browser=_browser, timeout=20)
    assert record["access_token"] == "tok-1" and record["refresh_token"] == "r-1"
    q = STATE["authorize"]
    assert q["code_challenge_method"] == "S256" and q["client_id"] == "client-1"
    assert q["resource"] == fake + "/mcp"
    assert STATE["register"]["token_endpoint_auth_method"] == "none"
    assert STATE["token"][0]["resource"] == fake + "/mcp"


def test_stored_token_reaches_the_server_and_refreshes_when_expired(fake, tmp_path, monkeypatch):
    monkeypatch.setattr(keychain, "keychain_available", lambda: False)
    home = str(tmp_path / "home")
    record = mcp_oauth.login(fake + "/mcp", browser=_browser, timeout=20)
    mcp_oauth.save_token(home, "board", record)
    spec = ServerSpec(name="board", source="x", trusted=True, url=fake + "/mcp")
    client, tools = connect(spec, home=home)
    client.close()
    assert "mcp__board__ping" in tools and STATE["mcp_auth"][0] == "Bearer tok-1"
    stored = mcp_oauth.load_token(home, "board")
    stored["expires_at"] = 1
    mcp_oauth.save_token(home, "board", stored)
    client, _ = connect(spec, home=home)
    client.close()
    assert STATE["mcp_auth"][-1] == "Bearer tok-2"
    assert mcp_oauth.load_token(home, "board")["refresh_token"] == "r-1"
    assert mcp_oauth.delete_token(home, "board") and mcp_oauth.load_token(home, "board") is None


def test_no_token_names_the_login_command(fake, tmp_path, monkeypatch):
    monkeypatch.setattr(keychain, "keychain_available", lambda: False)
    spec = ServerSpec(name="board", source="x", trusted=True, url=fake + "/mcp")
    with pytest.raises(Exception) as err:
        connect(spec, home=str(tmp_path))
    assert "flywheel mcp login board" in str(err.value)


def test_a_wrong_verifier_is_refused_by_the_fake(fake, monkeypatch):
    monkeypatch.setattr(mcp_oauth, "pkce_pair", lambda: ("wrong-verifier", "not-the-hash"))
    with pytest.raises(mcp_oauth.OAuthError):
        mcp_oauth.login(fake + "/mcp", browser=_browser, timeout=20)
