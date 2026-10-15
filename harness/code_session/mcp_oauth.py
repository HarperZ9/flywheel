"""mcp_oauth.py -- sign in to an MCP server over HTTP with OAuth (MCP authorization).

`flywheel mcp login NAME` follows the MCP authorization flow for a server
configured with a url:

1. ask the server once with no token; a 401 names its protected-resource
   metadata (RFC 9728), or the well-known path is tried;
2. read the authorization server's metadata (RFC 8414, then OpenID discovery);
3. register a public client dynamically (RFC 7591) when the server offers it;
4. open the browser on an authorization-code request with PKCE S256 and the
   resource indicator (RFC 8707), and catch the code on a one-shot loopback
   listener with a random path and a checked state;
5. exchange the code, and later refresh the token, at the token endpoint.

Tokens are kept in the OS credential store where Flywheel has one (Windows);
elsewhere in FLYWHEEL_HOME/mcp-tokens/<name>.json with owner-only permissions.
They are sent only to the server they were issued for, never logged and never
written to a ledger. `flywheel mcp logout NAME` removes them.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class OAuthError(RuntimeError):
    """The sign-in could not complete; the message says which step stopped."""


def _get_json(url: str, opener, timeout: float = 15.0) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with opener(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post(url: str, data: dict, opener, *, form: bool, timeout: float = 15.0) -> dict:
    body = (urllib.parse.urlencode(data) if form else json.dumps(data)).encode("utf-8")
    ctype = "application/x-www-form-urlencoded" if form else "application/json"
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": ctype, "Accept": "application/json"})
    try:
        with opener(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode("utf-8", "replace")
        raise OAuthError(f"{url} answered {e.code}: {detail}") from None


def _origin(url: str) -> str:
    p = urllib.parse.urlsplit(url)
    return f"{p.scheme}://{p.netloc}"


def resource_metadata_url(server_url: str, opener) -> str:
    """Where the server's protected-resource metadata lives."""
    probe = urllib.request.Request(server_url, data=b"{}", method="POST",
                                   headers={"Content-Type": "application/json"})
    try:
        with opener(probe, timeout=15.0):
            raise OAuthError(f"{server_url} answered without asking for a token; "
                             "no sign-in is needed")
    except urllib.error.HTTPError as e:
        challenge = e.headers.get("WWW-Authenticate", "") if e.headers else ""
        found = re.search(r'resource_metadata="([^"]+)"', challenge)
        if found:
            return found.group(1)
    return _origin(server_url) + "/.well-known/oauth-protected-resource"


def discover(server_url: str, opener) -> dict:
    """{"resource", "issuer", "authorization_endpoint", "token_endpoint", ...}."""
    prm = _get_json(resource_metadata_url(server_url, opener), opener)
    servers = prm.get("authorization_servers") or []
    if not servers:
        raise OAuthError("the server's metadata names no authorization server")
    issuer = servers[0].rstrip("/")
    meta = None
    for path in ("/.well-known/oauth-authorization-server", "/.well-known/openid-configuration"):
        try:
            meta = _get_json(issuer + path, opener)
            break
        except (urllib.error.URLError, ValueError):
            continue
    if not meta or not meta.get("authorization_endpoint") or not meta.get("token_endpoint"):
        raise OAuthError(f"no usable authorization server metadata at {issuer}")
    if "S256" not in (meta.get("code_challenge_methods_supported") or ["S256"]):
        raise OAuthError("the authorization server does not offer PKCE S256")
    return {**meta, "resource": prm.get("resource") or server_url}


