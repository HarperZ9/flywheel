"""remote_mcp.py — relay's MCP server over Streamable HTTP, for a remote client.

Wraps the transport-free ``local_mcp.handle()`` in the MCP Streamable HTTP
transport (protocol 2025-06-18): a single ``/mcp`` endpoint. A POST carrying one
JSON-RPC request returns one ``application/json`` response -- relay's run_agent
is blocking, so no SSE stream is needed for a usable v1; a POST carrying a
notification/response returns 202. GET returns 405 (relay opens no
server-initiated stream yet). This is what a phone MCP connector drives once the
endpoint is publicly reachable over HTTPS.

Safety posture, hardened versus the same-machine stdio server:
- every request must present the configured bearer token (constant-time check);
- when an allowlist is configured, the Origin header must be on it (the spec's
  DNS-rebinding guard);
- write, exec and the launch root are granted at launch (RELAY_ALLOW_WRITE /
  RELAY_ALLOW_EXEC / RELAY_MCP_ROOT, read by remote_cli from the process
  environment only), and a call can only narrow them;
- exec is refused on top of that unless the operator also opts in at the PC
  (RELAY_ALLOW_REMOTE_EXEC), because relay's run/exec is not root-confined.
The OAuth authorization layer is a later increment (a bearer token gates v1).

``process()`` is transport-free and fully testable without a socket; the HTTP
handler and ``serve()`` are the thin transport around it.
"""
from __future__ import annotations

import hmac
import json
import os
import urllib.parse
from collections.abc import Callable, Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .local_mcp import PROTOCOL, handle as _default_handle
from .mcp_grants import REMOTE_EXEC_ENV, SURFACE_EXEC_REFUSED, parse_flag
from .remote_oauth import (
    OAuthSettings,
    access_token_ok,
    authorization_server_endpoint,
    authorize_endpoint,
    protected_resource_endpoint,
    token_endpoint,
)

_MAX_BODY = 1 << 20  # 1 MiB request-body cap
_ENDPOINT = "/mcp"


class RemoteMcpConfig:
    """The remote surface's policy: the bearer token, an optional Origin
    allowlist, whether remote exec is permitted, and the JSON-RPC handler
    (injectable for tests)."""

    def __init__(
        self,
        *,
        token: str,
        allowed_origins=frozenset(),
        allow_remote_exec: bool = False,
        handle: Callable[[dict], dict | None] | None = None,
        oauth: OAuthSettings | None = None,
    ) -> None:
        if not token:
            raise ValueError("a non-empty bearer token is required for the remote surface")
        self.token = token
        self.allowed_origins = frozenset(allowed_origins)
        self.allow_remote_exec = allow_remote_exec
        self.handle = handle or _default_handle
        # When set, /mcp also accepts an OAuth access token this server issued, and
        # the /authorize, /token, and .well-known discovery endpoints are served, so
        # a phone MCP connector can drive the agent. The static bearer keeps working
        # (the local PC / Flywheel path uses it).
        self.oauth = oauth


def _oauth_from_env(env: Mapping[str, str]) -> OAuthSettings | None:
    """Build OAuthSettings when the full OAuth env is present, else None (the
    surface then runs with the static bearer only, for the local/PC path)."""
    from .oauth import RegisteredClient

    client_id = env.get("RELAY_OAUTH_CLIENT_ID")
    client_secret = env.get("RELAY_OAUTH_CLIENT_SECRET")
    signing = env.get("RELAY_OAUTH_SIGNING_SECRET")
    base_url = env.get("RELAY_PUBLIC_URL")
    approve = env.get("RELAY_AUTHORIZE_PASSWORD")
    redirects = {r.strip() for r in env.get("RELAY_OAUTH_REDIRECT_URIS", "").split(",") if r.strip()}
    if not (client_id and client_secret and signing and base_url and approve and redirects):
        return None
    return OAuthSettings(
        client=RegisteredClient(client_id, client_secret, frozenset(redirects)),
        signing_secret=signing,
        base_url=base_url,
        authorize_password=approve,
    )


def config_from_env(env: Mapping[str, str] | None = None) -> RemoteMcpConfig | None:
    """Build a RemoteMcpConfig from the environment, or None when
    RELAY_REMOTE_TOKEN is unset (the remote surface stays off by default). When
    the RELAY_OAUTH_* vars are also present, the OAuth phone-connector flow is on."""
    env = os.environ if env is None else env
    token = env.get("RELAY_REMOTE_TOKEN")
    if not token:
        return None
    origins = {o.strip() for o in env.get("RELAY_ALLOWED_ORIGINS", "").split(",") if o.strip()}
    # Parsed like the launch grants: an unrecognized value raises, never off.
    exec_ok = parse_flag(env, REMOTE_EXEC_ENV)
    return RemoteMcpConfig(
        token=token, allowed_origins=origins, allow_remote_exec=exec_ok,
        oauth=_oauth_from_env(env),
    )


def _json(status: int, obj) -> tuple[int, dict, bytes]:
    return status, {"Content-Type": "application/json"}, json.dumps(obj).encode("utf-8")


def _bearer_ok(authorization: str | None, token: str) -> bool:
    prefix = "Bearer "
    if not authorization or not authorization.startswith(prefix):
        return False
    return hmac.compare_digest(authorization[len(prefix):].strip(), token)


def _authorized(cfg: "RemoteMcpConfig", authorization: str | None) -> bool:
    """Accept the static bearer (the local/PC path) or, when OAuth is configured,
    a valid OAuth access token this server issued (the phone-connector path)."""
    if _bearer_ok(authorization, cfg.token):
        return True
    if cfg.oauth is not None and authorization and authorization.startswith("Bearer "):
        return access_token_ok(cfg.oauth, authorization[len("Bearer "):].strip())
    return False


