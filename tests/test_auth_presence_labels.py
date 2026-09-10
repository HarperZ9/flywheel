"""Presence-label regressions for auth status.

A non-empty credential proves only local credential presence. These tests pin
the user-visible boundary so a stored synthetic value cannot become a claimed
provider sign-in or leak the credential value.
"""
import json

import harness.oauth_signin as osi


def _provider_line(output: str, provider: str) -> str:
    for line in output.splitlines():
        if line.strip().startswith(provider):
            return line
    raise AssertionError(f"no status line for {provider!r} in:\n{output}")


def test_cli_status_labels_presence_as_authentication_unverified(monkeypatch, capsys):
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
    assert "absent" in anthropic


def test_cli_successful_store_feedback_does_not_claim_signed_in(
    monkeypatch, capsys
):
    written = {}
    monkeypatch.setattr(osi.keychain, "keychain_available", lambda: True)
    monkeypatch.setattr(
        osi.keychain,
        "keychain_set",
        lambda name, value: written.update({name: value}) or {"stored": name},
    )

    def _synthetic_prompt(_prompt: str) -> str:
        return "sk-ant-oat-synthetic-credential"

    monkeypatch.setattr("getpass.getpass", _synthetic_prompt)

    assert osi.cli(["login", "anthropic"]) == 0

    out = capsys.readouterr().out
    assert written == {"CLAUDE_CODE_OAUTH_TOKEN": "sk-ant-oat-synthetic-credential"}
    assert "sk-ant-oat-synthetic-credential" not in out
    assert "signed in" not in out
    assert "signed-in" not in out
    assert (
        "credential stored CLAUDE_CODE_OAUTH_TOKEN; authentication unverified"
        in out
    )


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
