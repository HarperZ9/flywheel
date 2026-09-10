"""Presence-label regressions for auth status.

A non-empty credential proves only local credential presence. These tests pin
the user-visible boundary so a stored synthetic value cannot become a claimed
provider sign-in or leak the credential value.
"""
import json

import harness.oauth_signin as osi
import harness.oauth_service as svc


def _provider_line(output: str, provider: str) -> str:
    for line in output.splitlines():
        if line.strip().startswith(provider):
            return line
    raise AssertionError(f"no status line for {provider!r} in:\n{output}")


def test_cli_status_labels_presence_as_authentication_unverified(monkeypatch, capsys):
    monkeypatch.setattr(
        osi.claude_cli_auth,
        "public_status",
        lambda: {"state": "not_authenticated", "authenticated": False,
                 "cli_present": True, "executable": "claude.exe"},
    )
    monkeypatch.setattr(
        osi.keychain,
        "resolve_credential",
        lambda name: "synthetic-openrouter-token"
        if name == "OPENROUTER_API_KEY"
        else "",
    )
    monkeypatch.setattr(
        osi.keychain,
        "credential_source",
        lambda name: "keychain" if name == "OPENROUTER_API_KEY" else "absent",
    )

    assert osi.cli(["status"]) == 0

    out = capsys.readouterr().out
    openrouter = _provider_line(out, "openrouter")
    anthropic = _provider_line(out, "anthropic")
    assert "synthetic-openrouter-token" not in out
    assert "signed-in" not in openrouter
    assert "credential present; authentication unverified" in openrouter
    assert "Claude Code account not signed in" in anthropic


def test_cli_login_launches_official_tool_without_token_paste(
    monkeypatch, capsys
):
    monkeypatch.setattr(
        osi.claude_cli_auth,
        "begin_login",
        lambda **_: {"ok": True, "provider": "anthropic",
                     "mode": "official-cli",
                     "note": "finish Claude Code sign-in, then return"},
    )

    assert osi.cli(["login", "anthropic"]) == 0

    out = capsys.readouterr().out
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in out
    assert "setup-token" not in out
    assert "signed in" not in out
    assert "signed-in" not in out
    assert "official-cli" in out
    assert "finish Claude Code sign-in" in out


def test_service_reports_official_cli_account_without_metadata(monkeypatch):
    monkeypatch.setattr(
        svc.claude_cli_auth,
        "public_status",
        lambda: {"state": "authenticated", "authenticated": True,
                 "cli_present": True, "executable": "claude.exe",
                 "auth_method": "claude.ai", "api_provider": "firstParty"},
    )
    doc = svc.auth_rows()
    anthropic = next(r for r in doc["providers"] if r["provider"] == "anthropic")

    assert anthropic["kind"] == "official-cli"
    assert anthropic["kind_label"] == "Claude Code account"
    assert anthropic["present"] is True
    assert anthropic["source"] == "claude-code-account"
    dumped = json.dumps(doc)
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in dumped
    assert "secret@" not in dumped


def test_service_refuses_official_cli_token_paste_without_leaking_value():
    result = svc.submit("anthropic", "sk-ant-oat-SECRET")

    assert result["ok"] is False
    assert "Claude Code" in result["error"]
    assert "SECRET" not in json.dumps(result)


def test_failed_store_control_still_reports_not_stored(monkeypatch):
    monkeypatch.setattr(osi.keychain, "keychain_available", lambda: True)
    monkeypatch.setattr(
        osi.keychain,
        "keychain_set",
        lambda name, value: {"error": "credential store write failed"},
    )

    result = osi._store(osi.PROFILES["openrouter"], "synthetic-openrouter-token")

    dumped = json.dumps(result)
    assert result["ok"] is False
    assert "NOT stored" in result["error"]
    assert "synthetic-openrouter-token" not in dumped
