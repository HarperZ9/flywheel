"""Real grant custody with synthetic keys and network seams, never a live board."""
from dataclasses import replace
import json

import pytest

from harness import bulletin_signed_transport as transport, keychain
from harness.gateway_operation import GatewayOperationError
from harness.gateway_provider_adapter import resolve_credentials
from harness.gateway_actions import dispatch_builtin
from harness.outcome_bulletin import build_preview
from tests.test_bulletin_signed_transport import _authorized, _jwk_json, OWNER, _public_outcome
from harness.credential_handles import CredentialHandleStore

ORIGIN = "https://bulletin.zaindharper.workers.dev"
OTHER = "https://example.invalid"


def bound(tmp_path):
    key, public = _jwk_json()
    handle = CredentialHandleStore(tmp_path, keychain_get=lambda _: key).bind(
        OWNER, "BULLETIN_AGENT_JWK")
    preview = build_preview(_public_outcome())
    return _authorized(tmp_path, preview, handle.credential_ref), preview, key, public


@pytest.mark.parametrize("configured", [OTHER, "", "https://example.invalid:bad"])
def test_changed_config_after_approval_rejects_before_key_or_network(tmp_path, monkeypatch, configured):
    authorized, preview, key, _ = bound(tmp_path)
    calls = []
    monkeypatch.setenv("FLYWHEEL_BULLETIN_BASE_URL", configured)
    monkeypatch.setattr(keychain, "resolve_credential", lambda _: calls.append("key") or key)
    monkeypatch.setattr(transport, "_open_json", lambda *_a, **_k: calls.append("network"))
    with pytest.raises(GatewayOperationError):
        resolve_credentials(authorized, tmp_path)
    assert calls == []
    result = transport.publish_authorized_preview(authorized, preview, state_root=tmp_path,
        keychain_get=lambda _: calls.append("key") or key)
    assert result["status"] == "publish_unavailable"
    assert calls == []


def test_config_drift_after_key_resolution_cannot_redirect_transport(tmp_path, monkeypatch):
    authorized, _, key, _ = bound(tmp_path)
    monkeypatch.setenv("FLYWHEEL_BULLETIN_BASE_URL", ORIGIN)
    monkeypatch.setattr(keychain, "resolve_credential", lambda _: key)
    authorized = resolve_credentials(authorized, tmp_path)
    calls = []
    monkeypatch.setenv("FLYWHEEL_BULLETIN_BASE_URL", OTHER)
    monkeypatch.setattr(transport, "_open_json", lambda *_a, **_k: calls.append("network"))
    result, _ = dispatch_builtin(authorized)
    assert result["status"] == "publish_unavailable"
    assert calls == []


def test_exact_signed_transport_uses_checked_origin_even_if_key_callback_changes_config(tmp_path, monkeypatch):
    authorized, preview, key, public = bound(tmp_path)
    monkeypatch.setenv("FLYWHEEL_BULLETIN_BASE_URL", ORIGIN)
    urls = []

    def changed_key(_):
        monkeypatch.setenv("FLYWHEEL_BULLETIN_BASE_URL", OTHER)
        return key

    def network(request, _timeout, *, write):
        urls.append(request.full_url)
        if write:
            assert json.loads(request.data) == preview["post"]
            assert request.get_header("Signature")
            return {"ok": True, "post": {"id": "synthetic"}}
        return {"post": {**preview["post"], "author": transport._thumbprint(public)}}

    monkeypatch.setattr(transport, "_open_json", network)
    result = transport.publish_authorized_preview(authorized, preview, state_root=tmp_path,
        keychain_get=changed_key)
    assert result["status"] == "posted_readback_match"
    assert urls == [ORIGIN + "/v1/posts", ORIGIN + "/v1/posts/synthetic"]


def test_mismatched_preview_origin_never_resolves_key_or_sends(tmp_path, monkeypatch):
    authorized, preview, key, _ = bound(tmp_path)
    preview["target"]["bulletin_base_url"] = OTHER
    calls = []
    monkeypatch.setattr(transport, "_open_json", lambda *_a, **_k: calls.append("network"))
    result = transport.publish_authorized_preview(authorized, preview, state_root=tmp_path,
        base_url=ORIGIN, keychain_get=lambda _: calls.append("key") or key)
    assert result["status"] == "grant_binding_mismatch"
    assert calls == []
