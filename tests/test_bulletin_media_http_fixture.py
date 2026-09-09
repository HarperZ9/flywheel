from __future__ import annotations

from pathlib import Path

import pytest

from harness.bulletin_identity_contract import BulletinIdentityError
from tests.bulletin_media_fixtures import jwk_json
from tests.bulletin_media_http_fixture import (
    actual_worker_start_commands,
    register_loopback_identity,
    validate_loopback_bulletin_base_url,
)


def test_actual_worker_bridge_accepts_only_plain_loopback_http() -> None:
    assert validate_loopback_bulletin_base_url("http://127.0.0.1:8787") == "http://127.0.0.1:8787"
    assert validate_loopback_bulletin_base_url("http://localhost:8787") == "http://localhost:8787"

    for value in (
        "https://bulletin.zaindharper.workers.dev",
        "http://example.com:8787",
        "http://user@127.0.0.1:8787",
        "http://127.0.0.1:8787/v1",
        "http://127.0.0.1:8787?x=1",
        "http://127.0.0.1:8787#frag",
        "http://127.0.0.1:8787\nhttps://example.com",
    ):
        with pytest.raises(ValueError):
            validate_loopback_bulletin_base_url(value)


def test_loopback_identity_registration_uses_bounded_pow() -> None:
    jwk, _public_jwk = jwk_json()

    def get_json(url: str, *, timeout: int) -> dict:
        if url.endswith("/v1/challenge"):
            return {"challenge": "hard", "bits": 13}
        return {"ok": False}

    with pytest.raises(BulletinIdentityError) as exc:
        register_loopback_identity(
            "http://127.0.0.1:8787",
            jwk,
            handle="flywheel-e2e",
            timeout=5,
            http_get_json=get_json,
            signed_post_json=lambda _path, _payload: {"ok": True},
        )
    assert exc.value.code == "POW_BITS_UNSUPPORTED"


def test_loopback_identity_registration_uses_synthetic_jwk_only() -> None:
    jwk, _public_jwk = jwk_json()
    calls: list[tuple[str, dict]] = []

    def get_json(url: str, *, timeout: int) -> dict:
        if url.endswith("/v1/challenge"):
            return {"challenge": "easy", "bits": 0}
        return {"ok": False}

    def signed_post_json(path: str, payload: dict) -> dict:
        calls.append((path, payload))
        return {"ok": True, "agent": {"handle": payload["handle"], "tier": "probation"}}

    registration = register_loopback_identity(
        "http://127.0.0.1:8787",
        jwk,
        handle="flywheel-e2e",
        timeout=5,
        http_get_json=get_json,
        signed_post_json=signed_post_json,
    )

    assert registration["registered"] is True
    assert calls and calls[0][0] == "/v1/agents"
    assert calls[0][1]["handle"] == "flywheel-e2e"
    assert calls[0][1]["solution"] == "0"


def test_loopback_identity_registration_has_finite_pow_attempt_cap(monkeypatch) -> None:
    import harness.bulletin_identity_network as identity_network

    jwk, _public_jwk = jwk_json()
    seen: dict[str, int | str] = {}

    def get_json(url: str, *, timeout: int) -> dict:
        if url.endswith("/v1/challenge"):
            return {"challenge": "bounded", "bits": 12}
        return {"ok": False}

    def fake_solve(challenge: str, thumbprint: str, bits: int, *, max_attempts: int) -> str:
        seen.update({
            "challenge": challenge,
            "bits": bits,
            "max_attempts": max_attempts,
        })
        return "bounded-solution"

    monkeypatch.setattr(identity_network, "solve_proof_of_work", fake_solve)
    register_loopback_identity(
        "http://127.0.0.1:8787",
        jwk,
        handle="flywheel-e2e",
        timeout=5,
        http_get_json=get_json,
        signed_post_json=lambda _path, _payload: {"ok": True},
    )

    assert seen == {
        "challenge": "bounded",
        "bits": 12,
        "max_attempts": 1 << 20,
    }


def test_actual_worker_start_commands_use_isolated_local_state(tmp_path: Path) -> None:
    commands = actual_worker_start_commands(tmp_path / "miniflare-state")
    joined = "\n".join(commands)
    assert "--local" in joined
    assert "--persist-to" in joined
    assert "--remote" not in joined
    assert "BULLETIN_POW_BITS:12" in joined
    assert "schema/0001_init.sql" in joined
    assert "schema/0005_rotation.sql" in joined
    assert "schema/0002_agents.sql" not in joined
