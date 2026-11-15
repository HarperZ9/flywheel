"""remote_state.py -- whether a phone could reach this workstation, and on what terms.

The remote MCP surface runs as its own process (``python -m relay.remote_mcp``),
so nothing talking to the local stdio server can tell whether it is configured at
all. A client that offers "remote access" and cannot say this is guessing.

This reads the same two sources ``remote_cli`` composes, the env file and the
real environment, and reports without handing back a secret: a value comes back
only for the keys on VALUE_SAFE, and every other key the surface reads is
reported as a boolean.

The half-configured case is the one worth naming. ``_oauth_from_env`` returns
None unless all six of its keys are set, and the server then serves the static
bearer with no phone connector and says nothing about why. Here that reads as
oauth off with the missing keys named.
"""
from __future__ import annotations

import os
import pathlib
from typing import Mapping

from .env_file import DEFAULT_ENV_FILE, env_file_path  # noqa: F401 (re-exported)

# The keys whose values may leave this module. A public URL is the address you
# hand the phone; the listen host, port, origin list and exec flag describe what
# the surface would do. None of them is a credential.
VALUE_SAFE = frozenset({
    "RELAY_PUBLIC_URL", "RELAY_REMOTE_HOST", "RELAY_REMOTE_PORT",
    "RELAY_ALLOWED_ORIGINS", "RELAY_ALLOW_REMOTE_EXEC",
    "RELAY_ALLOW_WRITE", "RELAY_ALLOW_EXEC",
})

# Every other key the remote surface reads. Presence is all that is reported for
# these, whether or not the key happens to hold something secret today.
PRESENCE_ONLY = (
    "RELAY_REMOTE_TOKEN", "RELAY_OAUTH_CLIENT_ID", "RELAY_OAUTH_CLIENT_SECRET",
    "RELAY_OAUTH_SIGNING_SECRET", "RELAY_AUTHORIZE_PASSWORD",
    "RELAY_OAUTH_REDIRECT_URIS", "RELAY_TLS_CERT", "RELAY_TLS_KEY",
)

# What ``_oauth_from_env`` demands before the phone connector exists at all. Miss
# one and the surface still serves, with the static bearer only.
OAUTH_REQUIRED = (
    "RELAY_OAUTH_CLIENT_ID", "RELAY_OAUTH_CLIENT_SECRET",
    "RELAY_OAUTH_SIGNING_SECRET", "RELAY_PUBLIC_URL",
    "RELAY_AUTHORIZE_PASSWORD", "RELAY_OAUTH_REDIRECT_URIS",
)


def _value(raw: str) -> str:
    """One value: the text inside matching quotes, or the text before an unquoted
    ``#`` that follows whitespace. ``KEY=   # note`` is an empty value."""
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] in "\"'" and raw[0] in raw[1:]:
        return raw[1:raw.index(raw[0], 1)]
    if raw.startswith("#"):
        return ""
    for i, ch in enumerate(raw):
        if ch == "#" and raw[i - 1] in " \t":
            return raw[:i].rstrip()
    return raw


def load_dotenv(path: str) -> dict[str, str]:
    """A tiny stdlib .env reader (KEY=value lines, # comments, inline comments
    after whitespace), so secrets live in a file instead of the process
    environment. No dependency; the real environment still wins over the file."""
    file = pathlib.Path(path)
    if not file.exists():
        return {}
    values: dict[str, str] = {}
    for line in file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = _value(value)
    return values


