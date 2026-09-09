from __future__ import annotations

import json
import base64
import hashlib

import pytest

pytest.importorskip("cryptography")

from harness.bulletin_signed_transport import BULLETIN_KEY_SLOT
from harness.credential_handles import CredentialBindings, CredentialHandleStore
from harness.file_backed_store import FileBackedHarnessStore
from harness.gateway_grant_route import authorize_gateway_operation, gateway_grant_post
from harness.gateway_operation import AuthorizedOperation, GatewayOperationError
from harness.gateway_provider_adapter import resolve_credentials
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
    OTHER_OWNER,
    PNG,
    MediaBoard,
    jwk_json,
    media_id,
    media_request,
)


def _journey(state):
    return JourneyStore(state).create(MutationCommand(
        OWNER, JOURNEY, None, "create-1", "intake",
        {"legacy_label": None, "goal": "publish selected artifacts",
         "intake": {}, "occurred_at": NOW}))


def _authorized_media(state, preview, credential_ref):
    head = _journey(state).event_head_sha256
    request = build_gateway_media_grant_request(
        preview, journey_ref=JOURNEY, expected_event_head=head,
        client_request_id="media-request-1", credential_ref=credential_ref)
    proposal, status = gateway_grant_post(
        "/api/gateway-grants/prepare/lane.call", json.dumps(request).encode(),
        owner_ref=OWNER, state_root=state, clock=lambda: NOW)
    assert status == 200, proposal
    assert proposal["summary"]["bulletin_media_review"]["mode"] == "artifact_share"
    approval, status = gateway_grant_post(
        "/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": proposal["proposal_ref"]}).encode(),
        owner_ref=OWNER, state_root=state, clock=lambda: NOW)
    assert status == 200, approval
    envelope = build_gateway_media_publish_envelope(
        preview, journey_ref=JOURNEY, expected_event_head=head,
        client_request_id="media-request-1", grant_ref=approval["grant_ref"],
        credential_ref=credential_ref)
    return authorize_gateway_operation(
        "lane.call", json.dumps(envelope, separators=(",", ":")).encode(),
        owner_ref=OWNER, state_root=state, clock=lambda: NOW)


def _auth_for_preview(preview):
    operation = {"name": "bulletin", "tool": "board_publish_media_post",
                 "args": preview, "governance_tier": "T2", "timeout": 20,
                 "data_refs": preview["data_refs"],
                 "credential_refs": ["cred_" + "a" * 32]}
    return AuthorizedOperation.for_test(
        action="lane.call", operation=operation,
        scopes=("exec", "network", "plugin", "secrets"))


def test_creative_artifact_preview_binds_media_without_checked_claims(tmp_path):
    state, root = tmp_path / "state", tmp_path / "store"
    root.mkdir()
    preview = build_media_preview(media_request(root), state_root=state)
    assert "Checked:" not in preview["post"]["body"]
    assert "license, authorship" in preview["post"]["body"]
    assert preview["post"]["attachments"][0]["media_id"] == media_id(PNG)
    assert preview["media"][1]["kind"] == "audio"
    assert preview["media"][2]["kind"] == "video"
    assert str(root) not in json.dumps(preview)
    raw, headers = preview_media_bytes(state, preview["preview_media"][0]["preview_ref"])
    assert raw == PNG and headers["content-type"] == "image/png"


