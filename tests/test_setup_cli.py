"""Falsifiers for `flywheel setup`: keys go to the credential store, never to a file or the screen."""
from harness import keychain, setup_cli

SECRET = "sk-setup-test-000111222333"


def test_store_writes_the_key_to_the_credential_store(monkeypatch, capsys):
    saved = {}
    monkeypatch.setattr(keychain, "keychain_available", lambda: True)
    monkeypatch.setattr(keychain, "keychain_set", lambda n, v: saved.update({n: v}) or {"ok": True})
    ok, msg = setup_cli.store("anthropic", read_secret=lambda prompt: SECRET)
    assert ok and saved == {"ANTHROPIC_API_KEY": SECRET} and SECRET not in msg


def test_no_credential_store_means_no_file_and_an_env_hint(monkeypatch, tmp_path):
    monkeypatch.setattr(keychain, "keychain_available", lambda: False)
    asked = []
    ok, msg = setup_cli.store("openai", read_secret=lambda p: asked.append(p) or SECRET)
    assert not ok and "OPENAI_API_KEY" in msg and asked == []   # never even asked


def test_empty_key_stores_nothing(monkeypatch):
    monkeypatch.setattr(keychain, "keychain_available", lambda: True)
    monkeypatch.setattr(keychain, "keychain_set", lambda n, v: (_ for _ in ()).throw(AssertionError))
    ok, _ = setup_cli.store("gemini", read_secret=lambda p: "  ")
    assert not ok


def test_status_names_sources_and_clis(monkeypatch):
    monkeypatch.setattr(keychain, "credential_source", lambda env: "keychain"
                        if env == "ANTHROPIC_API_KEY" else "absent")
    rows = setup_cli.status(which=lambda name: "/bin/" + name if name == "claude" else None)
    text = "\n".join(rows)
    assert "ANTHROPIC_API_KEY    keychain" in text and "claude      on PATH" in text
    assert "codex       not found" in text


def test_setup_is_a_packaged_command():
    from harness import cli_entry
    assert cli_entry._PACKAGED["setup"] == "harness.setup_cli"
