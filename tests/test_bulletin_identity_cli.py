from __future__ import annotations

import base64
import json

import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

BASE = "https://bulletin.zaindharper.workers.dev"


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _key_path(tmp_path):
    key = ed25519.Ed25519PrivateKey.generate()
    private = key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public = key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    public_jwk = {"kty": "OKP", "crv": "Ed25519", "x": _b64u(public)}
    path = tmp_path / "bulletin-agent.key.json"
    path.write_text(json.dumps({
        "public": public_jwk,
        "private": {**public_jwk, "d": _b64u(private)},
    }), encoding="utf-8")
    return path


def test_cli_prepare_is_read_only_by_default(tmp_path, capsys) -> None:
    from harness.bulletin_identity_cli import main

    rc = main(
        ["prepare", "--key", str(_key_path(tmp_path)),
         "--base", BASE],
        http_get_json=lambda _url, timeout=20: {"ok": False},
        credential_source=lambda _name: "absent",
    )

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["schema"] == "flywheel.bulletin-identity-prepare/v1"
    assert out["registration"]["action"] == "not_requested"
    dumped = json.dumps(out, sort_keys=True)
    assert "private" not in dumped
    assert '"d"' not in dumped


def test_cli_error_is_typed_and_does_not_echo_path(tmp_path, capsys) -> None:
    from harness.bulletin_identity_cli import main

    bad_path = tmp_path / "bad-secret-file-name.key.json"
    bad_path.write_text('{"bad": true}', encoding="utf-8")

    rc = main(["prepare", "--key", str(bad_path), "--base", BASE])

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.err == ""
    body = json.loads(captured.out)
    assert body["error"]["code"] == "KEY_FILE_INVALID"
    assert "bad-secret-file-name" not in captured.out


def test_cli_entry_packages_bulletin_identity() -> None:
    from harness.cli_entry import _PACKAGED

    assert _PACKAGED["bulletin-identity"] == "harness.bulletin_identity_cli"


def test_cli_lock_busy_returns_fixed_json(tmp_path, capsys) -> None:
    from harness.bulletin_identity_cli import main
    from harness.journey_lock import JourneyLockBusy

    class BusyLock:
        def __enter__(self):
            raise JourneyLockBusy()

        def __exit__(self, _exc_type, _exc, _tb):
            return False

    rc = main(
        ["prepare", "--key", str(_key_path(tmp_path)), "--base", BASE,
         "--store-keychain"],
        http_get_json=lambda _url, timeout=20: {"ok": False},
        credential_source=lambda _name: "absent",
        keychain_get=lambda _name: None,
        keychain_set=lambda name, _value: {"stored": name},
        keychain_lock=lambda _name: BusyLock(),
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.err == ""
    body = json.loads(captured.out)
    assert body["error"]["code"] == "STORE_BUSY"
