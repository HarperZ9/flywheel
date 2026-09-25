"""A sandboxed agent command cannot open the gateway bearer token.

The token authorizes every gateway route, including approving an exec grant.
The Windows sandbox runs commands at low integrity with the default No-Write-Up
policy, which leaves medium-integrity files readable, so a sandboxed command
could open ~/.flywheel/gateway.token. The POSIX backends do not confine reads
either and hide only a named credential denylist. These tests check the token
file is unreadable from inside the sandbox. They open it and read zero bytes;
no test reads or prints a token value.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from harness.gateway_auth import TOKEN_FILENAME, load_or_create_token
from harness.sandbox_protected_paths import default_paths

_CHILD = (
    "import sys\n"
    "try:\n"
    "    with open(sys.argv[1], 'rb') as fh:\n"
    "        fh.read(0)\n"
    "    print('TOKEN_OPENED')\n"
    "except OSError as exc:\n"
    "    print('TOKEN_DENIED', type(exc).__name__)\n"
)


def test_posix_sandbox_denylist_hides_the_gateway_token():
    hidden = dict((path, kind) for kind, path in default_paths("/home/op"))
    assert hidden.get("/home/op/.flywheel/gateway.token") == "file"


@pytest.mark.skipif(os.name != "nt", reason="Windows low-integrity sandbox only")
def test_windows_sandboxed_command_cannot_open_gateway_token(tmp_path):
    from harness.sandboxed_runner import SandboxUnavailable, sandboxed_run
    home = tmp_path / "flywheel-home"
    load_or_create_token(home)
    token = home / TOKEN_FILENAME
    child = tmp_path / "open_token.py"
    child.write_text(_CHILD, encoding="utf-8")
    workspace = tmp_path / "ws"
    workspace.mkdir()
    cmd = f"{Path(sys.executable).as_posix()} {child.as_posix()} {token.as_posix()}"
    try:
        ok, out = sandboxed_run(cmd, str(workspace), timeout_seconds=60)
    except SandboxUnavailable as exc:
        pytest.skip(f"no Windows sandbox on this host: {exc}")
    assert ok, out
    assert "TOKEN_DENIED" in out
    assert "TOKEN_OPENED" not in out


def test_token_stays_readable_by_its_owner(tmp_path):
    first = load_or_create_token(tmp_path)
    assert load_or_create_token(tmp_path) == first
    with open(tmp_path / TOKEN_FILENAME, "rb") as fh:
        assert len(fh.read()) > 0
