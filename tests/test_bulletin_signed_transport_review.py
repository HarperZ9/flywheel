from __future__ import annotations

from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import threading

import pytest

from harness.bulletin_signed_transport import (
    BULLETIN_KEY_SLOT,
    publish_authorized_preview,
)
from harness.credential_handles import CredentialBindings, CredentialHandleStore
from harness.gateway_actions import dispatch_builtin
from harness.gateway_operation import GatewayOperationError
from harness.gateway_provider_adapter import resolve_credentials
from harness.outcome_bulletin import build_preview
from tests.test_bulletin_signed_transport import (
    OWNER,
    POST_ID,
    _authorized,
    _jwk_json,
    _public_outcome,
)


class RedirectTarget:
    def __init__(self, body: dict) -> None:
        self.hits = 0
        parent = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                parent.hits += 1
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(body).encode())

            def do_POST(self):
                parent.hits += 1
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(body).encode())

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


class RedirectingBulletin:
    def __init__(self, location: str, *, redirect_on: str) -> None:
        self.posts = []
        self.gets = 0
        parent = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("content-length", "0")))
                if redirect_on == "post":
                    self.send_response(302)
                    self.send_header("location", location)
                    self.end_headers()
                    return
                payload = json.loads(raw.decode())
                parent.posts.append(payload)
                self.send_response(201)
                self.send_header("content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "post": {
                    "id": POST_ID, "room": payload["room"],
                    "content_hash": "hash"}}).encode())

            def do_GET(self):
                parent.gets += 1
                self.send_response(302)
                self.send_header("location", location)
                self.end_headers()

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


def _authorized_with_handle(
        tmp_path, token="d", *, bulletin_base_url=None, allow_loopback=False):
    jwk_value, _public_jwk = _jwk_json()
    slots = {BULLETIN_KEY_SLOT: jwk_value}
    store = CredentialHandleStore(tmp_path, keychain_get=slots.get,
                                  token_hex=lambda _size: token * 32)
    handle = store.bind(OWNER, BULLETIN_KEY_SLOT)
    preview_kwargs = {} if bulletin_base_url is None else {
        "bulletin_base_url": bulletin_base_url,
        "allow_loopback": allow_loopback,
    }
    preview = build_preview(_public_outcome(), **preview_kwargs)
    return _authorized(tmp_path, preview, handle.credential_ref), preview, jwk_value


def test_invalid_origin_is_rejected_before_keychain_resolution(tmp_path):
    authorized, preview, jwk_value = _authorized_with_handle(tmp_path)
    calls = []

    result = publish_authorized_preview(
        authorized, preview, state_root=tmp_path,
        keychain_get=lambda name: calls.append(name) or jwk_value,
        base_url="http://not-loopback.example")

    assert result["status"] == "publish_unavailable"
    assert calls == []


def test_userinfo_origin_is_rejected_before_keychain_resolution(tmp_path):
    authorized, preview, jwk_value = _authorized_with_handle(tmp_path, "e")
    calls = []

    result = publish_authorized_preview(
        authorized, preview, state_root=tmp_path,
        keychain_get=lambda name: calls.append(name) or jwk_value,
        base_url="https://user:pass@bulletin.example")

    assert result["status"] == "publish_unavailable"
    assert calls == []


def test_gateway_resolve_validates_bulletin_origin_before_keychain(tmp_path, monkeypatch):
    authorized, _preview, jwk_value = _authorized_with_handle(tmp_path, "f")
    monkeypatch.setenv("FLYWHEEL_BULLETIN_BASE_URL", "http://not-loopback.example")
    calls = []
    import harness.keychain as keychain
    monkeypatch.setattr(keychain, "keychain_get",
                        lambda name: calls.append(name) or jwk_value)

    with pytest.raises(GatewayOperationError):
        resolve_credentials(authorized, tmp_path)

    assert calls == []


def test_readback_redirect_is_not_followed(tmp_path):
    target = RedirectTarget({"ok": True, "post": {
        "id": POST_ID, "room": "findings", "body": "unused"}})
    try:
        server = RedirectingBulletin(target.url + "/matching", redirect_on="read")
        try:
            authorized, preview, jwk_value = _authorized_with_handle(
                tmp_path, "1", bulletin_base_url=server.url,
                allow_loopback=True)
            result = publish_authorized_preview(
                authorized, preview, state_root=tmp_path,
                keychain_get=lambda _name: jwk_value, base_url=server.url,
                allow_loopback=True, now=lambda: 1780000000,
                nonce_bytes=lambda n: b"\x04" * n)
        finally:
            server.close()
    finally:
        target.close()

    assert result["status"] == "posted_readback_unavailable"
    assert server.posts == [preview["post"]]
    assert target.hits == 0


def test_post_redirect_is_not_followed(tmp_path):
    target = RedirectTarget({"ok": True, "post": {
        "id": POST_ID, "room": "findings", "content_hash": "hash"}})
    try:
        server = RedirectingBulletin(target.url + "/accepted", redirect_on="post")
        try:
            authorized, preview, jwk_value = _authorized_with_handle(
                tmp_path, "2", bulletin_base_url=server.url,
                allow_loopback=True)
            result = publish_authorized_preview(
                authorized, preview, state_root=tmp_path,
                keychain_get=lambda _name: jwk_value, base_url=server.url,
                allow_loopback=True, now=lambda: 1780000000,
                nonce_bytes=lambda n: b"\x05" * n)
        finally:
            server.close()
    finally:
        target.close()

    assert result["status"] == "publish_failed"
    assert server.posts == []
    assert target.hits == 0


def test_gateway_builtin_routes_exact_bulletin_write_to_signed_transport(tmp_path, monkeypatch):
    jwk_value, public_jwk = _jwk_json()
    from tests.test_bulletin_signed_transport import BulletinServer
    server = BulletinServer(public_jwk)
    try:
        slots = {BULLETIN_KEY_SLOT: jwk_value}
        store = CredentialHandleStore(tmp_path, keychain_get=slots.get,
                                      token_hex=lambda _size: "3" * 32)
        handle = store.bind(OWNER, BULLETIN_KEY_SLOT)
        preview = build_preview(
            _public_outcome(), bulletin_base_url=server.url, allow_loopback=True)
        authorized = _authorized(tmp_path, preview, handle.credential_ref)
        authorized = replace(
            authorized,
            credential_bindings=CredentialBindings({BULLETIN_KEY_SLOT: jwk_value}))
        monkeypatch.setenv("FLYWHEEL_BULLETIN_BASE_URL", server.url)
        monkeypatch.setenv("FLYWHEEL_BULLETIN_ALLOW_LOOPBACK", "1")
        result = dispatch_builtin(authorized)
    finally:
        server.close()

    assert result[0]["status"] == "posted_readback_match"
    assert server.posts == [preview["post"]]
    assert result[1] == 200
