"""The subscription-auth seam consumes an already-authorized token and never
discloses it. These tests are hermetic: environment via monkeypatch, files via
tmp_path, and the OS credential store stubbed so a run is identical on any
platform. The load-bearing assertions are the redaction ones: no source label,
repr, or str may ever contain the token value."""

import pytest

from harness import keychain, subscription_auth as sa
from harness.subscription_auth import (
    AuthResolver,
    AuthToken,
    ChainAdapter,
    EnvTokenAdapter,
    KeychainTokenAdapter,
    TokenFileAdapter,
    default_auth_resolver,
)

_SECRET = "sk-live-DO-NOT-LEAK-abc123"


@pytest.fixture(autouse=True)
def _no_keychain(monkeypatch):
    """Default the OS store to empty so env/file cases are deterministic and a
    real machine's stored credentials cannot bleed into a test."""
    monkeypatch.setattr(keychain, "keychain_get", lambda name: None)
    for var in ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY",
                "ANTHROPIC_AUTH_TOKEN", "DASHSCOPE_API_KEY",
                "OPENROUTER_API_KEY", "MY_TOKEN"):
        monkeypatch.delenv(var, raising=False)


# ---- AuthToken ---------------------------------------------------------

def test_bearer_header_pair():
    tok = AuthToken("bearer", _SECRET, "env:MY_TOKEN")
    assert tok.header() == ("Authorization", f"Bearer {_SECRET}")


def test_x_api_key_header_pair():
    tok = AuthToken("x-api-key", _SECRET, "env:MY_TOKEN")
    assert tok.header() == ("x-api-key", _SECRET)


def test_unknown_scheme_header_raises():
    with pytest.raises(ValueError):
        AuthToken("basic", _SECRET, "env:MY_TOKEN").header()


def test_repr_and_str_redact_the_value():
    tok = AuthToken("bearer", _SECRET, "env:MY_TOKEN")
    assert _SECRET not in repr(tok)
    assert _SECRET not in str(tok)
    # the source and scheme are safe to show; a sha256 prefix identifies it
    assert "env:MY_TOKEN" in repr(tok)
    assert "sha256=" in repr(tok)


def test_expiry_judged_only_when_known():
    assert AuthToken("bearer", _SECRET, "s").expired(now=10) is False
    assert AuthToken("bearer", _SECRET, "s", expires_at=5).expired(now=10)
    assert not AuthToken("bearer", _SECRET, "s", expires_at=20).expired(now=10)


# ---- EnvTokenAdapter ---------------------------------------------------

def test_env_adapter_resolves_present_token(monkeypatch):
    monkeypatch.setenv("MY_TOKEN", _SECRET)
    tok = EnvTokenAdapter("MY_TOKEN").resolve()
    assert tok is not None
    assert tok.value == _SECRET
    assert tok.scheme == "bearer"
    assert tok.source == "env:MY_TOKEN"


def test_env_adapter_absent_is_none():
    assert EnvTokenAdapter("MY_TOKEN").resolve() is None


def test_env_adapter_source_label_is_presence_only(monkeypatch):
    monkeypatch.setenv("MY_TOKEN", _SECRET)
    label = EnvTokenAdapter("MY_TOKEN").source_label()
    assert label == "env:MY_TOKEN"
    assert _SECRET not in label
    assert EnvTokenAdapter("MY_TOKEN2").source_label() == "absent:MY_TOKEN2"


def test_env_adapter_scheme_flows_to_token(monkeypatch):
    monkeypatch.setenv("MY_TOKEN", _SECRET)
    tok = EnvTokenAdapter("MY_TOKEN", scheme="x-api-key").resolve()
    assert tok.header() == ("x-api-key", _SECRET)


# ---- KeychainTokenAdapter ----------------------------------------------

def test_keychain_adapter_resolves_present_token(monkeypatch):
    monkeypatch.setattr(keychain, "keychain_get",
                        lambda name: _SECRET if name == "KC" else None)
    tok = KeychainTokenAdapter("KC").resolve()
    assert tok is not None and tok.value == _SECRET
    assert tok.source == "keychain:KC"


def test_keychain_adapter_absent_is_none():
    assert KeychainTokenAdapter("KC").resolve() is None


