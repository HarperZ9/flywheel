"""Loopback Bulletin board used by the frozen gateway smoke."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

POST_ID = "01KFROZENGATEWAYSMOKE0000"


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


class LoopbackMediaBoard:
    def __init__(self, public_jwk: dict[str, str]) -> None:
        self.public_jwk, self.preview = public_jwk, None
        self.uploads: list[bytes] = []
        self.posts: list[dict] = []
        self.signed_requests = 0
        parent = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass
            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("content-length", "0")))
                if self.path == "/v1/media":
                    parent._verify(self, raw); parent._media(self, raw); return
                if self.path == "/v1/posts":
                    parent._verify(self, raw); parent._post(self, raw); return
                self.json_response(404, {"ok": False, "error": "unknown path"})
            def do_GET(self):
                if self.path == f"/v1/posts/{POST_ID}":
                    parent._post_readback(self); return
                if self.path.startswith("/v1/media/"):
                    parent._media_readback(self); return
                self.json_response(404, {"ok": False, "error": "unknown path"})
            def json_response(self, code, payload):
                body = json.dumps(payload).encode()
                self.send_response(code); self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body))); self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def close(self) -> None:
        self.server.shutdown(); self.thread.join(2); self.server.server_close()

    def _media(self, handler, raw: bytes) -> None:
        self.uploads.append(raw)
        row = self.preview["media"][len(self.uploads) - 1]
        handler.json_response(201, {"ok": True, "media": {
            "id": row["expected_media_id"], "media_type": row["media_type"],
            "kind": row["kind"], "bytes": len(raw),
            "url": "/v1/media/" + row["expected_media_id"],
            "width": None, "height": None, "deduplicated": False}})

    def _post(self, handler, raw: bytes) -> None:
        self.posts.append(json.loads(raw.decode()))
        handler.json_response(201, {"ok": True, "post": {"id": POST_ID}})

    def _post_readback(self, handler) -> None:
        post = self.posts[0]
        row = self.preview["media"][0]
        handler.json_response(200, {"ok": True, "post": {
            "id": POST_ID, "room": post["room"], "body": post["body"],
            "attachments": [{**post["attachments"][0], "kind": row["kind"],
                "media_type": row["media_type"], "bytes": row["bytes"],
                "url": "/v1/media/" + row["expected_media_id"]}]}})

    def _media_readback(self, handler) -> None:
        row = self.preview["media"][0]
        raw = self.uploads[0]
        body, code = (raw[:1], 206) if handler.headers.get("range") else (raw, 200)
        handler.send_response(code)
        if code == 206:
            handler.send_header("content-range", f"bytes 0-0/{len(raw)}")
        handler.send_header("content-type", row["media_type"])
        handler.send_header("content-length", str(len(body)))
        handler.send_header("x-content-type-options", "nosniff")
        handler.end_headers(); handler.wfile.write(body)

    def _verify(self, handler, raw: bytes) -> None:
        digest = handler.headers["content-digest"]
        expected = "sha-256=:" + base64.b64encode(hashlib.sha256(raw).digest()).decode() + ":"
        _require(digest == expected, "BULLETIN_DIGEST")
        params = handler.headers["signature-input"].removeprefix("sig1=")
        signature = re.fullmatch(r"sig1=:([A-Za-z0-9+/=]+):",
                                 handler.headers["signature"]).group(1)
        base = "\n".join(['"@method": POST',
            f'"@authority": {handler.headers["host"].lower()}',
            f'"@path": {handler.path}', f'"content-digest": {digest}',
            f'"@signature-params": {params}'])
        from cryptography.hazmat.primitives.asymmetric import ed25519
        key = ed25519.Ed25519PublicKey.from_public_bytes(
            base64.urlsafe_b64decode(self.public_jwk["x"] + "=="))
        key.verify(base64.b64decode(signature), base.encode())
        self.signed_requests += 1
