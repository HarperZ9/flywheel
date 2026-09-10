"""Reply destination and readback controls for the native publication path."""
from copy import deepcopy
import json

import pytest

from harness.bulletin_readback import post_matches
from harness.bulletin_origin import PUBLIC_BULLETIN_ORIGIN
from harness.evidence_public import TransportError
from harness.gateway_operation import AuthorizedOperation
from harness.outcome_bulletin import build_preview, OutcomeBulletinError
from harness.outcome_bulletin_gateway import preview_from_authorized_operation
from tests.test_bulletin_signed_transport import _public_outcome

PARENT = "1788991200000-abcdefgh"


def _authorized(post, *, bulletin_base_url=PUBLIC_BULLETIN_ORIGIN):
    return AuthorizedOperation.for_test(
        action="lane.call", operation={"name": "bulletin",
        "tool": "board_write_post", "args": post, "governance_tier": "T2",
        "bulletin_base_url": bulletin_base_url, "timeout": 20,
        "data_refs": [], "credential_refs": []},
        scopes=("exec", "network", "plugin"))


def test_reply_projection_matches_native_gateway_preview():
    outcome = {**_public_outcome(), "parent_id": PARENT}
    preview = build_preview(outcome)
    native = preview_from_authorized_operation(_authorized(preview["post"]))
    assert native["post"]["parent_id"] == PARENT
    assert native["post_payload_sha256"] == preview["post_payload_sha256"]
    root = build_preview(_public_outcome())
    assert root["body_sha256"] == preview["body_sha256"]
    assert root["post_payload_sha256"] != preview["post_payload_sha256"]


@pytest.mark.parametrize("parent", [None, "", " ", "../private", "x\n", 1, True, "x" * 129])
def test_explicit_invalid_parent_is_rejected_never_dropped(parent):
    with pytest.raises(OutcomeBulletinError):
        build_preview({**_public_outcome(), "parent_id": parent})
    with pytest.raises(TransportError):
        preview_from_authorized_operation(_authorized(
            {"room": "findings", "body": "reply", "parent_id": parent}))


@pytest.mark.parametrize("parent", [None, "other-parent", ""])
def test_readback_cannot_turn_reply_into_root_or_another_thread(parent):
    expected = {"room": "findings", "body": "reply", "parent_id": PARENT}
    seen = {**expected, "parent_id": parent}
    assert not post_matches(seen, expected)
    seen.pop("parent_id")
    assert not post_matches(seen, expected)
    assert post_matches(deepcopy(expected), expected)


def test_root_readback_cannot_be_a_reply():
    root = {"room": "findings", "body": "root"}
    assert post_matches(root, root)
    assert post_matches({**root, "parent_id": None}, root)
    assert not post_matches({**root, "parent_id": PARENT}, root)


@pytest.mark.parametrize("mode", ["ok", "missing_author", "wrong_author"])
def test_signed_reply_readback_binds_signing_actor(tmp_path, mode):
    from harness.bulletin_signed_transport import (
        BULLETIN_KEY_SLOT, publish_authorized_preview)
    from harness.credential_handles import CredentialHandleStore
    from tests.test_bulletin_signed_transport import (
        OWNER, BulletinServer, _authorized as grant, _jwk_json)
    key, public = _jwk_json()
    board = BulletinServer(public, mode=mode)
    try:
        store = CredentialHandleStore(tmp_path, keychain_get=lambda _: key)
        handle = store.bind(OWNER, BULLETIN_KEY_SLOT)
        preview = build_preview(
            {**_public_outcome(), "parent_id": PARENT},
            bulletin_base_url=board.url, allow_loopback=True)
        authorized = grant(tmp_path, preview, handle.credential_ref)
        result = publish_authorized_preview(
            authorized, preview, state_root=tmp_path,
            keychain_get=lambda _: key, base_url=board.url, allow_loopback=True)
        assert len(board.posts) == 1
        assert board.posts[0]["parent_id"] == PARENT
    finally:
        board.close()
    assert result["status"] == (
        "posted_readback_match" if mode == "ok" else "posted_readback_drift")


