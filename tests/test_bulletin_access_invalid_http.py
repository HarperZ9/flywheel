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
from harness.outcome_bulletin import build_gateway_grant_request, build_preview
from tests.bulletin_media_fixtures import JOURNEY, NOW, PNG, jwk_json


CANARY = "BULLETIN_SECRET_CANARY_461907"
BAD_MODE = "metadata\x07" + CANARY


def _serve(tmp_path, monkeypatch):
    from harness import gateway
    from harness.gateway_auth import load_or_create_owner_ref

    token, home = "invalid-access-token", tmp_path / "home"
    owner = load_or_create_owner_ref(home)
    monkeypatch.setenv("FLYWHEEL_BULLETIN_ACCESS", BAD_MODE)
    monkeypatch.setenv("FLYWHEEL_BULLETIN_ALLOW_LOOPBACK", "1")
    monkeypatch.setattr(gateway._Handler, "root", tmp_path, raising=False)
    monkeypatch.setattr(gateway._Handler, "run_root", str(tmp_path / "runs"),
                        raising=False)
    monkeypatch.setattr(gateway._Handler, "flywheel_home", home, raising=False)
    monkeypatch.setattr(gateway._Handler, "auth_token", token, raising=False)
    monkeypatch.setattr(gateway._Handler, "allowed_hosts",
                        gateway.DEFAULT_HOSTS, raising=False)
    monkeypatch.setattr(gateway._Handler, "clock", staticmethod(lambda: NOW),
                        raising=False)
    server = ThreadingHTTPServer(("127.0.0.1", 0), gateway._Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return owner, home / "state", token, server, thread


def _post(server, token, path, body):
    req = urllib.request.Request(
        f"http://127.0.0.1:{server.server_address[1]}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {token}"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw), raw
    except urllib.error.HTTPError as response:
        raw = response.read().decode()
        return response.code, json.loads(raw), raw


def _journey(state, owner, suffix):
    return JourneyStore(state).create(MutationCommand(
        owner, JOURNEY, None, f"invalid-access-{suffix}", "intake",
        {"legacy_label": None, "goal": "Bulletin exposure denial",
         "intake": {}, "occurred_at": NOW})).event_head_sha256


def _approve(server, token, journey_ref, head, request_id, operation):
    status, proposal, _raw = _post(
        server, token, "/api/gateway-grants/prepare/lane.call", {
            "schema": "flywheel.gateway-operation/v1",
            "journey_ref": journey_ref,
            "expected_event_head": head,
            "client_request_id": request_id,
            "operation": operation,
        })
    assert status == 200, proposal
    status, approval, _raw = _post(
        server, token, "/api/gateway-grants/approve-once",
        {"proposal_ref": proposal["proposal_ref"]})
    assert status == 200, approval
    return approval["grant_ref"]


def _assert_invalid_denial(payload, raw, tool):
    assert payload["schema"] == "flywheel.bulletin-access-denial/v1"
    assert payload["governance_denied"] is True
    assert payload["policy_error"] == "invalid_ceiling"
    assert payload["bulletin_access_ceiling"] == "invalid"
    assert payload["bulletin_access"] == "off"
    assert payload["tool"] == tool
    assert payload["network_attempted"] is False
    assert payload["credential_resolution_attempted"] is False
    assert CANARY not in raw
    assert CANARY.lower() not in raw.lower()
    assert "\\u0007" not in raw and "\x07" not in raw


def test_http_lane_grant_invalid_env_label_is_sanitized_before_transport(
        tmp_path, monkeypatch):
    import harness.lanes as lanes
    import harness.mcp_client as mcp_client

    calls = []
    monkeypatch.setattr(lanes, "resolve_mcp_launch",
                        lambda name: calls.append(name) or ["mcp", name],
                        raising=False)
    monkeypatch.setattr(mcp_client, "MCPClient", object)
    owner, state, token, server, thread = _serve(tmp_path, monkeypatch)
    try:
        head = _journey(state, owner, "read")
        operation = {"name": "bulletin", "tool": "board_feed", "args": {},
                     "governance_tier": "T1", "data_refs": [],
                     "credential_refs": []}
        grant = _approve(server, token, JOURNEY, head, "invalid-read", operation)
        status, payload, raw = _post(
            server, token, "/api/lane/bulletin/board_feed", {
                "schema": "flywheel.gateway-operation/v1",
                "journey_ref": JOURNEY,
                "expected_event_head": head,
                "client_request_id": "invalid-read",
                "grant_ref": grant,
                **operation,
            })
    finally:
        server.shutdown(); thread.join(2); server.server_close()
    assert status == 403, payload
    _assert_invalid_denial(payload, raw, "board_feed")
    assert calls == []


def test_native_plain_post_invalid_env_denies_before_keychain(tmp_path,
                                                              monkeypatch):
    import harness.keychain as keychain

    jwk, _public = jwk_json()
    owner, state, token, server, thread = _serve(tmp_path, monkeypatch)
    handle = CredentialHandleStore(state, keychain_get=lambda _slot: jwk).bind(
        owner, BULLETIN_KEY_SLOT)
    keychain_calls = []
    monkeypatch.setattr(
        keychain, "keychain_get",
        lambda slot: keychain_calls.append(slot) or (_ for _ in ()).throw(
            AssertionError("keychain must not be read")))
    try:
        head = _journey(state, owner, "plain")
        preview = build_preview({
            "schema": "flywheel.outcome-bulletin-request/v1",
            "title": "Denied plain post",
            "status": "This post is valid but policy-denied.",
            "room": "findings",
            "checked": ["The denial path is under test."],
            "positive_controls": ["A keychain spy is installed."],
            "held_blockers": ["The policy intentionally blocks transport."],
            "does_not_prove": ["A live Bulletin write occurred."],
            "links": [{
                "label": "Flywheel",
                "url": "https://github.com/HarperZ9/flywheel",
            }],
        })
        request = build_gateway_grant_request(
            preview, journey_ref=JOURNEY, expected_event_head=head,
            client_request_id="invalid-plain", credential_ref=handle.credential_ref)
        operation = request["operation"]
        grant = _approve(server, token, JOURNEY, head, "invalid-plain", operation)
        status, payload, raw = _post(
            server, token, "/api/lane/bulletin/board_write_post", {
                "schema": "flywheel.gateway-operation/v1",
                "journey_ref": JOURNEY,
                "expected_event_head": head,
                "client_request_id": "invalid-plain",
                "grant_ref": grant,
                **operation,
            })
    finally:
        server.shutdown(); thread.join(2); server.server_close()
    assert status == 403, payload
    _assert_invalid_denial(payload, raw, "board_write_post")
    assert keychain_calls == []


def test_native_media_invalid_env_denies_before_keychain_or_upload(
        tmp_path, monkeypatch):
    import harness.keychain as keychain

    jwk, _public = jwk_json()
    owner, state, token, server, thread = _serve(tmp_path, monkeypatch)
    run_root = tmp_path / "runs"
    source = tmp_path / "source.png"
    source.write_bytes(PNG)
    store = FileBackedHarnessStore(run_root)
    run = store.create_run(kind="creative", title="invalid mode media")
    artifact = store.copy_artifact(source, run_id=run["run_id"], label="cover")
    handle = CredentialHandleStore(state, keychain_get=lambda _slot: jwk).bind(
        owner, BULLETIN_KEY_SLOT)
    keychain_calls = []
    monkeypatch.setattr(
        keychain, "keychain_get",
        lambda slot: keychain_calls.append(slot) or (_ for _ in ()).throw(
            AssertionError("keychain must not be read")))
    try:
        head = _journey(state, owner, "media")
        status, wrapper, _raw = _post(
            server, token, "/api/gateway-grants/bulletin-media-preview", {
                "schema": "flywheel.outcome-bulletin-media-selection/v1",
                "journey_ref": JOURNEY,
                "expected_event_head": head,
                "client_request_id": "invalid-media",
                "credential_ref": handle.credential_ref,
                "bulletin_access": "full",
                "run_id": run["run_id"],
                "destination": {"base_url": "http://127.0.0.1:1"},
                "post": {
                    "room": "findings",
                    "title": "Denied media post",
                    "description": "A valid selected creative artifact.",
                    "source_attribution": "Created in a selected run.",
                    "limits": ["This fixture intentionally stops before upload."],
                    "links": [],
                },
                "media": [{"artifact_id": artifact["artifact_id"],
                           "alt": "Selected cover art."}],
            })
        assert status == 200, wrapper
        operation = wrapper["operation"]["operation"]
        assert operation["bulletin_access"] == "full"
        status, approval, _raw = _post(
            server, token, "/api/gateway-grants/approve-once",
            {"proposal_ref": wrapper["proposal"]["proposal_ref"]})
        assert status == 200, approval
        status, payload, raw = _post(
            server, token, "/api/lane/bulletin/board_publish_media_post", {
                "schema": "flywheel.gateway-operation/v1",
                "journey_ref": JOURNEY,
                "expected_event_head": head,
                "client_request_id": "invalid-media",
                "grant_ref": approval["grant_ref"],
                **operation,
            })
    finally:
        server.shutdown(); thread.join(2); server.server_close()
    assert status == 403, payload
    _assert_invalid_denial(payload, raw, "board_publish_media_post")
    assert keychain_calls == []
