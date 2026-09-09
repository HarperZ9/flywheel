from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
import struct
from pathlib import Path
import sys
import threading
import time
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Start a real gateway fixture for Bulletin media tests.")
    parser.add_argument("--fixture-root", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--bulletin-base-url", default="")
    parser.add_argument("--handle", default="flywheel-e2e")
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    from harness import gateway
    from harness.bulletin_signed_transport import BULLETIN_KEY_SLOT
    from harness.credential_handles import CredentialHandleStore
    from harness.file_backed_store import FileBackedHarnessStore
    from harness.gateway_auth import load_or_create_owner_ref
    from harness.journey_store import JourneyStore, MutationCommand
    import harness.keychain as keychain
    from tests.bulletin_media_fixtures import (
        JOURNEY,
        NOW,
        PNG,
        MediaBoard,
        jwk_json,
    )
    from tests.bulletin_media_http_fixture import (
        actual_worker_start_commands,
        public_registration,
        register_loopback_identity,
        validate_loopback_bulletin_base_url,
    )

    actual_worker_mode = bool(args.bulletin_base_url.strip())
    fixture_clock = _utc_now if actual_worker_mode else lambda: NOW

    fixture_root = Path(args.fixture_root).resolve()
    flywheel_home = fixture_root / "home"
    run_root = fixture_root / "runs"
    config_path = Path(args.config).resolve()
    state_root = flywheel_home / "state"
    fixture_root.mkdir(parents=True, exist_ok=True)
    owner = load_or_create_owner_ref(flywheel_home)

    source = fixture_root / "source.png"
    source_bytes = _actual_worker_png() if actual_worker_mode else PNG
    source.write_bytes(source_bytes)
    store = FileBackedHarnessStore(run_root)
    run = store.create_run(kind="creative", title="dart selected art")
    artifact = store.copy_artifact(
        source, run_id=run["run_id"], label="cover art")

    head = JourneyStore(state_root).create(MutationCommand(
        owner, JOURNEY, None, "dart-http-create-1", "intake",
        {"legacy_label": None, "goal": "publish selected artifacts",
         "intake": {}, "occurred_at": fixture_clock()})).event_head_sha256

    jwk, public_jwk = jwk_json()
    board = None
    control_server = None
    registration = None
    if actual_worker_mode:
        bulletin_base_url = validate_loopback_bulletin_base_url(
            args.bulletin_base_url)
        registration = register_loopback_identity(
            bulletin_base_url, jwk, handle=args.handle,
            timeout=_bounded_timeout(args.timeout))
        fixture_mode = "actual_worker_loopback"
        control_url = ""
    else:
        board = MediaBoard(public_jwk, {})
        control_server = _start_control_server(board)
        bulletin_base_url = board.url
        fixture_mode = "synthetic_media_board"
        control_host, control_port = control_server.server_address
        control_url = f"http://{control_host}:{control_port}"

    handle = CredentialHandleStore(
        state_root, keychain_get=lambda _slot: jwk).bind(owner, BULLETIN_KEY_SLOT)

    keychain.keychain_get = (
        lambda slot: jwk if slot == BULLETIN_KEY_SLOT else None)
    os.environ["FLYWHEEL_HOME"] = str(flywheel_home)
    os.environ["FLYWHEEL_BULLETIN_ALLOW_LOOPBACK"] = "1"
    os.environ["FLYWHEEL_BULLETIN_BASE_URL"] = bulletin_base_url

    token = "synthetic-unit-token"
    gateway._Handler.root = fixture_root
    gateway._Handler.run_root = str(run_root)
    gateway._Handler.flywheel_home = flywheel_home
    gateway._Handler.auth_token = token
    gateway._Handler.allowed_hosts = gateway.DEFAULT_HOSTS
    gateway._Handler.clock = staticmethod(fixture_clock)

    server = ThreadingHTTPServer(("127.0.0.1", 0), gateway._Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "schema": "flywheel.bulletin-media-gateway-fixture/v1",
        "mode": fixture_mode,
        "base_url": f"http://{host}:{port}",
        "token": token,
        "journey_ref": JOURNEY,
        "event_head": head,
        "credential_ref": handle.credential_ref,
        "run_id": run["run_id"],
        "artifact_id": artifact["artifact_id"],
        "bulletin_base_url": bulletin_base_url,
        "control_url": control_url,
    }
    if registration is not None:
        config["identity_registration"] = public_registration(registration)
        config["worker_start_commands"] = actual_worker_start_commands(
            fixture_root / "miniflare-state")
    config_path.write_text(json.dumps(config), encoding="utf-8")
    print(f"READY {config_path}", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        thread.join(2)
        server.server_close()
        if control_server is not None:
            control_server.shutdown()
            control_server.server_close()
        if board is not None:
            board.close()
    return 0


def _actual_worker_png() -> bytes:
    width, height = 4, 4
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            row.extend((x * 64, y * 64, 160, 255))
        rows.append(bytes(row))
    return b"\x89PNG\r\n\x1a\n" + _png_chunk(
        b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) + _png_chunk(
            b"IDAT", zlib.compress(b"".join(rows))) + _png_chunk(b"IEND", b"")


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(kind + data) & 0xffffffff
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)


def _start_control_server(board: object) -> ThreadingHTTPServer:
    class ControlHandler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            if self.path != "/set-preview":
                self.send_response(404)
                self.end_headers()
                return
            length = int(self.headers.get("content-length", "0"))
            try:
                preview = json.loads(self.rfile.read(length).decode("utf-8"))
                board.preview = preview
                body = json.dumps({"ok": True}).encode("utf-8")
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                self.send_response(422)
                self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), ControlHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    server.thread = thread
    return server


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _bounded_timeout(value: int) -> int:
    if not isinstance(value, int) or value < 1 or value > 60:
        raise ValueError("timeout must be between 1 and 60 seconds")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
