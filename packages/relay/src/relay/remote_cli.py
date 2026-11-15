"""remote_cli.py — the ``python -m relay.remote_mcp`` entrypoint.

Loads a .env file (so secrets stay out of the process environment and out of
git), validates the public-URL config, and serves. Kept out of remote_mcp so
the transport module stays within the size gate.
"""
from __future__ import annotations

from . import local_mcp
from .mcp_grants import describe, pin_root, remote_grants
from .remote_mcp import _ENDPOINT, config_from_env, serve
from .remote_state import ignored_file_keys, resolved_env


def listen_port(env) -> int:
    """RELAY_REMOTE_PORT, or 8787 when it is unset or blank."""
    return int(env.get("RELAY_REMOTE_PORT") or 8787)


def main() -> int:
    # Composed by remote_state, so the readout a client asks for is derived
    # from the same environment this entrypoint actually serves. The launch
    # grants, remote exec and the launch root come from the process environment
    # only: a run with the write grant could rewrite the env file.
    env, env_file = resolved_env()
    ignored = ignored_file_keys(env_file)
    if ignored:
        print(f"note: {', '.join(ignored)} in {env_file} ignored; set them in the "
              "environment that starts the server")
    try:
        cfg = config_from_env(env)
    except ValueError as e:
        print(f"error: {e}")
        return 2
    if cfg is None:
        print("remote MCP is off: set RELAY_REMOTE_TOKEN (see .env.example)")
        return 2
    # A wrong public URL silently breaks Anthropic's on-origin OAuth discovery, so
    # fail fast rather than serve an unreachable connector.
    if cfg.oauth is not None and not cfg.oauth.base_url.startswith("https://"):
        print(f"error: RELAY_PUBLIC_URL must be an https origin, got {cfg.oauth.base_url!r}")
        return 2
    try:
        # What this surface will allow: exec only with RELAY_ALLOW_REMOTE_EXEC
        # too, and write only with RELAY_ALLOW_WRITE, so RELAY_ALLOW_EXEC alone
        # grants nothing here. The banner and relay.status then say what runs get.
        grants = pin_root(remote_grants(env))
        port = listen_port(env)
    except ValueError as e:
        print(f"error: {e}")
        return 2
    # A call can only narrow these; the per-request exec refusal stays as a
    # second layer.
    local_mcp.configure(grants)
    host = env.get("RELAY_REMOTE_HOST") or "127.0.0.1"
    certfile = env.get("RELAY_TLS_CERT") or None
    keyfile = env.get("RELAY_TLS_KEY") or None
    server = serve(cfg, host, port, certfile=certfile, keyfile=keyfile)
    scheme = "https" if certfile and keyfile else "http"
    print(f"relay remote MCP on {scheme}://{host}:{port}{_ENDPOINT} "
          f"({describe(grants)}, remote exec {'on' if cfg.allow_remote_exec else 'off'}, "
          f"origins {'any' if not cfg.allowed_origins else len(cfg.allowed_origins)}, "
          f"oauth {'on' if cfg.oauth is not None else 'off'}, tls {scheme == 'https'})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
    return 0
