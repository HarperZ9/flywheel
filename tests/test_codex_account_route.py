from codex_account_fakes import ClientFactory, FakeClient, browser_login

from harness.codex_account_route import (
    CodexAccountSessionManager,
    codex_account_get,
    codex_account_post,
)


def test_status_read_is_one_shot_and_does_not_start_login():
    client = FakeClient(account={
        "account": {"type": "chatgpt", "email": "person@example.test",
                    "planType": "pro"},
        "requiresOpenaiAuth": False,
    })
    manager = CodexAccountSessionManager(
        client_factory=ClientFactory(client), key_source=lambda _env: "absent")

    body, status = codex_account_get(
        "/api/codex/account", "", owner_ref="owner-a", manager=manager)

    assert status == 200
    assert body["account"]["usable_for_codex"] is True
    assert client.calls == [("account", False), ("capabilities", None)]
    assert "person@example.test" not in repr(body)
    assert client.closed is True


def test_mutations_require_visible_ui_action_without_creating_client():
    factory = ClientFactory(FakeClient(login=browser_login()))
    manager = CodexAccountSessionManager(client_factory=factory)

    body, status = codex_account_post(
        "/api/codex/account/login/start", {"mode": "browser"},
        owner_ref="owner-a", manager=manager)

    assert status == 403
    assert body["state"] == "rejected"
    assert factory.created == []
