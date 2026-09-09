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
from harness.credential_handles import CredentialHandleStore
from harness.file_backed_store import FileBackedHarnessStore
from harness.journey_store import JourneyStore, MutationCommand
from tests.bulletin_media_fixtures import (
    JOURNEY,
    NOW,
    PNG,
    MediaBoard,
    jwk_json,
    media_id,
)


def test_gateway_http_media_runs_paginates_optional_limit_and_cursor(
        tmp_path, monkeypatch):
    from harness import gateway
    from harness.gateway_auth import load_or_create_owner_ref

    flywheel_home, run_root = tmp_path / "home", tmp_path / "runs"
    owner = load_or_create_owner_ref(flywheel_home)
    source = tmp_path / "source.png"
    source.write_bytes(PNG)
    store = FileBackedHarnessStore(run_root)
    runs = [store.create_run(kind="creative", title=f"run {index}")
            for index in range(3)]
    for run in runs:
        store.copy_artifact(source, run_id=run["run_id"], label="cover art")
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

    def post(body):
        req = urllib.request.Request(
            base + "/api/gateway-grants/bulletin-media-runs",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {token}"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as response:
            return response.code, json.loads(response.read())

    try:
        default_request = {
            "schema": "flywheel.bulletin-media-runs-request/v1",
            "limit": None,
            "cursor": None,
        }
        status, page = post(default_request)
        assert status == 200, page
        assert [row["run_id"] for row in page["runs"]] == [
            row["run_id"] for row in runs]
        assert page["next_cursor"] is None

        status, page = post({
            "schema": "flywheel.bulletin-media-runs-request/v1",
            "limit": 2,
        })
        assert status == 200, page
        assert [row["run_id"] for row in page["runs"]] == [
            runs[0]["run_id"], runs[1]["run_id"]]
        assert page["next_cursor"] == "2"
        status, page = post({
            "schema": "flywheel.bulletin-media-runs-request/v1",
            "limit": 2,
            "cursor": page["next_cursor"],
        })
        assert status == 200, page
        assert [row["run_id"] for row in page["runs"]] == [runs[2]["run_id"]]
        assert page["next_cursor"] is None

        for invalid in (0, 101, "2"):
            status, body = post({
                "schema": "flywheel.bulletin-media-runs-request/v1",
                "limit": invalid,
            })
            assert status == 422, body
        status, body = post({
            "schema": "flywheel.bulletin-media-runs-request/v1",
            "cursor": "not-a-cursor",
        })
        assert status == 422, body
    finally:
        server.shutdown()
        thread.join(2)
        server.server_close()


@pytest.mark.parametrize(("board_mode", "expected_status"), [
    ("ok", "posted_readback_match"),
    ("extra_public_byte", "media_upload_drift"),
])
def test_gateway_http_media_picker_preview_bytes_uses_authenticated_handler(
        tmp_path, monkeypatch, board_mode, expected_status):
    """The native route must work through the real HTTP handler.

    A helper-only gateway_grant_post test does not catch function-local import
    shadowing or auth/header setup in harness.gateway._Handler._post().
    """
    from harness import gateway
    from harness.gateway_auth import load_or_create_owner_ref

    flywheel_home, run_root = tmp_path / "home", tmp_path / "runs"
    state = flywheel_home / "state"
    owner = load_or_create_owner_ref(flywheel_home)
    source = tmp_path / "source.png"
    source.write_bytes(PNG)
    store = FileBackedHarnessStore(run_root)
    run = store.create_run(kind="creative", title="http selected art")
    artifact = store.copy_artifact(source, run_id=run["run_id"], label="cover art")
    head = JourneyStore(state).create(MutationCommand(
        owner, JOURNEY, None, "http-create-1", "intake",
        {"legacy_label": None, "goal": "publish selected artifacts",
         "intake": {}, "occurred_at": NOW})).event_head_sha256
    jwk, public_jwk = jwk_json()
    board = MediaBoard(public_jwk, {}, mode=board_mode)
    handle = CredentialHandleStore(state, keychain_get=lambda _: jwk).bind(
        owner, BULLETIN_KEY_SLOT)
    import harness.keychain as keychain
    monkeypatch.setattr(
        keychain, "keychain_get",
        lambda slot: jwk if slot == BULLETIN_KEY_SLOT else None)
    monkeypatch.setenv("FLYWHEEL_BULLETIN_ALLOW_LOOPBACK", "1")
    monkeypatch.setenv("FLYWHEEL_BULLETIN_BASE_URL", board.url)
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

    def post(path, body):
        req = urllib.request.Request(
            base + path, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {token}"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as response:
            return response.code, json.loads(response.read())

    try:
        status, runs = post(
            "/api/gateway-grants/bulletin-media-runs",
            {"schema": "flywheel.bulletin-media-runs-request/v1"})
        assert status == 200, runs
        assert runs["runs"][0]["run_id"] == run["run_id"]
        assert runs["runs"][0]["artifact_count"] == 1
        status, artifacts = post(
            "/api/gateway-grants/bulletin-media-artifacts",
            {"schema": "flywheel.bulletin-media-artifacts-request/v1",
             "run_id": run["run_id"]})
        assert status == 200, artifacts
        assert artifacts["artifacts"][0]["artifact_id"] == artifact["artifact_id"]
        assert artifacts["artifacts"][0]["kind"] == "image"
        assert not ({"source_path", "stored_path", "relative_path"}
                    & artifacts["artifacts"][0].keys())
        selection = {
            "schema": "flywheel.outcome-bulletin-media-selection/v1",
            "journey_ref": JOURNEY,
            "expected_event_head": head,
            "client_request_id": "http-selected-run-media-1",
            "credential_ref": handle.credential_ref,
            "run_id": run["run_id"],
            "destination": {"base_url": board.url},
            "post": {
                "room": "findings",
                "title": "HTTP selected synth sketch",
                "description": "A public creative artifact selected by run ID.",
                "source_attribution": (
                    "Created by the owner during a selected run."),
                "limits": [
                    "upload success does not prove license, authorship, malware safety, or hidden-data absence"
                ],
                "links": [{
                    "label": "Flywheel",
                    "url": "https://github.com/HarperZ9/flywheel/releases/tag/v0.6.1",
                }],
            },
            "media": [{"artifact_id": artifact["artifact_id"],
                       "alt": "Cover art from the selected creative run."}],
        }
        status, proposal = post(
            "/api/gateway-grants/bulletin-media-preview", selection)
        assert status == 200, proposal
        assert proposal["schema"] == (
            "flywheel.outcome-bulletin-media-preview-response/v1")
        operation = proposal["operation"]
        proposal = proposal["proposal"]
        assert operation["schema"] == "flywheel.gateway-operation/v1"
        assert operation["action"] == proposal["action"] == "lane.call"
        assert operation["journey_ref"] == proposal["journey_ref"] == JOURNEY
        assert operation["expected_event_head"] == proposal["expected_event_head"]
        assert operation["client_request_id"] == proposal["client_request_id"]
        assert operation["operation"]["name"] == "bulletin"
        assert operation["operation"]["tool"] == proposal["tool"]
        assert operation["operation"]["data_refs"] == proposal["data_refs"]
        assert operation["operation"]["credential_refs"] == proposal[
            "credential_refs"]
        board.preview = operation["operation"]["args"]
        review = proposal["summary"]["bulletin_media_review"]
        assert review["mode"] == "artifact_share"
        assert review["attachments"][0]["media_id"] == media_id(PNG)
        assert str(source) not in json.dumps({"proposal": proposal,
                                              "operation": operation})
        status, media = post(
            "/api/gateway-grants/bulletin-media-preview-bytes",
            {"schema": "flywheel.bulletin-media-preview-bytes-request/v1",
             "proposal_ref": proposal["proposal_ref"],
             "preview_ref": review["preview_media"][0]["preview_ref"],
             "preview_sha256": review["preview_sha256"]})
        assert status == 200, media
        assert media["content_type"] == "image/png"
        assert media["cache"] == "no-store"
        assert base64.b64decode(media["body_b64"]) == PNG
        status, approval = post(
            "/api/gateway-grants/approve-once",
            {"proposal_ref": proposal["proposal_ref"]})
        assert status == 200, approval
        assert approval["grant_ref"] == proposal["planned_grant_ref"]
        final_body = {
            "schema": operation["schema"],
            "journey_ref": operation["journey_ref"],
            "expected_event_head": operation["expected_event_head"],
            "client_request_id": operation["client_request_id"],
            "grant_ref": approval["grant_ref"],
            **operation["operation"],
        }
        status, publication = post(
            "/api/lane/bulletin/board_publish_media_post", final_body)
        assert status == 200, publication
        assert publication["status"] == expected_status
        if expected_status == "posted_readback_match":
            assert publication["uploaded_media"][0]["media_id"] == media_id(PNG)
            assert len(board.posts) == 1
        else:
            assert publication["media_id"] == media_id(PNG)
            assert board.posts == []
        assert len(board.uploads) == 1
    finally:
        server.shutdown()
        thread.join(2)
        server.server_close()
        board.close()