def test_run_artifact_selection_route_prepares_proposal_and_bound_preview_bytes(tmp_path):
    state, run_root, source = tmp_path / "state", tmp_path / "runs", tmp_path / "source.png"
    source.write_bytes(PNG)
    store = FileBackedHarnessStore(run_root)
    run = store.create_run(kind="creative", title="music and art sketch")
    artifact = store.copy_artifact(source, run_id=run["run_id"], label="cover art")
    head = _journey(state).event_head_sha256
    jwk, _ = jwk_json()
    handle = CredentialHandleStore(state, keychain_get=lambda _: jwk).bind(
        OWNER, BULLETIN_KEY_SLOT)
    runs, status = gateway_grant_post(
        "/api/gateway-grants/bulletin-media-runs",
        json.dumps({"schema": "flywheel.bulletin-media-runs-request/v1"}).encode(),
        owner_ref=OWNER, state_root=state, run_root=run_root, clock=lambda: NOW)
    assert status == 200 and runs["runs"][0]["artifact_count"] == 1
    artifacts, status = gateway_grant_post(
        "/api/gateway-grants/bulletin-media-artifacts",
        json.dumps({"schema": "flywheel.bulletin-media-artifacts-request/v1",
                    "run_id": run["run_id"]}).encode(),
        owner_ref=OWNER, state_root=state, run_root=run_root, clock=lambda: NOW)
    assert status == 200 and artifacts["artifacts"][0]["kind"] == "image"
    assert not ({"source_path", "stored_path", "relative_path"}
                & artifacts["artifacts"][0].keys())
    body = {
        "schema": "flywheel.outcome-bulletin-media-selection/v1",
        "journey_ref": JOURNEY,
        "expected_event_head": head,
        "client_request_id": "selected-run-media-1",
        "credential_ref": handle.credential_ref,
        "run_id": run["run_id"],
        "destination": {"base_url": "https://bulletin.example"},
        "post": media_request((tmp_path / "unused").mkdir() or tmp_path / "unused")["post"],
        "media": [{"artifact_id": artifact["artifact_id"],
                   "alt": "Cover art from the selected creative run."}],
    }
    bad = {**body, "media": [{**body["media"][0], "relative_path": "source.png"}]}
    response, status = gateway_grant_post(
        "/api/gateway-grants/bulletin-media-preview", json.dumps(bad).encode(),
        owner_ref=OWNER, state_root=state, run_root=run_root, clock=lambda: NOW)
    assert status == 422 and response["error"]["code"] == "INVALID_REQUEST"
    prepared, status = gateway_grant_post(
        "/api/gateway-grants/bulletin-media-preview", json.dumps(body).encode(),
        owner_ref=OWNER, state_root=state, run_root=run_root, clock=lambda: NOW)
    assert status == 200, prepared
    assert prepared["schema"] == "flywheel.outcome-bulletin-media-preview-response/v1"
    proposal = prepared["proposal"]
    operation = prepared["operation"]
    assert operation == {
        "schema": "flywheel.gateway-operation/v1",
        "action": "lane.call",
        "journey_ref": JOURNEY,
        "expected_event_head": head,
        "client_request_id": "selected-run-media-1",
        "operation": operation["operation"],
    }
    assert operation["operation"]["name"] == "bulletin"
    assert operation["operation"]["tool"] == proposal["tool"]
    assert operation["operation"]["data_refs"] == proposal["data_refs"]
    assert operation["operation"]["credential_refs"] == proposal["credential_refs"]
    review = proposal["summary"]["bulletin_media_review"]
    assert review["attachments"][0]["media_id"] == media_id(PNG)
    assert str(source) not in json.dumps(prepared)
    assert not (state / "artifacts.jsonl").exists()
    assert (state / "bulletin-media-previews" / OWNER).exists()
    payload = {"schema": "flywheel.bulletin-media-preview-bytes-request/v1",
               "proposal_ref": proposal["proposal_ref"],
               "preview_ref": review["preview_media"][0]["preview_ref"],
               "preview_sha256": review["preview_sha256"]}
    media, status = gateway_grant_post(
        "/api/gateway-grants/bulletin-media-preview-bytes",
        json.dumps(payload).encode(), owner_ref=OWNER, state_root=state,
        run_root=run_root, clock=lambda: NOW)
    assert status == 200, media
    denied, status = gateway_grant_post(
        "/api/gateway-grants/bulletin-media-preview-bytes",
        json.dumps(payload).encode(), owner_ref=OTHER_OWNER, state_root=state,
        run_root=run_root, clock=lambda: NOW)
    assert status == 403 and denied["error"]["code"] == "PERMISSION_REQUIRED"
    assert base64.b64decode(media["body_b64"]) == PNG
    assert media["cache"] == "no-store"
    assert media["sha256"] == hashlib.sha256(PNG).hexdigest()