@pytest.mark.parametrize("allow", ["", "0", "1"])
def test_gateway_local_board_requires_explicit_existing_loopback_flag(
        tmp_path, monkeypatch, allow):
    from harness.gateway_operation import GatewayOperationError
    from harness.gateway_provider_adapter import resolve_credentials
    from tests.test_bulletin_signed_transport_review import _authorized_with_handle
    from harness import keychain
    origin = "http://127.0.0.1:8787"
    authorized, _, key = _authorized_with_handle(
        tmp_path, bulletin_base_url=origin, allow_loopback=True)
    calls = []
    monkeypatch.setattr(keychain, "keychain_get", lambda slot: calls.append(slot) or key)
    monkeypatch.setenv("FLYWHEEL_BULLETIN_BASE_URL", origin)
    monkeypatch.setenv("FLYWHEEL_BULLETIN_ALLOW_LOOPBACK", allow)
    if allow == "1":
        assert resolve_credentials(authorized, tmp_path).credential_bindings
        assert calls == ["BULLETIN_AGENT_JWK"]
    else:
        with pytest.raises(GatewayOperationError):
            resolve_credentials(authorized, tmp_path)
        assert calls == []


@pytest.mark.parametrize("changed, expected_status, expected_code", [
    ("parent_id", 403, "PERMISSION_DENIED"),
    ("room", 403, "PERMISSION_DENIED"),
    ("body", 403, "PERMISSION_DENIED"),
    ("journey", 403, "PERMISSION_REQUIRED"),
    ("request", 403, "PERMISSION_DENIED"),
    ("bulletin_base_url", 403, "PERMISSION_DENIED"),
    ("missing_bulletin_base_url", 422, "BULLETIN_ORIGIN_REQUIRED"),
])
def test_changed_reply_grant_denied_before_resolver_or_dispatch(
        tmp_path, monkeypatch, changed, expected_status, expected_code):
    from harness.credential_handles import CredentialHandleStore
    from harness.gateway_grant_route import gateway_grant_post
    from harness.outcome_bulletin import (
        build_gateway_grant_request, build_gateway_publish_envelope)
    from tests.test_gateway_action_failures import _handler_post
    from tests.test_bulletin_signed_transport import (
        OWNER, JOURNEY, NOW, _jwk_json, _journey, _approve)
    state = tmp_path / "state"
    key, _ = _jwk_json()
    handle = CredentialHandleStore(state, keychain_get=lambda _: key).bind(
        OWNER, "BULLETIN_AGENT_JWK")
    head = _journey(state).event_head_sha256
    preview = build_preview({**_public_outcome(), "parent_id": PARENT})
    request = build_gateway_grant_request(preview, journey_ref=JOURNEY,
        expected_event_head=head, client_request_id="reply-1",
        credential_ref=handle.credential_ref)
    proposal, status = gateway_grant_post(
        "/api/gateway-grants/prepare/lane.call", json.dumps(request).encode(),
        owner_ref=OWNER, state_root=state, clock=lambda: NOW)
    assert status == 200
    approval, status = _approve(state, proposal)
    assert status == 200
    final = build_gateway_publish_envelope(preview, journey_ref=JOURNEY,
        expected_event_head=head, client_request_id="reply-1",
        grant_ref=approval["grant_ref"], credential_ref=handle.credential_ref)
    if changed == "journey":
        final["journey_ref"] = "jrn_" + "b" * 32
    elif changed == "request":
        final["client_request_id"] = "different-task"
    elif changed == "bulletin_base_url":
        final["bulletin_base_url"] = "https://example.invalid"
    elif changed == "missing_bulletin_base_url":
        del final["bulletin_base_url"]
    else:
        final["args"] = {**final["args"], changed: "different"}
    calls = []
    monkeypatch.setattr("harness.gateway_provider_adapter.resolve_credentials",
        lambda *_: calls.append("credentials") or pytest.fail("credential resolution"))
    monkeypatch.setattr("harness.gateway_actions.dispatch_builtin",
        lambda *_: calls.append("dispatch") or pytest.fail("dispatch"))
    status, result = _handler_post(tmp_path,
        "/api/lane/bulletin/board_write_post", OWNER, NOW, final)
    assert status == expected_status
    assert result["error"]["code"] == expected_code
    assert calls == []
