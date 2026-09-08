from __future__ import annotations

import base64
from contextlib import nullcontext
import json

import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

BASE = "https://bulletin.zaindharper.workers.dev"


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
    private_jwk = {**public_jwk, "d": _b64u(private)}
    return json.dumps({"public": public_jwk, "private": private_jwk})


def _write_key(tmp_path) -> object:
    path = tmp_path / "bulletin-agent.key.json"
    path.write_text(_jwk_json(), encoding="utf-8")
    return path


def test_identity_summary_never_contains_jwk_material(tmp_path) -> None:
    from harness.bulletin_identity import load_identity_file

    identity = load_identity_file(_write_key(tmp_path))
    summary = identity.public_summary(handle="flywheel")
    dumped = json.dumps(summary, sort_keys=True)

    assert summary["credential_name"] == "BULLETIN_AGENT_JWK"
    assert summary["handle"] == "flywheel"
    assert summary["thumbprint"]
    assert "public_jwk" not in dumped
    assert "private" not in dumped
    assert '"d"' not in dumped
    assert '"x"' not in dumped


def test_prepare_reuses_existing_registration_without_posting(tmp_path) -> None:
    from harness.bulletin_identity import prepare_identity

    key_path = _write_key(tmp_path)
    posts: list[dict] = []

    def get_json(url: str, *, timeout: int = 20) -> dict:
        assert "/v1/agents/" in url
        return {"ok": True, "agent": {"handle": "flywheel", "tier": "probation"}}

    result = prepare_identity(
        key_path,
        base_url=BASE,
        handle="flywheel",
        http_get_json=get_json,
        signed_post_json=lambda _path, payload: posts.append(payload) or {"ok": True},
        credential_source=lambda _name: "absent",
    )

    assert result["board"]["registered"] is True
    assert result["registration"]["action"] == "not_requested"
    assert posts == []


def test_explicit_register_posts_public_jwk_only_when_absent(tmp_path) -> None:
    from harness.bulletin_identity import BulletinIdentityHttpError, prepare_identity

    key_path = _write_key(tmp_path)
    payloads: list[dict] = []

    def get_json(url: str, *, timeout: int = 20) -> dict:
        if url.endswith("/v1/challenge"):
            return {"ok": True, "challenge": "challenge-1", "bits": 0}
        raise BulletinIdentityHttpError(404)

    def post_json(path: str, payload: dict) -> dict:
        payloads.append(payload)
        return {
            "ok": True,
            "agent": {"handle": payload["handle"], "tier": "probation"},
        }

    result = prepare_identity(
        key_path,
        base_url=BASE,
        handle="flywheel",
        register=True,
        http_get_json=get_json,
        signed_post_json=post_json,
        credential_source=lambda _name: "absent",
    )

    assert result["registration"]["action"] == "registered"
    assert len(payloads) == 1
    assert payloads[0]["handle"] == "flywheel"
    assert "d" not in payloads[0]["public_jwk"]
    assert set(payloads[0]["public_jwk"]) == {"kty", "crv", "x"}


def test_store_keychain_refuses_existing_invalid_value(tmp_path) -> None:
    from harness.bulletin_identity import BulletinIdentityError, prepare_identity

    with pytest.raises(BulletinIdentityError) as excinfo:
        prepare_identity(
            _write_key(tmp_path),
            base_url=BASE,
            handle="flywheel",
            store_keychain=True,
            http_get_json=lambda _url, timeout=20: {"ok": False},
            credential_source=lambda _name: "keychain",
            keychain_get=lambda _name: '{"not":"a bulletin key"}',
            keychain_set=lambda _name, _value: {"stored": _name},
        )

    assert excinfo.value.code == "KEYCHAIN_VALUE_INVALID"


def test_store_keychain_returns_presence_without_secret_value(tmp_path) -> None:
    from harness.bulletin_identity import BULLETIN_CREDENTIAL_NAME, prepare_identity

    captured: dict[str, str] = {}
    store: dict[str, str] = {}

    def keychain_set(name: str, value: str) -> dict:
        captured["name"] = name
        captured["value"] = value
        store[name] = value
        return {"stored": name}

    result = prepare_identity(
        _write_key(tmp_path),
        base_url=BASE,
        handle="flywheel",
        store_keychain=True,
        http_get_json=lambda _url, timeout=20: {"ok": False},
        credential_source=lambda name: "keychain" if name in store else "absent",
        keychain_get=store.get,
        keychain_set=keychain_set,
        keychain_lock=lambda _name: nullcontext(),
    )

    dumped = json.dumps(result, sort_keys=True)
    assert captured["name"] == BULLETIN_CREDENTIAL_NAME
    assert result["keychain"]["action"] == "stored"
    assert "private" not in dumped
    assert '"d"' not in dumped
    assert captured["value"] not in dumped


def test_store_keychain_rechecks_slot_before_writing(tmp_path) -> None:
    from harness.bulletin_identity import BulletinIdentityError, prepare_identity

    calls: list[str] = []

    def keychain_set(name: str, value: str) -> dict:
        calls.append("set")
        return {"stored": name}

    with pytest.raises(BulletinIdentityError) as excinfo:
        prepare_identity(
            _write_key(tmp_path),
            base_url=BASE,
            handle="flywheel",
            store_keychain=True,
            http_get_json=lambda _url, timeout=20: {"ok": False},
            credential_source=lambda _name: "absent",
            keychain_get=lambda _name: '{"not":"a bulletin key"}',
            keychain_set=keychain_set,
            keychain_lock=lambda _name: nullcontext(),
        )

    assert excinfo.value.code == "KEYCHAIN_VALUE_INVALID"
    assert calls == []
