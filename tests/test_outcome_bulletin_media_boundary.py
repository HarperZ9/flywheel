from dataclasses import replace
from types import SimpleNamespace

import pytest

from harness import bulletin_signed_transport as transport
from harness.credential_handles import CredentialBindings, CredentialHandleStore
from harness.evidence_public import TransportError
from harness.outcome_bulletin import build_preview
from harness.outcome_bulletin_gateway import preview_from_authorized_operation
from tests.test_bulletin_signed_transport import (
    OWNER, POST_ID, _authorized, _jwk_json, _public_outcome,
)


MEDIA = {"media_id": "a" * 43, "alt": "A diagram of the reviewed workflow."}


def _auth(root, preview):
    jwk, _ = _jwk_json()
    handle = CredentialHandleStore(root, keychain_get=lambda _: jwk).bind(
        OWNER, transport.BULLETIN_KEY_SLOT)
    return _authorized(root, preview, handle.credential_ref), jwk


@pytest.mark.parametrize("alt", [
    "C:/Users/Synthetic/private-demo.txt",
    "owner_" + "a" * 32,
    "cred_" + "a" * 32,
    "https://private.example/review",
])
def test_gateway_attachment_text_has_the_same_public_boundary_as_body(alt):
    operation = {"args": {"room": "findings", "body": "Public result.",
                          "attachments": [{**MEDIA, "alt": alt}]}}
    with pytest.raises(TransportError):
        preview_from_authorized_operation(SimpleNamespace(operation=operation))


def test_frozen_authorized_attachment_payload_can_be_sent_exactly(tmp_path, monkeypatch):
    outcome = {**_public_outcome(), "attachments": [MEDIA]}
    preview = build_preview(outcome)
    auth, jwk = _auth(tmp_path, preview)
    sent = []

    def send(_self, path, post):
        sent.append((path, post))
        return {"ok": True, "post": {"id": POST_ID}}

    monkeypatch.setattr(transport._SignedClient, "post_json", send)
    monkeypatch.setattr(transport, "_read_json", lambda *_: {
        "post": {**preview["post"], "author": transport._parse_key(jwk)["thumbprint"], "attachments": [
            {**MEDIA, "kind": "image", "url": "/v1/media/" + MEDIA["media_id"]}]}})
    result = transport.publish_authorized_preview(
        auth, preview, state_root=tmp_path,
        credential_bindings=CredentialBindings({transport.BULLETIN_KEY_SLOT: jwk}),
        base_url=preview["target"]["bulletin_base_url"])
    assert result["status"] == "posted_readback_match"
    assert sent == [("/v1/posts", preview["post"])]


@pytest.mark.parametrize("returned", [
    [], [{**MEDIA, "media_id": "b" * 43}], [{**MEDIA, "alt": "Changed"}],
    [MEDIA, MEDIA], None,
])
def test_attachment_readback_drift_never_reports_match(tmp_path, monkeypatch, returned):
    preview = build_preview({**_public_outcome(), "attachments": [MEDIA]})
    auth, jwk = _auth(tmp_path, preview)
    # Exercise readback independently of the frozen-container binding regression.
    auth = replace(auth, operation={**dict(auth.operation), "args": preview["post"]})
    monkeypatch.setattr(transport._SignedClient, "post_json", lambda *_: {
        "ok": True, "post": {"id": POST_ID}})
    monkeypatch.setattr(transport, "_read_json", lambda *_: {
        "post": {**preview["post"], "author": transport._parse_key(jwk)["thumbprint"],
                 "attachments": returned}})
    result = transport.publish_authorized_preview(
        auth, preview, state_root=tmp_path,
        credential_bindings=CredentialBindings({transport.BULLETIN_KEY_SLOT: jwk}),
        base_url=preview["target"]["bulletin_base_url"])
    assert result["status"] == "posted_readback_drift"


def test_unexpected_attachment_on_plain_post_is_drift(tmp_path, monkeypatch):
    preview = build_preview(_public_outcome())
    auth, jwk = _auth(tmp_path, preview)
    monkeypatch.setattr(transport._SignedClient, "post_json", lambda *_: {
        "ok": True, "post": {"id": POST_ID}})
    monkeypatch.setattr(transport, "_read_json", lambda *_: {
        "post": {**preview["post"], "author": transport._parse_key(jwk)["thumbprint"],
                 "attachments": [MEDIA]}})
    result = transport.publish_authorized_preview(
        auth, preview, state_root=tmp_path,
        credential_bindings=CredentialBindings({transport.BULLETIN_KEY_SLOT: jwk}),
        base_url=preview["target"]["bulletin_base_url"])
    assert result["status"] == "posted_readback_drift"


@pytest.mark.parametrize("returned", [[], [{**MEDIA, "alt": "Changed"}], None])
def test_injected_publication_seam_also_checks_attachments(returned):
    from harness.outcome_bulletin import publish_preview
    preview = build_preview({**_public_outcome(), "attachments": [MEDIA]})
    result = publish_preview(
        preview, grant_ref="gnt_" + "c" * 32,
        publisher=lambda *a, **k: {"ok": True, "post": {"id": POST_ID}},
        readback=lambda _: {"post": {**preview["post"], "attachments": returned}})
    assert result["status"] == "posted_readback_drift"


def test_attachment_change_after_authorization_cannot_resolve_credentials(tmp_path):
    preview = build_preview({**_public_outcome(), "attachments": [MEDIA]})
    auth, _ = _auth(tmp_path, preview)
    preview["post"]["attachments"][0]["alt"] = "Unapproved replacement"
    calls = []
    result = transport.publish_authorized_preview(
        auth, preview, state_root=tmp_path, keychain_get=lambda key: calls.append(key))
    assert result["status"] == "grant_binding_mismatch"
    assert calls == []
