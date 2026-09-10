from __future__ import annotations

import base64
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import re
import socket
import threading

import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from harness.bulletin_signed_transport import (
    BULLETIN_KEY_SLOT,
    _thumbprint,
    publish_authorized_preview,
)
from harness.credential_handles import CredentialHandleStore
from harness.gateway_grant_route import authorize_gateway_operation, gateway_grant_post
from harness.gateway_operation import AuthorizedOperation
from harness.journey_store import JourneyStore, MutationCommand
from harness.outcome_bulletin import (
    build_gateway_grant_request,
    build_gateway_publish_envelope,
    build_preview,
)

OWNER = "owner_" + "a" * 32
JOURNEY = "jrn_" + "a" * 32
NOW = "2026-08-15T12:00:00Z"
POST_ID = "01K4MTESTSIGNEDPOST0000000000"


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64ud(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _jwk_json() -> tuple[str, dict]:
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
    return json.dumps({"public": public_jwk, "private": private_jwk}), public_jwk


def _public_outcome() -> dict:
    return {
        "schema": "flywheel.outcome-bulletin-request/v1",
        "title": "Index reliability checkpoint",
        "status": "Index durable router work reached local review gates.",
        "room": "findings",
        "checked": ["router job tests passed against the local worktree"],
        "positive_controls": ["timeout and resume controls were exercised"],
        "held_blockers": ["publication waits for integration review"],
        "next_actions": ["publish reviewed release references after approval"],
        "does_not_prove": ["production Bulletin posting has happened"],
        "links": [{"label": "Index release", "url": "https://github.com/HarperZ9/index/releases/tag/v2.11.0"}],
    }


def _journey(root):
    return JourneyStore(root).create(MutationCommand(
        OWNER, JOURNEY, None, "create-1", "intake",
        {"legacy_label": None, "goal": "publish public outcome", "intake": {},
         "occurred_at": NOW}))


def _approve(root, proposal):
    return gateway_grant_post(
        "/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": proposal["proposal_ref"]}).encode(),
        owner_ref=OWNER, state_root=root, clock=lambda: NOW)


def _authorized(root, preview, credential_ref):
    head = _journey(root).event_head_sha256
    request = build_gateway_grant_request(
        preview, journey_ref=JOURNEY, expected_event_head=head,
        client_request_id="request-1", credential_ref=credential_ref)
    proposal, status = gateway_grant_post(
        "/api/gateway-grants/prepare/lane.call",
        json.dumps(request).encode(), owner_ref=OWNER, state_root=root,
        clock=lambda: NOW)
    assert status == 200, proposal
    approval, status = _approve(root, proposal)
    assert status == 200, approval
    envelope = build_gateway_publish_envelope(
        preview, journey_ref=JOURNEY, expected_event_head=head,
        client_request_id="request-1", grant_ref=approval["grant_ref"],
        credential_ref=credential_ref)
    return authorize_gateway_operation(
        "lane.call", json.dumps(envelope, separators=(",", ":")).encode(),
        owner_ref=OWNER, state_root=root, clock=lambda: NOW)


class BulletinServer:
    def __init__(self, public_jwk: dict, *, mode: str = "ok") -> None:
        self.public_jwk = public_jwk
        self.mode = mode
        self.posts = []
        self.gets = 0
        parent = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                length = int(self.headers.get("content-length", "0"))
                raw = self.rfile.read(length)
                parent._verify(self, raw)
                payload = json.loads(raw.decode())
                parent.posts.append(payload)
                if parent.mode == "drop":
                    self.close_connection = True
                    try:
                        self.connection.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    self.connection.close()
                    return
                self.send_response(201)
                self.send_header("content-type", "application/json")
                self.end_headers()
                body = {"ok": True, "post": {"id": POST_ID,
                        "room": payload["room"], "content_hash": "hash"}}
                self.wfile.write(json.dumps(body).encode())

            def do_GET(self):
                parent.gets += 1
                assert self.path == f"/v1/posts/{POST_ID}"
                post = parent.posts[0]
                body = "changed" if parent.mode == "drift" else post["body"]
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "post": {
                    "id": POST_ID, "room": post["room"], "body": body,
                    "parent_id": post.get("parent_id"),
                    "author": (None if parent.mode == "missing_author" else
                               "wrong" if parent.mode == "wrong_author" else
                               _thumbprint(parent.public_jwk))}}).encode())

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def close(self) -> None:
        self.server.shutdown()
        self.thread.join(2)
        self.server.server_close()

    def _verify(self, handler, raw: bytes) -> None:
        assert handler.path == "/v1/posts"
        digest = handler.headers["content-digest"]
        expected = "sha-256=:" + base64.b64encode(hashlib.sha256(raw).digest()).decode() + ":"
        assert digest == expected
        params = handler.headers["signature-input"].removeprefix("sig1=")
        signature = re.fullmatch(r"sig1=:([A-Za-z0-9+/=]+):", handler.headers["signature"]).group(1)
        keyid = re.search(r';keyid="([^"]+)"', params).group(1)
        nonce = re.search(r';nonce="([^"]+)"', params).group(1)
        assert keyid and nonce
        base = "\n".join([
            '"@method": POST',
            f'"@authority": {handler.headers["host"].lower()}',
            '"@path": /v1/posts',
            f'"content-digest": {digest}',
            f'"@signature-params": {params}',
        ])
        public = ed25519.Ed25519PublicKey.from_public_bytes(
            _b64ud(self.public_jwk["x"]))
        public.verify(base64.b64decode(signature), base.encode())


