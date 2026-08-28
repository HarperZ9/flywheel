"""Session token HTTP routes: mint, list, revoke."""
import json
import pytest

# operation_grants.OWNER_REF_PATTERN requires "owner_" + exactly 32 hex
# chars; pad the brief's readable stem out to the required length.
OWNER = "owner_" + "abc123def456" + "0" * 20


def _fake_keychain():
    return {"OPENROUTER_API_KEY": "or-live-xxx"}.get


def _make_stores(tmp_path):
    from harness.credential_handles import CredentialHandleStore
    from harness.session_token import SessionTokenStore
    hs = CredentialHandleStore(tmp_path, keychain_get=_fake_keychain())
    return hs, SessionTokenStore(hs)


def test_mint_returns_token_ref(tmp_path):
    from harness.session_token_route import session_token_post
    hs, ts = _make_stores(tmp_path)
    h = hs.bind(OWNER, "OPENROUTER_API_KEY")
    body, status = session_token_post(
        "mint",
        {"credential_refs": [h.credential_ref],
         "required_slots": ["OPENROUTER_API_KEY"],
         "session_ref": "sess_001", "ttl_seconds": 900},
        owner_ref=OWNER, token_store=ts)
    assert status == 200
    assert body["ok"]
    assert body["token_ref"].startswith("stok_")
    assert "expires_at" in body


def test_list_returns_active_tokens(tmp_path):
    from harness.session_token_route import session_token_get
    hs, ts = _make_stores(tmp_path)
    h = hs.bind(OWNER, "OPENROUTER_API_KEY")
    ts.mint(OWNER, "s1", [h.credential_ref],
            ["OPENROUTER_API_KEY"], 900)
    body, status = session_token_get(
        owner_ref=OWNER, token_store=ts)
    assert status == 200
    assert len(body["tokens"]) == 1
    assert "or-live-xxx" not in json.dumps(body)


def test_revoke_succeeds(tmp_path):
    from harness.session_token_route import session_token_post
    hs, ts = _make_stores(tmp_path)
    h = hs.bind(OWNER, "OPENROUTER_API_KEY")
    token = ts.mint(OWNER, "s1", [h.credential_ref],
                    ["OPENROUTER_API_KEY"], 900)
    body, status = session_token_post(
        "revoke", {"token_ref": token.token_ref},
        owner_ref=OWNER, token_store=ts)
    assert status == 200
    assert body["ok"]


def test_mint_rejects_missing_fields(tmp_path):
    from harness.session_token_route import session_token_post
    _, ts = _make_stores(tmp_path)
    body, status = session_token_post(
        "mint", {}, owner_ref=OWNER, token_store=ts)
    assert status == 400