@pytest.mark.parametrize("name, raw", [
    ("active.svg", b"<svg><script>alert(1)</script></svg>"),
    ("page.html", b"<!doctype html><script>alert(1)</script>"),
])
def test_active_content_is_rejected_before_grant_packet(tmp_path, name, raw):
    state, root = tmp_path / "state", tmp_path / "store"
    root.mkdir()
    (root / name).write_bytes(raw)
    request = media_request(root)
    request["media"] = [{**request["media"][0], "relative_path": name}]
    with pytest.raises(Exception):
        build_media_preview(request, state_root=state)
    assert not (state / "bulletin-media-previews").exists()


def test_byte_or_destination_drift_fails_before_secret_resolution(tmp_path, monkeypatch):
    state, root = tmp_path / "state", tmp_path / "store"
    root.mkdir()
    jwk, _ = jwk_json()
    handle = CredentialHandleStore(state, keychain_get=lambda _: jwk).bind(
        OWNER, BULLETIN_KEY_SLOT)
    preview = build_media_preview(
        media_request(root), state_root=state, owner_ref=OWNER)
    authorized = _authorized_media(state, preview, handle.credential_ref)
    import harness.keychain as keychain
    resolved_slots = []
    monkeypatch.setattr(
        keychain, "keychain_get", lambda slot: resolved_slots.append(slot) or jwk)
    monkeypatch.setenv("FLYWHEEL_BULLETIN_BASE_URL", "https://other.example")
    with pytest.raises(GatewayOperationError):
        resolve_credentials(authorized, state)
    assert resolved_slots == []
    monkeypatch.setenv("FLYWHEEL_BULLETIN_BASE_URL", "https://bulletin.example")
    (root / "artifacts" / "image.png").write_bytes(b"\x89PNG\r\n\x1a\nchanged")
    with pytest.raises(GatewayOperationError):
        resolve_credentials(authorized, state)
    assert resolved_slots == []


def test_loopback_uploads_verify_same_bytes_ranges_and_post_once(tmp_path):
    state, root = tmp_path / "state", tmp_path / "store"
    root.mkdir()
    jwk, public_jwk = jwk_json()
    preview = build_media_preview(
        media_request(root, base_url="http://127.0.0.1:1"), state_root=state,
        owner_ref=OWNER, allow_loopback=True)
    server = MediaBoard(public_jwk, preview)
    try:
        preview = build_media_preview(
            media_request(root, base_url=server.url), state_root=state,
            owner_ref=OWNER, allow_loopback=True)
        result = publish_authorized_media_preview(
            _auth_for_preview(preview), preview, state_root=state,
            allow_loopback=True,
            credential_bindings=CredentialBindings({BULLETIN_KEY_SLOT: jwk}),
            now=lambda: HEAD_TIME, nonce_bytes=lambda n: b"\x01" * n)
    finally:
        server.close()
    assert result["status"] == "posted_readback_match"
    assert len(server.uploads) == 3 and len(server.posts) == 1
    assert server.ranges == 2


def test_wrong_media_id_or_lost_upload_never_posts(tmp_path):
    state, root = tmp_path / "state", tmp_path / "store"
    root.mkdir()
    jwk, public_jwk = jwk_json()
    preview = build_media_preview(
        media_request(root, base_url="http://127.0.0.1:1"), state_root=state,
        owner_ref=OWNER, allow_loopback=True)
    for mode, status in (("wrong_media", "media_upload_drift"),
                         ("drop_upload", "media_upload_unverified")):
        server = MediaBoard(public_jwk, preview, mode=mode)
        try:
            preview = build_media_preview(
                media_request(root, base_url=server.url), state_root=state,
                owner_ref=OWNER, allow_loopback=True)
            result = publish_authorized_media_preview(
                _auth_for_preview(preview), preview, state_root=state,
                allow_loopback=True,
                credential_bindings=CredentialBindings({BULLETIN_KEY_SLOT: jwk}),
                now=lambda: HEAD_TIME, nonce_bytes=lambda n: b"\x02" * n)
        finally:
            server.close()
        assert result["status"] == status
        assert server.posts == []