def test_gateway_grant_with_bulletin_credential_publishes_and_reads_back(tmp_path):
    jwk_value, public_jwk = _jwk_json()
    slots = {BULLETIN_KEY_SLOT: jwk_value}
    store = CredentialHandleStore(tmp_path, keychain_get=slots.get,
                                  token_hex=lambda _size: "a" * 32)
    handle = store.bind(OWNER, BULLETIN_KEY_SLOT)
    preview = build_preview(_public_outcome())
    authorized = _authorized(tmp_path, preview, handle.credential_ref)
    server = BulletinServer(public_jwk)
    try:
        result = publish_authorized_preview(
            authorized, preview, state_root=tmp_path, keychain_get=slots.get,
            base_url=server.url, allow_loopback=True,
            now=lambda: 1780000000, nonce_bytes=lambda n: b"\x01" * n)
    finally:
        server.close()
    assert result["status"] == "posted_readback_match"
    assert result["post_id"] == POST_ID
    assert len(server.posts) == 1 and server.gets == 1


def test_readback_drift_is_typed_after_signed_write(tmp_path):
    jwk_value, public_jwk = _jwk_json()
    slots = {BULLETIN_KEY_SLOT: jwk_value}
    store = CredentialHandleStore(tmp_path, keychain_get=slots.get,
                                  token_hex=lambda _size: "b" * 32)
    handle = store.bind(OWNER, BULLETIN_KEY_SLOT)
    preview = build_preview(_public_outcome())
    authorized = _authorized(tmp_path, preview, handle.credential_ref)
    server = BulletinServer(public_jwk, mode="drift")
    try:
        result = publish_authorized_preview(
            authorized, preview, state_root=tmp_path, keychain_get=slots.get,
            base_url=server.url, allow_loopback=True,
            now=lambda: 1780000000, nonce_bytes=lambda n: b"\x02" * n)
    finally:
        server.close()
    assert result["status"] == "posted_readback_drift"
    assert result["post_id"] == POST_ID and len(server.posts) == 1


def test_lost_post_response_does_not_retry_or_claim_publication(tmp_path):
    jwk_value, public_jwk = _jwk_json()
    slots = {BULLETIN_KEY_SLOT: jwk_value}
    store = CredentialHandleStore(tmp_path, keychain_get=slots.get,
                                  token_hex=lambda _size: "c" * 32)
    handle = store.bind(OWNER, BULLETIN_KEY_SLOT)
    preview = build_preview(_public_outcome())
    authorized = _authorized(tmp_path, preview, handle.credential_ref)
    server = BulletinServer(public_jwk, mode="drop")
    try:
        result = publish_authorized_preview(
            authorized, preview, state_root=tmp_path, keychain_get=slots.get,
            base_url=server.url, allow_loopback=True,
            now=lambda: 1780000000, nonce_bytes=lambda n: b"\x03" * n)
    finally:
        server.close()
    assert result["status"] == "post_write_unverified"
    assert len(server.posts) == 1 and server.gets == 0


def test_unconfigured_transport_is_typed_and_does_not_resolve_secret(tmp_path):
    preview = build_preview(_public_outcome())
    operation = {"name": "bulletin", "tool": "board_write_post",
                 "args": preview["post"], "governance_tier": "T2",
                 "timeout": 20, "data_refs": [], "credential_refs": []}
    authorized = AuthorizedOperation.for_test(
        action="lane.call", operation=operation,
        scopes=("exec", "network", "plugin"))
    result = publish_authorized_preview(
        authorized, preview, state_root=tmp_path,
        keychain_get=lambda _name: pytest.fail("secret was requested"))
    assert result["status"] == "publish_unavailable"


def test_grant_binding_mismatch_fails_before_secret_resolution(tmp_path):
    preview = build_preview(_public_outcome())
    operation = {"name": "bulletin", "tool": "board_write_post",
                 "args": {"room": "findings", "body": "different"},
                 "governance_tier": "T2", "timeout": 20, "data_refs": [],
                 "credential_refs": ["cred_" + "a" * 32]}
    authorized = AuthorizedOperation.for_test(
        action="lane.call", operation=operation,
        scopes=("exec", "network", "plugin", "secrets"))
    result = publish_authorized_preview(
        authorized, preview, state_root=tmp_path,
        keychain_get=lambda _name: pytest.fail("secret was requested"),
        base_url="https://bulletin.example")
    assert result["status"] == "grant_binding_mismatch"
