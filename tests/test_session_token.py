"""Session tokens: scoped, time-bounded credential derivation."""
import time
from unittest.mock import MagicMock

import pytest


OWNER = "owner_" + "a" * 32
OTHER = "owner_" + "b" * 32


def _fake_keychain():
    store = {"OPENROUTER_API_KEY": "or-live-xxx", "OPENAI_API_KEY": "sk-yyy"}
    return lambda name: store.get(name)


def _make_handle_store(tmp_path):
    from harness.credential_handles import CredentialHandleStore
    return CredentialHandleStore(tmp_path, keychain_get=_fake_keychain())


def _make_store(tmp_path):
    from harness.session_token import SessionTokenStore
    handle_store = _make_handle_store(tmp_path)
    return SessionTokenStore(handle_store)


def test_mint_returns_token_with_expiry(tmp_path):
    from harness.session_token import SessionTokenStore
    store = _make_store(tmp_path)
    hs = store._handle_store
    h = hs.bind(OWNER, "OPENROUTER_API_KEY")
    token = store.mint(
        owner_ref=OWNER,
        session_ref="sess_001",
        credential_refs=[h.credential_ref],
        required_slots=["OPENROUTER_API_KEY"],
        ttl_seconds=900,
    )
    assert token.token_ref.startswith("stok_")
    assert token.expires_at > token.created_at
    assert token.expires_at - token.created_at == pytest.approx(900, abs=2)
    assert not token.revoked


def test_resolve_returns_bindings_within_ttl(tmp_path):
    store = _make_store(tmp_path)
    hs = store._handle_store
    h = hs.bind(OWNER, "OPENROUTER_API_KEY")
    token = store.mint(OWNER, "sess_001",
                       [h.credential_ref], ["OPENROUTER_API_KEY"], 900)
    bindings = store.resolve(token.token_ref, OWNER, "sess_001")
    assert bindings.value_for("OPENROUTER_API_KEY") == "or-live-xxx"


def test_resolve_rejects_expired_token(tmp_path):
    from harness.session_token import SessionTokenError
    store = _make_store(tmp_path)
    hs = store._handle_store
    h = hs.bind(OWNER, "OPENROUTER_API_KEY")
    token = store.mint(OWNER, "sess_001",
                       [h.credential_ref], ["OPENROUTER_API_KEY"], 0)
    time.sleep(0.05)
    with pytest.raises(SessionTokenError, match="EXPIRED"):
        store.resolve(token.token_ref, OWNER, "sess_001")


def test_resolve_rejects_wrong_session(tmp_path):
    from harness.session_token import SessionTokenError
    store = _make_store(tmp_path)
    hs = store._handle_store
    h = hs.bind(OWNER, "OPENROUTER_API_KEY")
    token = store.mint(OWNER, "sess_001",
                       [h.credential_ref], ["OPENROUTER_API_KEY"], 900)
    with pytest.raises(SessionTokenError):
        store.resolve(token.token_ref, OWNER, "sess_OTHER")


def test_resolve_rejects_wrong_owner(tmp_path):
    from harness.session_token import SessionTokenError
    store = _make_store(tmp_path)
    hs = store._handle_store
    h = hs.bind(OWNER, "OPENROUTER_API_KEY")
    token = store.mint(OWNER, "sess_001",
                       [h.credential_ref], ["OPENROUTER_API_KEY"], 900)
    with pytest.raises(SessionTokenError):
        store.resolve(token.token_ref, OTHER, "sess_001")


def test_revoke_prevents_future_resolve(tmp_path):
    from harness.session_token import SessionTokenError
    store = _make_store(tmp_path)
    hs = store._handle_store
    h = hs.bind(OWNER, "OPENROUTER_API_KEY")
    token = store.mint(OWNER, "sess_001",
                       [h.credential_ref], ["OPENROUTER_API_KEY"], 900)
    assert store.revoke(token.token_ref, OWNER)
    with pytest.raises(SessionTokenError, match="REVOKED"):
        store.resolve(token.token_ref, OWNER, "sess_001")


def test_list_active_excludes_expired_and_revoked(tmp_path):
    store = _make_store(tmp_path)
    hs = store._handle_store
    h = hs.bind(OWNER, "OPENROUTER_API_KEY")
    t1 = store.mint(OWNER, "s1", [h.credential_ref],
                    ["OPENROUTER_API_KEY"], 0)
    time.sleep(0.05)
    t2 = store.mint(OWNER, "s2", [h.credential_ref],
                    ["OPENROUTER_API_KEY"], 900)
    t3 = store.mint(OWNER, "s3", [h.credential_ref],
                    ["OPENROUTER_API_KEY"], 900)
    store.revoke(t3.token_ref, OWNER)
    active = store.list_active(OWNER)
    refs = [t.token_ref for t in active]
    assert t2.token_ref in refs
    assert t1.token_ref not in refs
    assert t3.token_ref not in refs


def test_reap_removes_expired_tokens(tmp_path):
    store = _make_store(tmp_path)
    hs = store._handle_store
    h = hs.bind(OWNER, "OPENROUTER_API_KEY")
    store.mint(OWNER, "s1", [h.credential_ref],
              ["OPENROUTER_API_KEY"], 0)
    store.mint(OWNER, "s2", [h.credential_ref],
              ["OPENROUTER_API_KEY"], 900)
    time.sleep(0.05)
    removed = store.reap()
    assert removed == 1
    assert len(store.list_active(OWNER)) == 1


def test_repr_never_contains_credential_value(tmp_path):
    store = _make_store(tmp_path)
    hs = store._handle_store
    h = hs.bind(OWNER, "OPENROUTER_API_KEY")
    token = store.mint(OWNER, "sess_001",
                       [h.credential_ref], ["OPENROUTER_API_KEY"], 900)
    assert "or-live-xxx" not in repr(token)
    assert "or-live-xxx" not in str(token)
