import json
from types import SimpleNamespace

import pytest

from harness import endpoint_registry, endpoints, gateway
from harness.endpoints import CliBackend
from harness.local_agent import BackendError


def _logged_in_status(_argv, _timeout):
    return SimpleNamespace(
        returncode=0,
        stdout=json.dumps({
            "loggedIn": True,
            "authMethod": "claude.ai",
            "apiProvider": "firstParty",
        }),
        stderr="SECRET",
    )


def _claude_row(**extra):
    row = {
        "name": "claude-cli",
        "credential": "cli-auth",
        "account_authenticated": False,
        "account_state": "not_authenticated",
        "receipt_capable": False,
    }
    row.update(extra)
    return row


def test_route_request_refuses_unauthenticated_claude_before_proposer(monkeypatch):
    monkeypatch.setattr(gateway, "_unified_roster", lambda: {
        "endpoints": [_claude_row()],
        "usable_names": [],
    })

    def forbidden(*_args, **_kwargs):
        raise AssertionError("proposer factory must not run")

    monkeypatch.setattr(endpoint_registry, "make_endpoint_proposer", forbidden)

    body, code = gateway.route_request("hello", "claude-cli")

    assert code == 403
    assert "Claude Code account" in body["error"]
    assert body["account_state"] == "not_authenticated"


def test_resolve_proposer_refuses_not_usable_claude_before_factory(monkeypatch):
    monkeypatch.setattr(gateway, "_unified_roster", lambda: {
        "endpoints": [_claude_row(account_authenticated=True,
                                  account_state="authenticated")],
        "usable_names": [],
    })

    def forbidden(*_args, **_kwargs):
        raise AssertionError("proposer factory must not run")

    monkeypatch.setattr(endpoint_registry, "make_endpoint_proposer", forbidden)

    proposer, err, code = gateway._resolve_proposer("claude-cli", "http://x")

    assert proposer is None
    assert code == 403
    assert "Claude Code account" in err


def test_claude_generation_uses_authenticated_resolved_executable(monkeypatch):
    monkeypatch.setattr(endpoints, "build_endpoints",
                        lambda **_: [CliBackend(
                            "claude-plan",
                            ["claude.exe", "-p", "{prompt}", "--model", "{model}"],
                            "claude-sonnet-5",
                        )])
    monkeypatch.setattr(endpoint_registry.claude_cli_auth, "_run_status",
                        _logged_in_status)
    monkeypatch.setattr(endpoint_registry.claude_cli_auth, "resolve_official_cli",
                        lambda **_: {
                            "ok": True,
                            "state": "available",
                            "cli_present": True,
                            "path": "C:/official/claude.exe",
                            "executable": "claude.exe",
                            "identity": "same",
                        })

    proposer = endpoint_registry.make_endpoint_proposer("claude-cli", extract=False)
    commands = []
    proposer.backend.runner = lambda cmd: commands.append(cmd) or (0, "ok", "")
    out = proposer.generate("hello", seed=0, temperature=0, max_new_tokens=8)

    assert out.text == "ok"
    assert proposer.backend.argv[0] == "C:/official/claude.exe"
    assert commands[0][0] == "C:/official/claude.exe"


def test_claude_generation_refuses_identity_drift_before_prompt(monkeypatch):
    monkeypatch.setattr(endpoints, "build_endpoints",
                        lambda **_: [CliBackend(
                            "claude-plan",
                            ["claude.exe", "-p", "{prompt}", "--model", "{model}"],
                            "claude-sonnet-5",
                        )])
    identities = iter(["first", "second"])

    def resolver(**_kwargs):
        return {
            "ok": True,
            "state": "available",
            "cli_present": True,
            "path": "C:/official/claude.exe",
            "executable": "claude.exe",
            "identity": next(identities),
        }

    monkeypatch.setattr(endpoint_registry.claude_cli_auth, "_run_status",
                        _logged_in_status)
    monkeypatch.setattr(endpoint_registry.claude_cli_auth, "resolve_official_cli",
                        resolver)

    proposer = endpoint_registry.make_endpoint_proposer("claude-cli", extract=False)
    commands = []
    proposer.backend.runner = lambda cmd: commands.append(cmd) or (0, "ok", "")

    with pytest.raises(BackendError, match="executable changed"):
        proposer.generate("hello", seed=0, temperature=0, max_new_tokens=8)

    assert commands == []