def resolved_env(env: Mapping[str, str] | None = None, env_file: str | None = None,
                 *, read_default: bool = True) -> tuple[dict[str, str], str | None]:
    """The environment the remote server would see, and the file consulted.

    Composed exactly as ``remote_cli.main`` composes it: the file first, the real
    environment over it. The launch grants, remote exec and the launch root
    (LAUNCH_ONLY_KEYS) are never taken from the file: a run with the write grant
    can rewrite that file, and would hand itself exec on the next restart. A
    caller that passes ``env`` is asking about that environment rather than this
    process's. With ``read_default=False`` no file is read unless RELAY_ENV_FILE
    or ``env_file`` names one, and the path comes back None.
    """
    from .mcp_grants import LAUNCH_ONLY_KEYS
    env = dict(os.environ if env is None else env)
    path = env_file if env_file is not None else (
        env_file_path(env) if read_default else env.get("RELAY_ENV_FILE") or None)
    loaded = load_dotenv(path) if path else {}
    from_file = {k: v for k, v in loaded.items() if k not in LAUNCH_ONLY_KEYS}
    return {**from_file, **env}, path


def ignored_file_keys(path: str) -> list[str]:
    """Launch-only keys the env file sets, which the server ignores."""
    from .mcp_grants import LAUNCH_ONLY_KEYS
    return sorted(set(load_dotenv(path)) & set(LAUNCH_ONLY_KEYS))


def _start_grants(resolved: Mapping[str, str]) -> dict:
    from .mcp_grants import remote_grants
    try:
        return remote_grants(resolved).as_dict()
    except ValueError as e:
        return {"error": str(e)}


def _remote_exec(resolved: Mapping[str, str]) -> "bool | dict":
    from .mcp_grants import REMOTE_EXEC_ENV, parse_flag
    try:
        return parse_flag(resolved, REMOTE_EXEC_ENV)
    except ValueError as e:
        return {"error": str(e)}


def _origins(raw: str) -> list[str]:
    return sorted({o.strip() for o in raw.split(",") if o.strip()})


def remote_state(env: Mapping[str, str] | None = None, env_file: str | None = None,
                 *, read_default: bool = True) -> dict:
    """What the phone-facing surface is configured to do, values withheld.

    The stdio doctor passes ``read_default=False``: its working folder is
    whatever folder a client started it in, so a ``.env`` there describes nothing
    the operator configured unless RELAY_ENV_FILE names it.

    ``configured`` answers the only question that gates everything else: with no
    RELAY_REMOTE_TOKEN the entrypoint prints its notice and exits, so nothing
    remote is running whatever else is set.
    """
    resolved, path = resolved_env(env, env_file, read_default=read_default)
    present = {k: bool(resolved.get(k)) for k in PRESENCE_ONLY}
    missing_oauth = [k for k in OAUTH_REQUIRED if not resolved.get(k)]
    configured = present["RELAY_REMOTE_TOKEN"]
    remote_exec, grants = _remote_exec(resolved), _start_grants(resolved)
    state = {
        "configured": configured,
        "reason": "" if configured
                  else "RELAY_REMOTE_TOKEN is unset, so the remote surface stays off",
        "env_file": path,
        "env_file_found": bool(path) and pathlib.Path(path).is_file(),
        "oauth_configured": not missing_oauth,
        # Named, never valued: which keys the phone connector is still waiting on.
        "oauth_missing": missing_oauth,
        "tls_configured": present["RELAY_TLS_CERT"] and present["RELAY_TLS_KEY"],
        # The flag as set, and whether remote runs can reach a shell at all,
        # which also needs RELAY_ALLOW_EXEC.
        "remote_exec_allowed": remote_exec,
        "remote_exec_in_effect": grants.get("allow_exec") is True,
        # The grants remote_cli configures, from the process environment only:
        # exec only with remote exec too, write only with RELAY_ALLOW_WRITE.
        "start_grants": grants,
        # Grant lines in the env file are ignored; named so an operator who put
        # them there learns why the surface did not take them.
        "env_file_ignored": ignored_file_keys(path) if path else [],
        "public_url": resolved.get("RELAY_PUBLIC_URL") or None,
        "allowed_origins": _origins(resolved.get("RELAY_ALLOWED_ORIGINS", "")),
        "listen": {"host": resolved.get("RELAY_REMOTE_HOST") or None,
                   "port": resolved.get("RELAY_REMOTE_PORT") or None},
        "keys_present": present,
    }
    return state
