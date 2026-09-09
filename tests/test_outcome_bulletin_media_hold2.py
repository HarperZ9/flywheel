from __future__ import annotations

import base64
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

pytest.importorskip("cryptography")

from harness.bulletin_signed_transport import BULLETIN_KEY_SLOT
from harness.credential_handles import CredentialBindings, CredentialHandleStore
from harness.file_backed_store import FileBackedHarnessStore
from harness.gateway_grant_route import authorize_gateway_operation, gateway_grant_post
from harness.gateway_operation import AuthorizedOperation
from harness.journey_store import JourneyStore, MutationCommand
from harness.outcome_bulletin_media import (
    build_gateway_media_grant_request,
    build_gateway_media_publish_envelope,
    build_media_preview,
    preview_media_bytes,
    publish_authorized_media_preview,
)
from tests.bulletin_media_fixtures import (
    HEAD_TIME,
    JOURNEY,
    NOW,
    OWNER,
    PNG,
    MediaBoard,
    jwk_json,
    media_id,
    media_request,
)

LARGE_WAV = b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x01" * (2_100_000 - 12)
MAX_PNG = PNG + b"\x00" * (10 * 1024 * 1024 - len(PNG))


def _journey(state):
    return JourneyStore(state).create(MutationCommand(
        OWNER, JOURNEY, None, "hold2-create-1", "intake",
        {"legacy_label": None, "goal": "publish selected artifacts",
         "intake": {}, "occurred_at": NOW}))


def _authorized_media(state, preview, credential_ref):
    head = _journey(state).event_head_sha256
    request = build_gateway_media_grant_request(
        preview, journey_ref=JOURNEY, expected_event_head=head,
        client_request_id="hold2-media-request-1", credential_ref=credential_ref)
    proposal, status = gateway_grant_post(
        "/api/gateway-grants/prepare/lane.call", json.dumps(request).encode(),
        owner_ref=OWNER, state_root=state, clock=lambda: NOW)
    assert status == 200, proposal
    approval, status = gateway_grant_post(
        "/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": proposal["proposal_ref"]}).encode(),
        owner_ref=OWNER, state_root=state, clock=lambda: NOW)
    assert status == 200, approval
    envelope = build_gateway_media_publish_envelope(
        preview, journey_ref=JOURNEY, expected_event_head=head,
        client_request_id="hold2-media-request-1",
        grant_ref=approval["grant_ref"], credential_ref=credential_ref)
    return authorize_gateway_operation(
        "lane.call", json.dumps(envelope, separators=(",", ":")).encode(),
        owner_ref=OWNER, state_root=state, clock=lambda: NOW)


def _auth_for_preview(preview, credential_ref="cred_" + "a" * 32):
    operation = {"name": "bulletin", "tool": "board_publish_media_post",
                 "args": preview, "governance_tier": "T2", "timeout": 20,
                 "data_refs": preview["data_refs"],
                 "credential_refs": [credential_ref]}
    return AuthorizedOperation.for_test(
        action="lane.call", operation=operation,
        scopes=("exec", "network", "plugin", "secrets"))