def test_keychain_adapter_source_label_never_carries_value(monkeypatch):
    monkeypatch.setattr(keychain, "keychain_get",
                        lambda name: _SECRET if name == "KC" else None)
    label = KeychainTokenAdapter("KC").source_label()
    assert label == "keychain:KC"
    assert _SECRET not in label
    assert KeychainTokenAdapter("GONE").source_label() == "absent:GONE"


# ---- TokenFileAdapter --------------------------------------------------

def test_file_adapter_whole_file_text(tmp_path):
    p = tmp_path / "token.txt"
    p.write_text(f"  {_SECRET}\n", encoding="utf-8")
    tok = TokenFileAdapter(p).resolve()
    assert tok is not None and tok.value == _SECRET
    assert tok.source == f"file:{p}"


def test_file_adapter_json_field(tmp_path):
    p = tmp_path / "creds.json"
    p.write_text('{"access_token": "%s", "other": 1}' % _SECRET,
                 encoding="utf-8")
    tok = TokenFileAdapter(p, field="access_token").resolve()
    assert tok is not None and tok.value == _SECRET


def test_file_adapter_missing_file_is_none(tmp_path):
    assert TokenFileAdapter(tmp_path / "nope.txt").resolve() is None


def test_file_adapter_missing_json_field_is_none(tmp_path):
    p = tmp_path / "creds.json"
    p.write_text('{"other": 1}', encoding="utf-8")
    assert TokenFileAdapter(p, field="access_token").resolve() is None


def test_file_adapter_never_writes(tmp_path):
    p = tmp_path / "absent.txt"
    TokenFileAdapter(p).resolve()
    TokenFileAdapter(p).source_label()
    assert not p.exists()


def test_file_adapter_source_label_presence_only(tmp_path):
    p = tmp_path / "token.txt"
    p.write_text(_SECRET, encoding="utf-8")
    label = TokenFileAdapter(p).source_label()
    assert label == f"file:{p}"
    assert _SECRET not in label
    assert TokenFileAdapter(tmp_path / "gone").source_label().startswith(
        "absent:")


# ---- ChainAdapter ------------------------------------------------------

def test_chain_falls_through_to_second(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", _SECRET)
    chain = ChainAdapter([
        EnvTokenAdapter("CLAUDE_CODE_OAUTH_TOKEN", "bearer"),
        EnvTokenAdapter("ANTHROPIC_API_KEY", "x-api-key"),
    ])
    tok = chain.resolve()
    assert tok is not None and tok.value == _SECRET
    assert tok.source == "env:ANTHROPIC_API_KEY"
    assert chain.source_label() == "env:ANTHROPIC_API_KEY"


def test_chain_prefers_first_present(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oauth-tok")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "raw-key")
    chain = ChainAdapter([
        EnvTokenAdapter("CLAUDE_CODE_OAUTH_TOKEN", "bearer"),
        EnvTokenAdapter("ANTHROPIC_API_KEY", "x-api-key"),
    ])
    assert chain.resolve().value == "oauth-tok"


def test_chain_all_absent_is_none():
    chain = ChainAdapter([
        EnvTokenAdapter("CLAUDE_CODE_OAUTH_TOKEN"),
        EnvTokenAdapter("ANTHROPIC_API_KEY"),
    ])
    assert chain.resolve() is None
    assert chain.source_label() == "absent"


# ---- AuthResolver / default_auth_resolver ------------------------------

def test_default_resolver_anthropic_from_oauth_token(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _SECRET)
    r = default_auth_resolver()
    tok = r.resolve("anthropic")
    assert tok is not None and tok.value == _SECRET
    assert tok.header() == ("Authorization", f"Bearer {_SECRET}")
    assert r.source("anthropic") == "env:CLAUDE_CODE_OAUTH_TOKEN"


def test_default_resolver_openrouter(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", _SECRET)
    r = default_auth_resolver()
    assert r.resolve("openrouter").value == _SECRET


def test_default_resolver_unknown_provider_is_none_and_absent():
    r = default_auth_resolver()
    assert r.resolve("no-such-provider") is None
    assert r.source("no-such-provider") == "absent"


def test_resolver_source_never_leaks_value(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _SECRET)
    r = default_auth_resolver()
    assert _SECRET not in r.source("anthropic")


def test_resolver_register_and_providers():
    r = AuthResolver()
    r.register("x", EnvTokenAdapter("MY_TOKEN"))
    assert r.providers() == ["x"]
