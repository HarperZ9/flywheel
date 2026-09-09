from __future__ import annotations

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
from tests.bulletin_media_fixtures import JOURNEY, NOW, PNG, jwk_json


def test_media_http_off_denies_after_grant_before_keychain_resolution(
        tmp_path, monkeypatch):
    from harness import gateway
    from harness.gateway_auth import load_or_create_owner_ref
    import harness.keychain as keychain

    flywheel_home, run_root = tmp_path / "home", tmp_path / "runs"
    state = flywheel_home / "state"
    owner = load_or_create_owner_ref(flywheel_home)
    source = tmp_path / "source.png"
    source.write_bytes(PNG)
    store = FileBackedHarnessStore(run_root)
    run = store.create_run(kind="creative", title="policy denied art")
    artifact = store.copy_artifact(
        source, run_id=run["run_id"], label="cover art")
    head = JourneyStore(state).create(MutationCommand(
        owner, JOURNEY, None, "http-access-create-1", "intake",
        {"legacy_label": None, "goal": "publish selected artifact",
         "intake": {}, "occurred_at": NOW})).event_head_sha256
    jwk, _public = jwk_json()
    handle = CredentialHandleStore(state, keychain_get=lambda _slot: jwk).bind(
        owner, BULLETIN_KEY_SLOT)
    keychain_calls = []

    def fail_keychain(slot):
        keychain_calls.append(slot)
        raise AssertionError("Bulletin keychain must not be read")

    monkeypatch.setattr(keychain, "keychain_get", fail_keychain)
    monkeypatch.setenv("FLYWHEEL_BULLETIN_ACCESS", "off")
    monkeypatch.setenv("FLYWHEEL_BULLETIN_ALLOW_LOOPBACK", "1")
    token = "media-access-token"
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

    def post(path, body):
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}{path}",
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
        status, wrapper = post(
            "/api/gateway-grants/bulletin-media-preview", {
                "schema": "flywheel.outcome-bulletin-media-selection/v1",
                "journey_ref": JOURNEY,
                "expected_event_head": head,
                "client_request_id": "media-access-denied-1",
                "credential_ref": handle.credential_ref,
                "timeout": 20,
                "bulletin_access": "off",
                "run_id": run["run_id"],
                "destination": {"base_url": "http://127.0.0.1:1"},
                "post": {
                    "room": "findings",
                    "title": "Policy denied synth sketch",
                    "description": "A selected creative artifact.",
                    "source_attribution": "Created in a selected run.",
                    "limits": ["publication is intentionally denied here"],
                    "links": [],
                },
                "media": [{"artifact_id": artifact["artifact_id"],
                           "alt": "Policy denied cover art."}],
            })
        assert status == 200, wrapper
        operation = wrapper["operation"]
        assert operation["operation"]["bulletin_access"] == "off"
        status, approval = post("/api/gateway-grants/approve-once", {
            "proposal_ref": wrapper["proposal"]["proposal_ref"],
        })
        assert status == 200, approval
        status, denied = post(
            "/api/lane/bulletin/board_publish_media_post", {
                "schema": operation["schema"],
                "journey_ref": operation["journey_ref"],
                "expected_event_head": operation["expected_event_head"],
                "client_request_id": operation["client_request_id"],
                "grant_ref": approval["grant_ref"],
                **operation["operation"],
            })
    finally:
        server.shutdown()
        thread.join(2)
        server.server_close()

    assert status == 403, denied
    assert denied["policy"] == "flywheel.bulletin-access/v1"
    assert denied["tool"] == "board_publish_media_post"
    assert denied["credential_resolution_attempted"] is False
    assert denied["network_attempted"] is False
    assert keychain_calls == []