def _post(base, token, path, body):
    request = urllib.request.Request(
        base + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {token}"},
        method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as response:
        return response.code, json.loads(response.read())


def _gateway(tmp_path, monkeypatch, run_root):
    from harness import gateway
    from harness.gateway_auth import load_or_create_owner_ref

    flywheel_home = tmp_path / "home"
    owner = load_or_create_owner_ref(flywheel_home)
    token = "unit-token"
    monkeypatch.setattr(gateway._Handler, "root", tmp_path, raising=False)
    monkeypatch.setattr(gateway._Handler, "run_root", str(run_root),
                        raising=False)
    monkeypatch.setattr(gateway._Handler, "flywheel_home", flywheel_home,
                        raising=False)
    monkeypatch.setattr(gateway._Handler, "auth_token", token, raising=False)
    monkeypatch.setattr(gateway._Handler, "allowed_hosts",
                        gateway.DEFAULT_HOSTS, raising=False)
    monkeypatch.setattr(gateway._Handler, "clock", staticmethod(lambda: NOW),
                        raising=False)
    server = ThreadingHTTPServer(("127.0.0.1", 0), gateway._Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    return server, thread, base, token, owner, flywheel_home / "state"


def test_http_mixed_run_selected_media_previews_large_wav(tmp_path, monkeypatch):
    run_root = tmp_path / "runs"
    png_path, wav_path, text_path = tmp_path / "image.png", tmp_path / "big.wav", tmp_path / "note.txt"
    png_path.write_bytes(PNG)
    wav_path.write_bytes(LARGE_WAV)
    text_path.write_text("not media", encoding="utf-8")
    store = FileBackedHarnessStore(run_root)
    run = store.create_run(kind="creative", title="mixed media run")
    png = store.copy_artifact(png_path, run_id=run["run_id"], label="cover art")
    wav = store.copy_artifact(wav_path, run_id=run["run_id"], label="large audio")
    store.copy_artifact(text_path, run_id=run["run_id"], label="notes")
    server, thread, base, token, owner, state = _gateway(
        tmp_path, monkeypatch, run_root)
    jwk, _ = jwk_json()
    handle = CredentialHandleStore(state, keychain_get=lambda _: jwk).bind(
        owner, "BULLETIN_AGENT_JWK")
    head = JourneyStore(state).create(MutationCommand(
        owner, JOURNEY, None, "hold2-http-create-1", "intake",
        {"legacy_label": None, "goal": "publish selected artifacts",
         "intake": {}, "occurred_at": NOW})).event_head_sha256
    try:
        status, listed = _post(
            base, token, "/api/gateway-grants/bulletin-media-artifacts",
            {"schema": "flywheel.bulletin-media-artifacts-request/v1",
             "run_id": run["run_id"]})
        assert status == 200, listed
        assert [row["artifact_id"] for row in listed["artifacts"]] == [
            png["artifact_id"], wav["artifact_id"]]
        unused = tmp_path / "unused"
        unused.mkdir()
        selection = {
            "schema": "flywheel.outcome-bulletin-media-selection/v1",
            "journey_ref": JOURNEY,
            "expected_event_head": head,
            "client_request_id": "hold2-large-wav-1",
            "credential_ref": handle.credential_ref,
            "run_id": run["run_id"],
            "destination": {"base_url": "https://bulletin.example"},
            "post": media_request(unused)["post"],
            "media": [{"artifact_id": wav["artifact_id"],
                       "alt": "Large selected audio from the mixed run."}],
        }
        status, prepared = _post(
            base, token, "/api/gateway-grants/bulletin-media-preview",
            selection)
        assert status == 200, prepared
        proposal = prepared["proposal"]
        review = proposal["summary"]["bulletin_media_review"]
        assert review["preview_media"][0]["bytes"] == len(LARGE_WAV)
        status, media = _post(
            base, token, "/api/gateway-grants/bulletin-media-preview-bytes",
            {"schema": "flywheel.bulletin-media-preview-bytes-request/v1",
             "proposal_ref": proposal["proposal_ref"],
             "preview_ref": review["preview_media"][0]["preview_ref"],
             "preview_sha256": review["preview_sha256"]})
        assert status == 200, media
        assert media["bytes"] == len(LARGE_WAV)
        assert base64.b64decode(media["body_b64"]) == LARGE_WAV
    finally:
        server.shutdown()
        thread.join(2)
        server.server_close()


def test_http_huge_cursor_is_typed_media_request_error(tmp_path, monkeypatch):
    run_root = tmp_path / "runs"
    FileBackedHarnessStore(run_root).init()
    server, thread, base, token, _owner, _state = _gateway(
        tmp_path, monkeypatch, run_root)
    try:
        status, body = _post(
            base, token, "/api/gateway-grants/bulletin-media-runs",
            {"schema": "flywheel.bulletin-media-runs-request/v1",
             "cursor": "9" * 5000})
        assert status == 422, body
        assert body["error"]["code"] == "INVALID_REQUEST"
    finally:
        server.shutdown()
        thread.join(2)
        server.server_close()


@pytest.mark.parametrize("mode", [
    "wrong_attachment_url",
    "authority_attachment_url",
    "wrong_attachment_media_type",
    "conflicting_attachment_media_type",
])
def test_loopback_readback_rejects_extra_bytes_and_noncanonical_urls(
        tmp_path, mode):
    state, root = tmp_path / "state", tmp_path / "store"
    root.mkdir()
    (root / "image.png").write_bytes(PNG)
    request = media_request(root, base_url="http://127.0.0.1:1")
    request["media"] = [request["media"][0]]
    jwk, public_jwk = jwk_json()
    preview = build_media_preview(
        request, state_root=state, owner_ref=OWNER, allow_loopback=True)
    server = MediaBoard(public_jwk, preview, mode=mode)
    try:
        request["destination"] = {"base_url": server.url}
        preview = build_media_preview(
            request, state_root=state, owner_ref=OWNER, allow_loopback=True)
        result = publish_authorized_media_preview(
            _auth_for_preview(preview), preview, state_root=state,
            allow_loopback=True,
            credential_bindings=CredentialBindings({BULLETIN_KEY_SLOT: jwk}),
            now=lambda: HEAD_TIME, nonce_bytes=lambda n: b"\x03" * n)
    finally:
        server.close()
    assert result["status"] == "posted_readback_drift"


def test_loopback_rejects_ten_mib_matching_prefix_with_extra_public_byte(
        tmp_path):
    state, root = tmp_path / "state", tmp_path / "store"
    root.mkdir()
    (root / "max.png").write_bytes(MAX_PNG)
    request = media_request(root, base_url="http://127.0.0.1:1")
    request["media"] = [{**request["media"][0], "relative_path": "max.png"}]
    jwk, public_jwk = jwk_json()
    preview = build_media_preview(
        request, state_root=state, owner_ref=OWNER, allow_loopback=True)
    server = MediaBoard(public_jwk, preview, mode="extra_public_byte")
    try:
        request["destination"] = {"base_url": server.url}
        preview = build_media_preview(
            request, state_root=state, owner_ref=OWNER, allow_loopback=True)
        result = publish_authorized_media_preview(
            _auth_for_preview(preview), preview, state_root=state,
            allow_loopback=True,
            credential_bindings=CredentialBindings({BULLETIN_KEY_SLOT: jwk}),
            now=lambda: HEAD_TIME, nonce_bytes=lambda n: b"\x04" * n)
    finally:
        server.close()
    assert result["status"] == "media_upload_drift"
    assert server.posts == []


def test_deadline_before_client_construction_returns_typed_result(
        tmp_path, monkeypatch):
    state, root = tmp_path / "state", tmp_path / "store"
    root.mkdir()
    preview = build_media_preview(
        media_request(root), state_root=state, owner_ref=OWNER)
    import harness.outcome_bulletin_media_publish as publisher
    ticks = iter([0.0, 1.0])
    monkeypatch.setattr(publisher.time, "monotonic", lambda: next(ticks))
    result = publish_authorized_media_preview(
        _auth_for_preview(preview), preview, state_root=state,
        credential_bindings=CredentialBindings({BULLETIN_KEY_SLOT: jwk_json()[0]}),
        timeout=0)
    assert result["status"] == "publish_unavailable"


def test_direct_publish_validates_packet_before_key_resolution(tmp_path):
    state, root = tmp_path / "state", tmp_path / "store"
    root.mkdir()
    jwk, _ = jwk_json()
    handle = CredentialHandleStore(state, keychain_get=lambda _: jwk).bind(
        OWNER, "BULLETIN_AGENT_JWK")
    preview = build_media_preview(
        media_request(root), state_root=state, owner_ref=OWNER)
    authorized = _authorized_media(state, preview, handle.credential_ref)
    (root / "artifacts" / "image.png").write_bytes(b"\x89PNG\r\n\x1a\nchanged")
    calls = []
    result = publish_authorized_media_preview(
        authorized, preview, state_root=state,
        keychain_get=lambda slot: calls.append(slot) or jwk)
    assert result["status"] == "publish_unavailable"
    assert calls == []
