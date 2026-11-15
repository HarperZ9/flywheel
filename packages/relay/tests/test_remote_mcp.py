import json
import threading
import urllib.request

from relay.remote_mcp import (
    RemoteMcpConfig,
    config_from_env,
    make_handler,
    process,
    serve,
)
from relay.local_mcp import PROTOCOL

TOKEN = "s3cret-remote-token"


def _cfg(**over):
    base = dict(token=TOKEN)
    base.update(over)
    return RemoteMcpConfig(**base)


def _auth(tok=TOKEN):
    return {"authorization": f"Bearer {tok}"}


def _post(cfg, obj, headers=None):
    h = {**_auth(), "content-type": "application/json", **(headers or {})}
    return process(cfg, "POST", h, json.dumps(obj).encode())


# --- auth + transport gating ---

def test_missing_token_is_401():
    status, _, _ = process(_cfg(), "POST", {}, b"{}")
    assert status == 401


def test_wrong_token_is_401():
    status, _, _ = process(_cfg(), "POST", {"authorization": "Bearer nope"}, b"{}")
    assert status == 401


def test_get_is_405_no_stream():
    status, headers, body = process(_cfg(), "GET", _auth(), b"")
    assert status == 405 and headers.get("Allow") == "POST" and body == b""


def test_initialize_roundtrips_through_handle():
    status, headers, body = _post(_cfg(), {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert status == 200 and headers["Content-Type"] == "application/json"
    assert json.loads(body)["result"]["protocolVersion"] == PROTOCOL


def test_tools_list_is_served():
    status, _, body = _post(_cfg(), {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in json.loads(body)["result"]["tools"]}
    assert status == 200 and {"relay.status", "local_agent_run"} <= names


def test_notification_is_202_no_body():
    status, _, body = _post(_cfg(), {"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert status == 202 and body == b""


def test_unsupported_protocol_version_is_400():
    status, _, _ = _post(
        _cfg(), {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        headers={"mcp-protocol-version": "1999-01-01"},
    )
    assert status == 400


def test_matching_protocol_version_passes():
    status, _, _ = _post(
        _cfg(), {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        headers={"mcp-protocol-version": PROTOCOL},
    )
    assert status == 200


def test_bad_body_is_400():
    status, _, _ = process(_cfg(), "POST", _auth(), b"not json")
    assert status == 400


# --- Origin allowlist (DNS-rebinding guard) ---

def test_disallowed_origin_is_403():
    cfg = _cfg(allowed_origins={"https://claude.ai"})
    status, _, _ = process(cfg, "POST", {**_auth(), "origin": "https://evil.example"}, b"{}")
    assert status == 403


def test_allowed_origin_passes():
    cfg = _cfg(allowed_origins={"https://claude.ai"})
    status, _, _ = _post(cfg, {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
                         headers={"origin": "https://claude.ai"})
    assert status == 200


def test_absent_origin_with_allowlist_still_passes():
    # a non-browser client (the phone connector's server side) sends no Origin
    cfg = _cfg(allowed_origins={"https://claude.ai"})
    status, _, _ = _post(cfg, {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert status == 200


# --- remote-exec posture ---

def _capture():
    from relay.mcp_grants import SURFACE_EXEC_REFUSED

    seen = {}

    def h(req):
        seen["req"] = json.loads(json.dumps(req))  # snapshot as handle sees it
        seen["exec_refused"] = SURFACE_EXEC_REFUSED.get()
        return {"jsonrpc": "2.0", "id": req.get("id"), "result": {"ok": True}}

    return seen, h


def test_remote_exec_is_refused_by_default():
    seen, h = _capture()
    cfg = _cfg(handle=h)  # allow_remote_exec defaults False
    _post(cfg, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": "local_agent_run",
                           "arguments": {"goal": "x", "allow_exec": True, "allow_write": True}}})
    assert seen["exec_refused"] is True  # exec refused on the remote surface
    # the caller's arguments reach the server as sent; the binding records them
    assert seen["req"]["params"]["arguments"] == {"goal": "x", "allow_exec": True,
                                                  "allow_write": True}


def test_remote_exec_allowed_when_pc_opts_in():
    seen, h = _capture()
    cfg = _cfg(handle=h, allow_remote_exec=True)
    _post(cfg, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": "local_agent_run",
                           "arguments": {"goal": "x", "allow_exec": True}}})
    assert seen["exec_refused"] is False


def test_background_start_also_has_exec_forced_off_by_default():
    # local_agent_start carries the same exec risk as local_agent_run, so the
    # remote posture must refuse it too -- otherwise the async path is an exec bypass.
    seen, h = _capture()
    cfg = _cfg(handle=h)  # allow_remote_exec defaults False
    _post(cfg, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": "local_agent_start",
                           "arguments": {"goal": "x", "allow_exec": True, "allow_write": True}}})
    assert seen["exec_refused"] is True


# --- env config + real socket ---

def test_config_from_env_off_without_token():
    assert config_from_env({}) is None
    cfg = config_from_env({"RELAY_REMOTE_TOKEN": "t", "RELAY_ALLOW_REMOTE_EXEC": "true",
                           "RELAY_ALLOWED_ORIGINS": "https://claude.ai, https://chatgpt.com"})
    assert cfg.token == "t" and cfg.allow_remote_exec is True
    assert cfg.allowed_origins == {"https://claude.ai", "https://chatgpt.com"}


def test_behind_a_tls_terminating_proxy_advertises_the_public_https_url():
    # The Cloudflare Tunnel path runs relay as plain HTTP on localhost (no
    # RELAY_TLS_*) while the public identity is the https tunnel hostname. OAuth
    # discovery must advertise that public https URL, not the local http bind, or a
    # phone connector cannot find the authorization server.
    from relay.remote_oauth import (
        authorization_server_endpoint,
        protected_resource_endpoint,
    )

    cfg = config_from_env({
        "RELAY_REMOTE_TOKEN": "t",
        "RELAY_PUBLIC_URL": "https://relay.example.com",  # the Cloudflare tunnel hostname
        "RELAY_OAUTH_CLIENT_ID": "cid", "RELAY_OAUTH_CLIENT_SECRET": "csecret",
        "RELAY_OAUTH_SIGNING_SECRET": "sign", "RELAY_AUTHORIZE_PASSWORD": "pw",
        "RELAY_OAUTH_REDIRECT_URIS": "https://claude.ai/api/mcp/auth_callback",
    })
    assert cfg.oauth is not None and cfg.oauth.base_url == "https://relay.example.com"
    pr = json.loads(protected_resource_endpoint(cfg.oauth)[2])
    assert pr["resource"] == "https://relay.example.com/mcp"
    assert pr["authorization_servers"] == ["https://relay.example.com"]
    md = json.loads(authorization_server_endpoint(cfg.oauth)[2])
    assert md["authorization_endpoint"] == "https://relay.example.com/authorize"
    assert md["token_endpoint"] == "https://relay.example.com/token"


def test_empty_token_is_refused():
    try:
        RemoteMcpConfig(token="")
    except ValueError:
        return
    raise AssertionError("empty token should raise")


def test_serves_over_a_real_socket():
    server = serve(_cfg(), host="127.0.0.1", port=0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/mcp",
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}).encode(),
            headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read())
        assert resp.status == 200
        assert body["result"]["serverInfo"]["name"] == "local-agent"
    finally:
        thread.join(timeout=5)
        server.server_close()
    assert not thread.is_alive()


def test_serve_plain_http_without_cert():
    server = serve(_cfg(), port=0)
    try:
        assert server.server_address[1] > 0  # bound, plain HTTP
    finally:
        server.server_close()


def test_serve_with_missing_cert_raises_and_does_not_leak():
    import pytest
    with pytest.raises(OSError):  # FileNotFoundError from load_cert_chain
        serve(_cfg(), port=0, certfile="/no/such/cert.pem", keyfile="/no/such/key.pem")
