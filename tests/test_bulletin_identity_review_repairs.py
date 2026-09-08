from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

BASE = "https://bulletin.zaindharper.workers.dev"
OWNER = "owner_" + "a" * 32


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _jwk_json() -> str:
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
    return json.dumps({"public": public_jwk,
                       "private": {**public_jwk, "d": _b64u(private)}})


def _write_key(tmp_path, raw: str | None = None):
    path = tmp_path / "bulletin-agent.key.json"
    path.write_text(raw or _jwk_json(), encoding="utf-8")
    return path


def _absent_status(_url: str, *, timeout: int = 20) -> dict:
    return {"ok": False}


def test_prepare_without_key_reuses_native_keychain_identity(tmp_path) -> None:
    from harness.bulletin_identity import BULLETIN_CREDENTIAL_NAME, prepare_identity

    raw = _jwk_json()
    result = prepare_identity(
        None,
        base_url=BASE,
        http_get_json=_absent_status,
        credential_source=lambda name: "keychain" if name == BULLETIN_CREDENTIAL_NAME else "absent",
        keychain_get=lambda name: raw if name == BULLETIN_CREDENTIAL_NAME else None,
    )

    assert result["keychain"]["action"] == "reused"
    assert result["thumbprint"]


def test_prepare_without_key_reports_missing_native_identity() -> None:
    from harness.bulletin_identity import BulletinIdentityError, prepare_identity

    with pytest.raises(BulletinIdentityError) as excinfo:
        prepare_identity(
            None,
            base_url=BASE,
            http_get_json=_absent_status,
            credential_source=lambda _name: "absent",
            keychain_get=lambda _name: None,
        )

    assert excinfo.value.code == "NATIVE_IDENTITY_MISSING"


def test_create_store_generates_directly_into_keychain_without_plaintext_file() -> None:
    from harness.bulletin_identity import BULLETIN_CREDENTIAL_NAME, prepare_identity

    store: dict[str, str] = {}
    generated: list[bool] = []

    def generate() -> str:
        generated.append(True)
        return _jwk_json()

    result = prepare_identity(
        None,
        create=True,
        store_keychain=True,
        base_url=BASE,
        http_get_json=_absent_status,
        credential_source=lambda name: "keychain" if name in store else "absent",
        keychain_get=store.get,
        keychain_set=lambda name, value: store.setdefault(name, value) and {"stored": name},
        generate_key_json=generate,
        keychain_lock_root=Path("unused-by-fake-lock"),
        keychain_lock=lambda _name: _NullLock(),
    )

    assert generated == [True]
    assert BULLETIN_CREDENTIAL_NAME in store
    assert result["keychain"]["action"] == "created_stored"
    assert store[BULLETIN_CREDENTIAL_NAME] not in json.dumps(result, sort_keys=True)


def test_binding_refuses_keychain_thumbprint_mismatch(tmp_path) -> None:
    from harness.bulletin_identity import BulletinIdentityError, prepare_identity

    stored_other = _jwk_json()

    with pytest.raises(BulletinIdentityError) as excinfo:
        prepare_identity(
            _write_key(tmp_path),
            base_url=BASE,
            bind_owner=OWNER,
            state_root=tmp_path,
            http_get_json=_absent_status,
            credential_source=lambda _name: "keychain",
            keychain_get=lambda _name: stored_other,
        )

    assert excinfo.value.code == "KEYCHAIN_VALUE_MISMATCH"


def test_store_and_bind_verify_actual_stored_thumbprint(tmp_path) -> None:
    from harness.bulletin_identity import BulletinIdentityError, prepare_identity

    stored_other = _jwk_json()
    store: dict[str, str] = {}

    def set_different(name: str, _value: str) -> dict:
        store[name] = stored_other
        return {"stored": name}

    with pytest.raises(BulletinIdentityError) as excinfo:
        prepare_identity(
            _write_key(tmp_path),
            base_url=BASE,
            store_keychain=True,
            bind_owner=OWNER,
            state_root=tmp_path,
            http_get_json=_absent_status,
            credential_source=lambda name: "keychain" if name in store else "absent",
            keychain_get=store.get,
            keychain_set=set_different,
            keychain_lock=lambda _name: _NullLock(),
        )

    assert excinfo.value.code == "KEYCHAIN_VALUE_MISMATCH"


