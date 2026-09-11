import json

import harness.oauth_service as svc


def test_auth_rows_can_request_chatgpt_execution_readiness(monkeypatch):
    seen = {}

    def fake_status():
        return [{"provider": "openai", "kind": "official-app-server",
                 "keychain_name": "", "present": False,
                 "source": "codex-app-server", "sanction": "test",
                 "official_app_server": {"authenticated": False}}]

    monkeypatch.setattr(svc.oauth_signin, "status", fake_status)
    monkeypatch.setattr(
        svc.codex_app_server_auth,
        "public_status",
        lambda **kwargs: seen.update(kwargs) or {
            "authenticated": True,
            "source": "codex-app-server",
            "route_ready": True,
            "route_ready_reason": "codex_exec_help_ok",
            "run_ready": True,
            "run_ready_reason": "codex_exec_help_ok",
        },
    )
    doc = svc.auth_rows(check_execution=True)
    row = doc["providers"][0]

    assert seen["check_execution"] is True
    assert row["present"] is True
    assert row["official_app_server"]["route_ready"] is True
    assert "argv_prefix" not in json.dumps(doc)