def pkce_pair() -> "tuple[str, str]":
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def login(server_url: str, *, opener=urllib.request.urlopen, browser=None,
          timeout: float = 300.0) -> dict:
    """Run the flow; returns the token record to store."""
    from harness.oauth_callback import CallbackServer
    meta = discover(server_url, opener)
    state = secrets.token_urlsafe(24)
    server = CallbackServer(expected_state=state)
    redirect = server.callback_url
    client_id = meta.get("client_id_hint", "")
    if meta.get("registration_endpoint"):
        reg = _post(meta["registration_endpoint"], {
            "client_name": "Flywheel", "redirect_uris": [redirect],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"], "token_endpoint_auth_method": "none"},
            opener, form=False)
        client_id = reg.get("client_id", "")
    if not client_id:
        server.server_close()
        raise OAuthError("the server offers no dynamic client registration; "
                         "a pre-registered client id is not supported yet")
    verifier, challenge = pkce_pair()
    query = {"response_type": "code", "client_id": client_id, "redirect_uri": redirect,
             "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
             "resource": meta["resource"]}
    if meta.get("scopes_supported"):
        query["scope"] = " ".join(meta["scopes_supported"])
    url = meta["authorization_endpoint"] + "?" + urllib.parse.urlencode(query)
    if browser is None:
        import webbrowser
        print(f"Opening your browser to sign in. If it does not open, visit:\n  {url}")
        browser = webbrowser.open
    import threading
    threading.Thread(target=browser, args=(url,), daemon=True).start()
    code = server.wait_for_code(timeout)
    if not code:
        raise OAuthError(f"no authorization code arrived ({server.error or 'timed out'})")
    tok = _post(meta["token_endpoint"], {
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect,
        "client_id": client_id, "code_verifier": verifier, "resource": meta["resource"]},
        opener, form=True)
    return _record(tok, client_id, meta)


def _record(tok: dict, client_id: str, meta: dict) -> dict:
    if not tok.get("access_token"):
        raise OAuthError("the token endpoint returned no access token")
    expires = tok.get("expires_in")
    return {"access_token": tok["access_token"], "refresh_token": tok.get("refresh_token", ""),
            "expires_at": time.time() + float(expires) if expires else 0,
            "client_id": client_id, "token_endpoint": meta["token_endpoint"],
            "resource": meta["resource"]}


def refresh(record: dict, opener=urllib.request.urlopen) -> dict:
    if not record.get("refresh_token"):
        raise OAuthError("the token expired and no refresh token was issued; "
                         "run `flywheel mcp login` again")
    tok = _post(record["token_endpoint"], {
        "grant_type": "refresh_token", "refresh_token": record["refresh_token"],
        "client_id": record["client_id"], "resource": record["resource"]}, opener, form=True)
    new = _record(tok, record["client_id"], record)
    new["refresh_token"] = new["refresh_token"] or record["refresh_token"]
    return new


# -- token storage -----------------------------------------------------------

def _key(name: str) -> str:
    return "MCP_OAUTH_" + re.sub(r"[^A-Za-z0-9]", "_", name).upper()


def _file(home: str, name: str) -> Path:
    return Path(home) / "mcp-tokens" / (re.sub(r"[^A-Za-z0-9_.-]", "_", name) + ".json")


def save_token(home: str, name: str, record: dict) -> str:
    from harness import keychain
    raw = json.dumps(record)
    if keychain.keychain_available():
        keychain.keychain_set(_key(name), raw)
        return "the OS credential store"
    path = _file(home, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(raw)
    return str(path)


def load_token(home: str, name: str) -> "dict | None":
    from harness import keychain
    raw = keychain.keychain_get(_key(name)) if keychain.keychain_available() else None
    if raw is None:
        path = _file(home, name)
        raw = path.read_text(encoding="utf-8") if path.is_file() else None
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def delete_token(home: str, name: str) -> bool:
    from harness import keychain
    gone = False
    if keychain.keychain_available() and keychain.keychain_get(_key(name)) is not None:
        keychain.keychain_delete(_key(name))
        gone = True
    path = _file(home, name)
    if path.is_file():
        path.unlink()
        gone = True
    return gone


def bearer_for(home: str, name: str, opener=urllib.request.urlopen) -> "str | None":
    """A current access token for the server, refreshed and re-saved if expired."""
    record = load_token(home, name)
    if record is None:
        return None
    if record.get("expires_at") and record["expires_at"] - 60 < time.time():
        record = refresh(record, opener)
        save_token(home, name, record)
    return record["access_token"]
