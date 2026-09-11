from harness import endpoint_registry


def _cli_present(monkeypatch):
    monkeypatch.setattr(endpoint_registry.shutil, "which",
                        lambda binary: f"/usr/bin/{binary}")
    monkeypatch.setattr(
        endpoint_registry.claude_cli_auth,
        "public_status",
        lambda: {"state": "authenticated", "authenticated": True,
                 "cli_present": True, "executable": "claude.exe"},
    )


def test_codex_cli_binary_without_chatgpt_account_is_not_usable(monkeypatch):
    _cli_present(monkeypatch)
    monkeypatch.setattr(
        endpoint_registry.codex_app_server_auth,
        "public_status",
        lambda: {"state": "not_authenticated", "authenticated": False,
                 "account_state": "not_authenticated", "cli_present": True,
                 "executable": "node.exe", "route_ready": False,
                 "run_ready": False,
                 "supervised_run_ready": False},
    )

    roster = endpoint_registry.unified_roster()
    row = next(e for e in roster["endpoints"] if e["name"] == "codex-cli")

    assert row["credential"] == "cli-auth"
    assert row["account_authenticated"] is False
    assert row["account_state"] == "not_authenticated"
    assert row["route_ready"] is False
    assert row["run_ready"] is False
    assert row["supervised_run_ready"] is False
    assert row["receipt_capable"] is False
    assert "codex-cli" not in roster["usable_names"]


def test_codex_chatgpt_account_connected_is_not_supervised_run_ready(monkeypatch):
    _cli_present(monkeypatch)
    monkeypatch.setattr(
        endpoint_registry.codex_app_server_auth,
        "public_status",
        lambda: {"state": "authenticated", "account_state": "authenticated",
                 "authenticated": True, "cli_present": True,
                 "executable": "node.exe", "plan_type": "pro",
                 "route_ready": False, "route_ready_reason": "not_checked",
                 "run_ready": False, "run_ready_reason": "not_checked",
                 "readiness_check_available": True,
                 "supervised_run_ready": False},
    )

    roster = endpoint_registry.unified_roster()
    row = next(e for e in roster["endpoints"] if e["name"] == "codex-cli")

    assert row["account_authenticated"] is True
    assert row["plan_type"] == "pro"
    assert row["route_ready"] is False
    assert row["route_ready_reason"] == "not_checked"
    assert row["run_ready"] is False
    assert row["run_ready_reason"] == "not_checked"
    assert row["supervised_run_ready"] is False
    assert row["receipt_capable"] is False
    assert "codex-cli" not in roster["usable_names"]


def test_codex_cli_is_usable_only_after_account_and_execution_are_ready(monkeypatch):
    _cli_present(monkeypatch)
    monkeypatch.setattr(
        endpoint_registry.codex_app_server_auth,
        "public_status",
        lambda: {"state": "authenticated", "account_state": "authenticated",
                 "authenticated": True, "cli_present": True,
                 "executable": "node.exe", "route_ready": True,
                 "run_ready": True,
                 "supervised_run_ready": False},
    )

    roster = endpoint_registry.unified_roster()
    row = next(e for e in roster["endpoints"] if e["name"] == "codex-cli")

    assert row["receipt_capable"] is True
    assert row["route_ready"] is True
    assert "codex-cli" in roster["usable_names"]
