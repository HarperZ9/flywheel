from __future__ import annotations

import base64
import hashlib
import json
import re

import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric import ed25519

from harness.bulletin_identity_key import generate_identity_json, parse_identity_json
from harness.bulletin_identity_network import agent_status, register_or_reuse
from harness.bulletin_signed_transport import (
    _SignedClient,
    _parse_key,
    _read_json,
)

BASE = "https://bulletin.zaindharper.workers.dev"
EXPECTED_UA = "Flywheel-native-client/1 (+https://github.com/HarperZ9/flywheel)"


class JsonResponse:
    def __init__(self, body: dict) -> None:
        self.body = json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return False

    def read(self, _limit: int) -> bytes:
        return self.body


class CapturingOpener:
    def __init__(self, bodies: list[dict]) -> None:
        self.bodies = list(bodies)
        self.requests = []
        self.timeouts = []

    def open(self, request, *, timeout: int):
        self.requests.append(request)
        self.timeouts.append(timeout)
        return JsonResponse(self.bodies.pop(0))


def test_identity_status_and_challenge_gets_use_flywheel_user_agent(monkeypatch) -> None:
    from harness import bulletin_identity_network as network

    opener = CapturingOpener([
        {"ok": False},
        {"ok": True, "challenge": "challenge-1", "bits": 0},
    ])
    monkeypatch.setattr(network, "_NO_REDIRECT", opener)
    identity = parse_identity_json(generate_identity_json())
    posts = []

    status = agent_status(BASE, "thumbprint-1", http_get_json=None, timeout=7)
    registered = register_or_reuse(
        identity,
        BASE,
        "flywheel",
        known_status=status,
        http_get_json=None,
        signed_post_json=lambda path, payload: posts.append((path, payload))
        or {"ok": True, "agent": {"handle": "flywheel", "tier": "probation"}},
        timeout=7,
    )

    assert status == {"registered": False}
    assert registered["action"] == "registered"
    assert [request.get_method() for request in opener.requests] == ["GET", "GET"]
    assert [request.full_url for request in opener.requests] == [
        f"{BASE}/v1/agents/thumbprint-1",
        f"{BASE}/v1/challenge",
    ]
    assert [_header(request, "user-agent") for request in opener.requests] == [
        EXPECTED_UA,
        EXPECTED_UA,
    ]
    assert posts and posts[0][0] == "/v1/agents"


def test_signed_post_and_readback_get_use_user_agent_without_signature_drift(monkeypatch) -> None:
    from harness import bulletin_signed_transport as transport

    opener = CapturingOpener([
        {"ok": True, "post": {"id": "post-1", "room": "findings",
                              "content_hash": "hash"}},
        {"ok": True, "post": {"id": "post-1", "room": "findings",
                              "body": "body"}},
    ])
    monkeypatch.setattr(transport, "_NO_REDIRECT", opener)
    key = _parse_key(generate_identity_json())
    payload = {"room": "findings", "body": "body"}

    posted = _SignedClient(
        BASE, key, timeout=9, now=lambda: 1780000000,
        nonce_bytes=lambda n: b"\x06" * n).post_json("/v1/posts", payload)
    seen = _read_json(f"{BASE}/v1/posts/post-1", 9)

    assert posted["ok"] is True and seen["ok"] is True
    assert [request.get_method() for request in opener.requests] == ["POST", "GET"]
    assert [_header(request, "user-agent") for request in opener.requests] == [
        EXPECTED_UA,
        EXPECTED_UA,
    ]
    _verify_signed_request(opener.requests[0], payload, key)


def _verify_signed_request(request, payload: dict, key: dict) -> None:
    body = request.data
    assert json.loads(body.decode()) == payload
    digest = _header(request, "content-digest")
    expected_digest = "sha-256=:" + base64.b64encode(
        hashlib.sha256(body).digest()).decode() + ":"
    assert digest == expected_digest
    params = _header(request, "signature-input").removeprefix("sig1=")
    assert params.startswith('("@method" "@authority" "@path" "content-digest")')
    assert "user-agent" not in params.lower()
    signature = re.fullmatch(
        r"sig1=:([A-Za-z0-9+/=]+):", _header(request, "signature")).group(1)
    base = "\n".join([
        '"@method": POST',
        '"@authority": bulletin.zaindharper.workers.dev',
        '"@path": /v1/posts',
        f'"content-digest": {digest}',
        f'"@signature-params": {params}',
    ])
    public = key["key"].public_key()
    assert isinstance(public, ed25519.Ed25519PublicKey)
    public.verify(base64.b64decode(signature), base.encode())


def _header(request, name: str) -> str | None:
    for key, value in request.header_items():
        if key.lower() == name:
            return value
    return None