def _handle(cfg: RemoteMcpConfig, req: dict):
    """Run the handler with the remote exec posture. relay's shell is not
    root-confined, so without RELAY_ALLOW_REMOTE_EXEC every tool call on this
    surface runs with exec refused: no run tool, no check, no test_cmd and no
    agentic CLI tier. The run still proceeds without exec. The refusal travels in
    a context variable, so the caller's arguments are left as sent and no field
    in the request can set or clear it."""
    token = SURFACE_EXEC_REFUSED.set(not cfg.allow_remote_exec)
    try:
        return cfg.handle(req)
    finally:
        SURFACE_EXEC_REFUSED.reset(token)


def process(
    cfg: RemoteMcpConfig, method: str, headers: Mapping[str, str], body: bytes
) -> tuple[int, dict, bytes]:
    """Handle one HTTP request to the MCP endpoint. Transport-free: returns
    (status, response_headers, response_body). ``headers`` keys are lowercase."""
    origin = headers.get("origin")
    if cfg.allowed_origins and origin is not None and origin not in cfg.allowed_origins:
        return _json(403, {"error": "origin not allowed"})
    if not _authorized(cfg, headers.get("authorization")):
        out = {"Content-Type": "application/json"}
        if cfg.oauth is not None:
            # RFC 9728: point the client at the protected-resource metadata so it
            # can discover the authorization server and start the OAuth flow.
            out["WWW-Authenticate"] = f'Bearer resource_metadata="{cfg.oauth.resource_metadata_url}"'
        return 401, out, json.dumps({"error": "missing or invalid bearer token"}).encode("utf-8")
    if method == "GET":
        # relay offers no server-initiated SSE stream on the endpoint yet
        return 405, {"Allow": "POST"}, b""
    if method != "POST":
        return _json(405, {"error": f"method {method} not allowed"})
    version = headers.get("mcp-protocol-version")
    if version is not None and version != PROTOCOL:
        return _json(400, {"error": f"unsupported MCP-Protocol-Version {version!r}"})
    if len(body) > _MAX_BODY:
        return _json(413, {"error": "request body too large"})
    try:
        req = json.loads(body)
    except json.JSONDecodeError:
        return _json(400, {"error": "body is not valid JSON-RPC"})
    if not isinstance(req, dict):
        return _json(400, {"error": "JSON-RPC message must be an object"})
    resp = _handle(cfg, req)
    if resp is None:
        # a notification or response the server accepts carries no reply body
        return 202, {}, b""
    return _json(200, resp)


def make_handler(cfg: RemoteMcpConfig):
    class _Handler(BaseHTTPRequestHandler):
        def _dispatch(self, method: str) -> None:
            raw = self.path
            path = raw.split("?", 1)[0]
            length = int(self.headers.get("Content-Length") or 0)
            if length > _MAX_BODY:
                self._send(*_json(413, {"error": "request body too large"}))
                return
            body = self.rfile.read(length) if length else b""
            lower = {k.lower(): v for k, v in self.headers.items()}
            if cfg.oauth is not None:
                if method == "GET" and path in (
                    "/.well-known/oauth-protected-resource",
                    "/.well-known/oauth-protected-resource/mcp",
                ):
                    # a connector may probe the bare path or the resource-suffixed
                    # variant (RFC 9728); serve the same metadata for both
                    self._send(*protected_resource_endpoint(cfg.oauth))
                    return
                if method == "GET" and path == "/.well-known/oauth-authorization-server":
                    self._send(*authorization_server_endpoint(cfg.oauth))
                    return
                if method == "GET" and path == "/authorize":
                    query = dict(urllib.parse.parse_qsl(raw.split("?", 1)[1] if "?" in raw else ""))
                    self._send(*authorize_endpoint(cfg.oauth, lower, query))
                    return
                if method == "POST" and path == "/token":
                    form = dict(urllib.parse.parse_qsl(body.decode("utf-8", "replace")))
                    self._send(*token_endpoint(cfg.oauth, lower, form))
                    return
            if path == _ENDPOINT:
                self._send(*process(cfg, method, lower, body))
                return
            self._send(*_json(404, {"error": f"no endpoint {path!r}; use {_ENDPOINT}"}))

        def do_POST(self) -> None:
            self._dispatch("POST")

        def do_GET(self) -> None:
            self._dispatch("GET")

        def _send(self, status: int, headers: dict, body: bytes) -> None:
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)

        def log_message(self, *args) -> None:  # keep the server quiet
            return None

    return _Handler


def serve(
    cfg: RemoteMcpConfig,
    host: str = "127.0.0.1",
    port: int = 8787,
    *,
    certfile: str | None = None,
    keyfile: str | None = None,
) -> ThreadingHTTPServer:
    """Build (do not start) a ThreadingHTTPServer for the remote MCP endpoint.

    With ``certfile``/``keyfile`` the listening socket is wrapped in TLS, so the
    server speaks HTTPS directly -- what a phone MCP connector requires (it needs
    a publicly-valid certificate; use a Let's Encrypt cert for your DDNS name, the
    PEM files a stdlib ssl context loads). Without them it serves plain HTTP for
    localhost / the PC path. The caller runs ``serve_forever()``.
    """
    server = ThreadingHTTPServer((host, port), make_handler(cfg))
    if certfile and keyfile:
        import ssl

        try:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(certfile, keyfile)
            server.socket = context.wrap_socket(server.socket, server_side=True)
        except Exception:
            server.server_close()  # do not leak the bound socket on a cert error
            raise
    return server


if __name__ == "__main__":  # pragma: no cover
    from .remote_cli import main

    raise SystemExit(main())
