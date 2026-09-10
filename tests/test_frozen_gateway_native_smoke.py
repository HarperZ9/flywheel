from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request

import pytest

pytest.importorskip("cryptography")

from harness.bulletin_signed_transport import BULLETIN_KEY_SLOT
from harness.credential_handles import CredentialHandleStore
from harness.gateway_grant_route import authorize_gateway_operation, gateway_grant_post
from harness.gateway_provider_adapter import resolve_credentials
from harness.journey_store import JourneyStore, MutationCommand
from harness.outcome_bulletin_media import (
    build_gateway_media_grant_request,
    build_gateway_media_publish_envelope,
    build_media_preview,
)
from tests.bulletin_media_fixtures import JOURNEY, NOW, OWNER, jwk_json, media_request


def test_media_grant_resolves_environment_key_after_approval(monkeypatch, tmp_path):
    state, root = tmp_path / "state", tmp_path / "store"
    root.mkdir()
    jwk, _public = jwk_json()
    monkeypatch.setenv(BULLETIN_KEY_SLOT, jwk)
    monkeypatch.setenv("FLYWHEEL_BULLETIN_ALLOW_LOOPBACK", "1")
    monkeypatch.setenv("FLYWHEEL_BULLETIN_BASE_URL", "http://127.0.0.1:1")
    handle = CredentialHandleStore(state, keychain_get=lambda _slot: jwk).bind(
        OWNER, BULLETIN_KEY_SLOT)
    preview = build_media_preview(
        media_request(root, base_url="http://127.0.0.1:1"),
        state_root=state, owner_ref=OWNER, allow_loopback=True)
    head = JourneyStore(state).create(MutationCommand(
        OWNER, JOURNEY, None, "frozen-smoke-media-create", "intake",
        {"legacy_label": None, "goal": "publish selected artifacts",
         "intake": {}, "occurred_at": NOW})).event_head_sha256
    request = build_gateway_media_grant_request(
        preview, journey_ref=JOURNEY, expected_event_head=head,
        client_request_id="frozen-smoke-media", credential_ref=handle.credential_ref)
    proposal, status = gateway_grant_post(
        "/api/gateway-grants/prepare/lane.call",
        json.dumps(request).encode(), owner_ref=OWNER, state_root=state,
        clock=lambda: NOW)
    assert status == 200, proposal
    approval, status = gateway_grant_post(
        "/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": proposal["proposal_ref"]}).encode(),
        owner_ref=OWNER, state_root=state, clock=lambda: NOW)
    assert status == 200, approval
    envelope = build_gateway_media_publish_envelope(
        preview, journey_ref=JOURNEY, expected_event_head=head,
        client_request_id="frozen-smoke-media",
        grant_ref=approval["grant_ref"], credential_ref=handle.credential_ref)

    authorized = authorize_gateway_operation(
        "lane.call", json.dumps(envelope, separators=(",", ":")).encode(),
        owner_ref=OWNER, state_root=state, clock=lambda: NOW)
    resolved = resolve_credentials(authorized, state)

    assert resolved.credential_bindings.value_for(BULLETIN_KEY_SLOT) == jwk



def test_writing_smoke_requires_real_route_state_sequence():
    from scripts.frozen_gateway_native_payloads import WRITING_BODY
    from scripts.frozen_gateway_native_smoke import run_writing_acceptance_smoke

    journey = "jrn_" + "e" * 32
    heads = {"p_init": "1" * 64, "p_section": "2" * 64, "p_revision": "3" * 64}
    calls = []
    revision_body = None

    def fake_request(_base, path, _token, *, body=None, secret_values=()):
        nonlocal revision_body
        calls.append((path.split("?", 1)[0], body, secret_values))
        if path == "/api/writing/status":
            return 200, {"schema": "flywheel.writing-status/v1"}
        if path == "/api/writing/init/prepare":
            return 200, {"proposal_ref": "p_init"}
        if path == "/api/writing/section/prepare":
            assert body["section"]["section_ref"] == "sec_acceptance"
            return 200, {"proposal_ref": "p_section"}
        if path == "/api/writing/revision/prepare":
            revision_body = body["body"]
            return 200, {"proposal_ref": "p_revision"}
        if path == "/api/writing/proposal/approve":
            return 200, {"grant_ref": "grant_" + body["proposal_ref"]}
        if path == "/api/writing/proposal/commit":
            return 200, {"journey_ref": journey,
                         "event_head_sha256": heads[body["proposal_ref"]]}
        if path.startswith("/api/writing/project?"):
            return 200, {"journey_ref": journey,
                         "sections": [{"current_body": WRITING_BODY}]}
        raise AssertionError(path)

    summary = run_writing_acceptance_smoke(
        "http://127.0.0.1:1", "token", secrets=("token",), request=fake_request)

    assert revision_body == WRITING_BODY
    assert summary["journey_ref"] == journey
    assert summary["event_head_sha256"] == "3" * 64
    assert summary["routes"] == [path for path, _body, _secrets in calls]



