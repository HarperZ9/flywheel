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
    "for label, path in (('TOKEN', sys.argv[1]), ('CONTROL', sys.argv[2])):\n"
    "    try:\n"
    "        with open(path, 'rb') as fh:\n"
    "            fh.read(0)\n"
    "        print(label + '_OPENED')\n"
    "    except OSError as exc:\n"
    "        print(label + '_DENIED', type(exc).__name__)\n"
)


def _sandboxed_open(tmp_path, secret, control):
    """Open ``secret`` and an unlabeled ``control`` sibling from the sandbox.

    The control must open: it shows the sandboxed child can see the directory,
    so a denial of the secret comes from the label and not from a wrong path."""
    from harness.sandboxed_runner import SandboxUnavailable, sandboxed_run
    child = tmp_path / "open_secret.py"
    child.write_text(_CHILD, encoding="utf-8")
    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)
    cmd = (f"{Path(sys.executable).as_posix()} {child.as_posix()} "
           f"{Path(secret).as_posix()} {Path(control).as_posix()}")
    try:
        ok, out = sandboxed_run(cmd, str(workspace), timeout_seconds=60)
    except SandboxUnavailable as exc:
        pytest.skip(f"no Windows sandbox on this host: {exc}")
    assert ok, out
    return out


def _assert_denied_by_label(out):
    assert "CONTROL_OPENED" in out, out
    assert "TOKEN_DENIED PermissionError" in out, out
    assert "TOKEN_OPENED" not in out


def test_posix_sandbox_denylist_hides_the_gateway_token():
    hidden = dict((path, kind) for kind, path in default_paths("/home/op"))
    assert hidden.get("/home/op/.flywheel/gateway.token") == "file"


def test_posix_denylist_follows_a_custom_flywheel_home():
    from harness.sandbox_protected_paths import host_protected_paths
    hidden = dict((path, kind) for kind, path in host_protected_paths(
        "/home/op", {"FLYWHEEL_HOME": "/srv/flywheel"}, exists=lambda path: True))
    assert hidden.get("/srv/flywheel/gateway.token") == "file"
    assert hidden.get("/srv/flywheel/keys") == "dir"
    assert hidden.get("/home/op/.flywheel/gateway.token") == "file"


def test_posix_run_hides_the_token_under_flywheel_home(tmp_path, monkeypatch):
    import harness.posix_sandbox as ps
    home = tmp_path / "custom-home"
    home.mkdir()
    (home / "gateway.token").write_bytes(b"")
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    seen = []
    monkeypatch.setattr(ps, "build", lambda *a, protected, **k: seen.append(protected) or ["true"])
    monkeypatch.setattr(ps, "describe", lambda *a, **k: None)
    ps.posix_run("true", str(tmp_path), str(tmp_path), env={}, platform="linux",
                 which=lambda name: "/usr/bin/bwrap", probe=lambda *a: True,
                 runner=lambda *a: (0, ""))
    (hidden,) = seen
    token = home.resolve() / "gateway.token"
    assert ("file", token.as_posix()) in hidden


@pytest.mark.skipif(os.name != "nt", reason="Windows low-integrity sandbox only")
def test_windows_sandboxed_command_cannot_open_gateway_token(tmp_path):
    home = tmp_path / "flywheel-home"
    load_or_create_token(home)
    control = home / "control.txt"
    control.write_bytes(b"not secret")
    out = _sandboxed_open(tmp_path, home / TOKEN_FILENAME, control)
    _assert_denied_by_label(out)


@pytest.mark.skipif(os.name != "nt", reason="Windows low-integrity sandbox only")
def test_windows_sandboxed_command_cannot_open_the_receipt_signing_key(tmp_path):
    from harness.receipt_signer import _lock_down
    keys = tmp_path / "keys"
    keys.mkdir()
    key = keys / "receipt-signing-ed25519"
    key.write_bytes(b"dummy key material, not a real key")
    _lock_down(key)
    control = keys / "control.txt"
    control.write_bytes(b"not secret")
    _assert_denied_by_label(_sandboxed_open(tmp_path, key, control))


@pytest.mark.skipif(os.name != "nt", reason="Windows low-integrity sandbox only")
def test_loading_an_existing_signing_key_labels_it(tmp_path):
    from harness.receipt_signer import SigningKeyError, load_signing_key
    keys = tmp_path / "keys"
    keys.mkdir()
    key = keys / "receipt-signing-ed25519"
    key.write_bytes(b"minted before the label existed, not a real key")
    with pytest.raises(SigningKeyError):
        load_signing_key(key)
    control = keys / "control.txt"
    control.write_bytes(b"not secret")
    _assert_denied_by_label(_sandboxed_open(tmp_path, key, control))


def test_token_stays_readable_by_its_owner(tmp_path):
    first = load_or_create_token(tmp_path)
    assert load_or_create_token(tmp_path) == first
    with open(tmp_path / TOKEN_FILENAME, "rb") as fh:
        assert len(fh.read()) > 0
