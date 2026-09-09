from __future__ import annotations

import base64
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import re
import socket
import threading

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from harness.outcome_bulletin_media import REQUEST_SCHEMA
from harness.private_artifact_fs import root_identity

OWNER = "owner_" + "a" * 32
OTHER_OWNER = "owner_" + "b" * 32
JOURNEY = "jrn_" + "a" * 32
NOW = "2026-09-09T12:00:00Z"
HEAD_TIME = 1788955200
POST_ID = "01KMEDIAARTICLE0000000000"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGNg"
    "AAIAAAUAAXpeqz8AAAAASUVORK5CYII=")
MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x08TIT2\x00\x00\x00\x00"
MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 16


def b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def media_id(raw: bytes) -> str:
    return b64u(hashlib.sha256(raw).digest())


def jwk_json() -> tuple[str, dict]:
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
    public_jwk = {"kty": "OKP", "crv": "Ed25519", "x": b64u(public)}
    return json.dumps({"public": public_jwk,
                       "private": {**public_jwk, "d": b64u(private)}}), public_jwk


def write_media(root):
    (root / "artifacts").mkdir(exist_ok=True)
    rows = [("image.png", PNG, "review image"),
            ("sound.mp3", MP3, "review audio"),
            ("clip.mp4", MP4, "review video")]
    for name, raw, _label in rows:
        (root / "artifacts" / name).write_bytes(raw)
    return rows


def media_request(root, *, base_url="https://bulletin.example",
                  description="A public creative artifact set from the selected run."):
    rows = write_media(root)
    return {
        "schema": REQUEST_SCHEMA,
        "mode": "artifact_share",
        "post": {
            "room": "findings",
            "title": "Loopback synth sketch",
            "description": description,
            "source_attribution": "Created by the owner during a selected run.",
            "limits": [
                "upload success does not prove license, authorship, malware safety, or hidden-data absence"
            ],
            "links": [{
                "label": "Flywheel",
                "url": "https://github.com/HarperZ9/flywheel/releases/tag/v0.6.1",
            }],
        },
        "artifact_root": {
            "path": str(root),
            "identity": root_identity(root).to_json_dict(),
        },
        "destination": {"base_url": base_url},
        "media": [{
            "artifact_id": f"artifact_{index:016x}",
            "label": label,
            "relative_path": f"artifacts/{name}",
            "alt": f"{label} from the selected Flywheel run.",
        } for index, (name, _raw, label) in enumerate(rows, start=1)],
    }


class MediaBoard:
    def __init__(self, public_jwk: dict, preview: dict, *, mode="ok") -> None:
        self.public_jwk = public_jwk
        self.preview = preview
        self.mode = mode
        self.uploads, self.posts, self.ranges = [], [], 0
        parent = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                length = int(self.headers.get("content-length", "0"))
                raw = self.rfile.read(length)
                parent._verify(self, raw)
                if self.path == "/v1/media":
                    parent._media(self, raw)
                else:
                    parent._post(self, raw)

            def do_GET(self):
                if self.path == f"/v1/posts/{POST_ID}":
                    parent._post_readback(self)
                    return
                parent._media_readback(self)

            def json_response(self, code, payload):
                self.send_response(code)
                self.send_header("content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode())

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

    def _drop(self, handler) -> None:
        handler.close_connection = True
        try:
            handler.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        handler.connection.close()

    def _media(self, handler, raw: bytes) -> None:
        self.uploads.append(raw)
        if self.mode == "drop_upload":
            self._drop(handler)
            return
        row = self.preview["media"][len(self.uploads) - 1]
        media = ("wrong" + row["expected_media_id"][5:]
                 if self.mode == "wrong_media" else row["expected_media_id"])
        media_type = (
            "image/jpeg" if self.mode == "wrong_media_type"
            else row["media_type"])
        payload = {
            "id": media, "media_type": media_type, "kind": row["kind"],
            "bytes": len(raw), "url": "/v1/media/" + media,
            "width": None, "height": None, "deduplicated": False}
        if self.mode == "legacy_type_only":
            payload.pop("media_type")
            payload["type"] = row["media_type"]
        if self.mode == "conflicting_media_type":
            payload["type"] = "application/octet-stream"
        if self.mode == "wrong_media_url":
            payload["url"] = "/wrong/" + media
        if self.mode == "authority_media_url":
            payload["url"] = "//evil.example/v1/media/" + media
        handler.json_response(201, {"ok": True, "media": payload})

    def _post(self, handler, raw: bytes) -> None:
        payload = json.loads(raw.decode())
        self.posts.append(payload)
        if self.mode == "drop_post":
            self._drop(handler)
            return
        handler.json_response(201, {"ok": True, "post": {"id": POST_ID}})

    def _post_readback(self, handler) -> None:
        post = self.posts[0]
        attachments = [
            {**item, "kind": row["kind"], "media_type": row["media_type"],
             "bytes": row["bytes"], "url": "/v1/media/" + item["media_id"]}
            for item, row in zip(post["attachments"], self.preview["media"])
        ]
        if self.mode == "wrong_attachment_url":
            attachments[0]["url"] = "/wrong/" + attachments[0]["media_id"]
        if self.mode == "authority_attachment_url":
            attachments[0]["url"] = (
                "//evil.example/v1/media/" + attachments[0]["media_id"])
        if self.mode == "wrong_attachment_media_type":
            attachments[0]["media_type"] = "image/jpeg"
        if self.mode == "conflicting_attachment_media_type":
            attachments[0]["type"] = "application/octet-stream"
        handler.json_response(200, {"ok": True, "post": {
            "id": POST_ID, "room": post["room"], "body": post["body"],
            "attachments": attachments}})

    def _media_readback(self, handler) -> None:
        media = handler.path.rsplit("/", 1)[-1]
        row = next(r for r in self.preview["media"]
                   if r["expected_media_id"] == media)
        raw = self.uploads[self.preview["media"].index(row)]
        if handler.headers.get("range"):
            self.ranges += 1
            handler.send_response(206)
            handler.send_header("content-range", f"bytes 0-0/{len(raw)}")
            body = raw[:1]
        else:
            handler.send_response(200)
            body = raw + b"x" if self.mode == "extra_public_byte" else raw
        handler.send_header("content-type", row["media_type"])
        handler.send_header("x-content-type-options", "nosniff")
        handler.end_headers()
        handler.wfile.write(body)

    def _verify(self, handler, raw: bytes) -> None:
        digest = handler.headers["content-digest"]
        expected = "sha-256=:" + base64.b64encode(
            hashlib.sha256(raw).digest()).decode() + ":"
        assert digest == expected
        params = handler.headers["signature-input"].removeprefix("sig1=")
        signature = re.fullmatch(
            r"sig1=:([A-Za-z0-9+/=]+):", handler.headers["signature"]).group(1)
        base = "\n".join([
            '"@method": POST',
            f'"@authority": {handler.headers["host"].lower()}',
            f'"@path": {handler.path}',
            f'"content-digest": {digest}',
            f'"@signature-params": {params}',
        ])
        key = ed25519.Ed25519PublicKey.from_public_bytes(
            base64.urlsafe_b64decode(self.public_jwk["x"] + "=="))
        key.verify(base64.b64decode(signature), base.encode())