@pytest.mark.parametrize("corruption", [None, "preview", "upload", "missing_upload", "duplicate_upload"])
def test_bulletin_media_smoke_binds_actual_bytes_before_acceptance(corruption):
    from scripts.frozen_gateway_native_smoke import run_bulletin_media_acceptance_smoke

    class Board:
        url = "http://127.0.0.1:55"
        preview = None
        signed_requests = 0
        posts = []
        uploads = []

    class Fixture:
        board = Board()
        media_journey_ref = "jrn_" + "f" * 32
        media_event_head = "1" * 64
        credential_ref = "cred_" + "a" * 32
        run_id = "run_20260909T120000_abcdefabcdef"
        artifact_id = "artifact_" + "c" * 16
        artifact_sha256 = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        artifact_bytes = 3

    calls = []
    raw = b"abc"

    def fake_request(_base, path, _token, *, body=None, secret_values=()):
        calls.append(path)
        if path == "/api/gateway-grants/bulletin-media-runs":
            return 200, {"runs": [{"run_id": Fixture.run_id,
                                    "artifact_count": 1}]}
        if path == "/api/gateway-grants/bulletin-media-artifacts":
            assert body["run_id"] == Fixture.run_id
            return 200, {"artifacts": [{"artifact_id": Fixture.artifact_id,
                                         "sha256": Fixture.artifact_sha256}]}
        if path == "/api/gateway-grants/bulletin-media-preview":
            assert body["credential_ref"] == Fixture.credential_ref
            return 200, {"proposal": {
                "proposal_ref": "prp_" + "b" * 32,
                "summary": {"bulletin_media_review": {
                    "preview_sha256": "e" * 64,
                    "preview_media": [{"preview_ref": "prv_" + "f" * 32}],
                }}}, "operation": {
                    "schema": "flywheel.gateway-operation/v1",
                    "journey_ref": Fixture.media_journey_ref,
                    "expected_event_head": Fixture.media_event_head,
                    "client_request_id": "frozen-native-media",
                    "operation": {"name": "bulletin",
                                  "tool": "board_publish_media_post",
                                  "args": {"media": []}},
                }}
        if path == "/api/gateway-grants/bulletin-media-preview-bytes":
            assert body["preview_sha256"] == "e" * 64
            return 200, {"bytes": 3, "sha256": Fixture.artifact_sha256,
                         "body_b64": base64.b64encode(
                             b"abd" if corruption == "preview" else raw).decode()}
        if path == "/api/gateway-grants/approve-once":
            return 200, {"grant_ref": "grant_" + "a" * 32}
        if path == "/api/lane/bulletin/board_publish_media_post":
            Fixture.board.signed_requests = 2
            Fixture.board.posts = [{"body": "posted"}]
            Fixture.board.uploads = [b"abd" if corruption == "upload" else raw]
            if corruption == "missing_upload":
                Fixture.board.uploads = []
            elif corruption == "duplicate_upload":
                Fixture.board.uploads = [raw, raw]
            return 200, {"status": "posted_readback_match"}
        raise AssertionError(path)

    if corruption:
        failure = "MEDIA_PREVIEW_BYTES" if corruption == "preview" else "MEDIA_UPLOAD_BYTES"
        with pytest.raises(RuntimeError, match=failure):
            run_bulletin_media_acceptance_smoke(
                "http://127.0.0.1:1", "token", Fixture(), request=fake_request)
        return
    summary = run_bulletin_media_acceptance_smoke(
        "http://127.0.0.1:1", "token", Fixture(), request=fake_request)

    assert summary["result_state"] == "posted_readback_match"
    assert summary["signed_uploads"] == 1
    assert summary["routes"] == calls


def test_native_smoke_summary_requires_writing_and_bulletin_results():
    from scripts.frozen_gateway_native_smoke import validate_native_smoke_summary

    good = {
        "writing": {
            "journey_ref": "jrn_" + "a" * 32,
            "current_body_sha256": "b" * 64,
            "routes": [
                "/api/writing/status",
                "/api/writing/init/prepare",
                "/api/writing/section/prepare",
                "/api/writing/revision/prepare",
                "/api/writing/project",
            ],
        },
        "bulletin_media": {
            "run_id": "run_20260909T120000_abcdefabcdef",
            "artifact_id": "artifact_" + "c" * 16,
            "preview_bytes": 67,
            "preview_sha256": "d" * 64,
            "result_state": "posted_readback_match",
            "signed_uploads": 1,
            "posts": 1,
            "routes": [
                "/api/gateway-grants/bulletin-media-runs",
                "/api/gateway-grants/bulletin-media-artifacts",
                "/api/gateway-grants/bulletin-media-preview",
                "/api/gateway-grants/bulletin-media-preview-bytes",
                "/api/lane/bulletin/board_publish_media_post",
            ],
        },
    }
    validate_native_smoke_summary(good)

    missing = dict(good)
    missing["bulletin_media"] = {
        **good["bulletin_media"],
        "result_state": "media_upload_drift",
    }
    with pytest.raises(RuntimeError, match="BULLETIN_MEDIA_RESULT"):
        validate_native_smoke_summary(missing)



def test_loopback_board_rejects_unknown_paths():
    from scripts.frozen_gateway_media_board import LoopbackMediaBoard

    board = LoopbackMediaBoard({"x": "A" * 43})
    try:
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(board.url + "/unexpected", timeout=5)
        assert exc.value.code == 404
        assert board.signed_requests == 0
    finally:
        board.close()


def test_release_checker_wires_native_acceptance_after_startup():
    text = open("scripts/check_frozen_gateway.py", encoding="utf-8").read()

    assert "prepare_native_smoke_fixture" in text
    assert "run_native_acceptance_smoke" in text
    assert "native Writing workflow" in text
    assert "native Bulletin media publication" in text
