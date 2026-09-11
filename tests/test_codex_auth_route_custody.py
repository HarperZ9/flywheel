from harness import endpoint_registry, gateway


def _codex_row(**extra):
    row = {
        "name": "codex-cli",
        "credential": "cli-auth",
        "account_authenticated": False,
        "account_state": "not_authenticated",
        "route_ready": False,
        "route_ready_reason": "not_authenticated",
        "run_ready": False,
        "run_ready_reason": "not_authenticated",
        "supervised_run_ready": False,
        "receipt_capable": False,
    }
    row.update(extra)
    return row


def test_route_request_refuses_unauthenticated_codex_before_proposer(monkeypatch):
    monkeypatch.setattr(gateway, "_unified_roster", lambda: {
        "endpoints": [_codex_row()],
        "usable_names": [],
    })

    def forbidden(*_args, **_kwargs):
        raise AssertionError("proposer factory must not run")

    monkeypatch.setattr(endpoint_registry, "make_endpoint_proposer", forbidden)

    body, code = gateway.route_request("hello", "codex-cli")

    assert code == 403
    assert "ChatGPT account" in body["error"]
    assert body["account_state"] == "not_authenticated"


def test_route_request_refuses_codex_account_without_execution_readiness(monkeypatch):
    monkeypatch.setattr(gateway, "_unified_roster", lambda: {
        "endpoints": [_codex_row(account_authenticated=True,
                                 account_state="authenticated",
                                 route_ready=False,
                                 route_ready_reason="project_config_not_admitted",
                                 run_ready=False,
                                 run_ready_reason="project_config_not_admitted")],
        "usable_names": [],
    })

    def forbidden(*_args, **_kwargs):
        raise AssertionError("proposer factory must not run")

    monkeypatch.setattr(endpoint_registry, "make_endpoint_proposer", forbidden)

    body, code = gateway.route_request("hello", "codex-cli")

    assert code == 403
    assert "Codex CLI execution" in body["error"]
    assert body["route_ready"] is False
    assert body["route_ready_reason"] == "project_config_not_admitted"
    assert body["run_ready"] is False
    assert body["run_ready_reason"] == "project_config_not_admitted"