def test_key_file_read_is_bounded_before_allocation(tmp_path, monkeypatch) -> None:
    from harness.bulletin_identity import BulletinIdentityError, MAX_KEY_BYTES, load_identity_file

    path = tmp_path / "oversized.key.json"
    path.write_bytes(b"{" + (b" " * MAX_KEY_BYTES) + b"}")

    def unbounded_read(_self):
        raise AssertionError("read_bytes would allocate the whole file")

    monkeypatch.setattr(Path, "read_bytes", unbounded_read)

    with pytest.raises(BulletinIdentityError) as excinfo:
        load_identity_file(path)

    assert excinfo.value.code == "KEY_FILE_TOO_LARGE"


def test_private_origin_is_rejected_before_key_file_read(tmp_path, monkeypatch) -> None:
    from harness.bulletin_identity import BulletinIdentityError, prepare_identity

    path = _write_key(tmp_path)

    def unbounded_read(_self):
        raise AssertionError("base URL should be rejected before key load")

    monkeypatch.setattr(Path, "read_bytes", unbounded_read)

    with pytest.raises(BulletinIdentityError) as excinfo:
        prepare_identity(path, base_url="https://169.254.169.254",
                         http_get_json=_absent_status)

    assert excinfo.value.code == "BASE_URL_UNAVAILABLE"


def test_arbitrary_https_origin_is_rejected_by_default(tmp_path) -> None:
    from harness.bulletin_identity import BulletinIdentityError, prepare_identity

    with pytest.raises(BulletinIdentityError) as excinfo:
        prepare_identity(_write_key(tmp_path), base_url="https://bulletin.example",
                         http_get_json=_absent_status)

    assert excinfo.value.code == "BASE_URL_UNAVAILABLE"


def test_registration_transport_error_becomes_fixed_identity_error(tmp_path) -> None:
    from harness.bulletin_identity import (
        BulletinIdentityError,
        BulletinIdentityHttpError,
        prepare_identity,
    )
    from harness.bulletin_signed_transport import BulletinSignedTransportError

    def get_json(url: str, *, timeout: int = 20) -> dict:
        if url.endswith("/v1/challenge"):
            return {"ok": True, "challenge": "challenge-1", "bits": 0}
        raise BulletinIdentityHttpError(404)

    def post_json(_path: str, _payload: dict) -> dict:
        raise BulletinSignedTransportError("WRITE_RESPONSE_LOST")

    with pytest.raises(BulletinIdentityError) as excinfo:
        prepare_identity(
            _write_key(tmp_path),
            base_url=BASE,
            register=True,
            http_get_json=get_json,
            signed_post_json=post_json,
            credential_source=lambda _name: "absent",
        )

    assert excinfo.value.code == "REGISTRATION_UNAVAILABLE"


def test_keychain_lock_uses_configured_flywheel_home(tmp_path, monkeypatch) -> None:
    from harness.bulletin_identity import BULLETIN_CREDENTIAL_NAME, load_identity_file
    from harness.bulletin_identity_store import store_identity_in_keychain

    home = tmp_path / "home"
    store: dict[str, str] = {}
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))

    def keychain_set(name: str, value: str) -> dict:
        store[name] = value
        return {"stored": name}

    store_identity_in_keychain(
        load_identity_file(_write_key(tmp_path)),
        credential_source=lambda name: "keychain" if name in store else "absent",
        keychain_get=store.get,
        keychain_set=keychain_set,
    )

    assert (home / "state" / "credential-locks" / f"{BULLETIN_CREDENTIAL_NAME}.lock").exists()


class _NullLock:
    def __enter__(self):
        return None

    def __exit__(self, _exc_type, _exc, _tb):
        return False
