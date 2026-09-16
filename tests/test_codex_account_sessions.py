from codex_account_fakes import ClientFactory, FakeClient, browser_login, manager_with

from harness.codex_account_route import CodexAccountSessionManager
from harness.codex_account_route import codex_account_get, codex_account_post


def start_browser(manager, owner="owner-a", login_id="login-1"):
    return codex_account_post(
        "/api/codex/account/login/start", {"mode": "browser"},
        owner_ref=owner, manager=manager, visible_ui_action=True)


def completed(login_id="login-1", success=True, error=None):
    return {"method": "account/login/completed",
            "params": {"loginId": login_id, "success": success, "error": error}}


def test_login_result_does_not_infer_success_from_old_account_state():
    client = FakeClient(
        account={"account": {"type": "chatgpt", "email": None,
                             "planType": "pro"},
                 "requiresOpenaiAuth": False},
        login=browser_login("new-login"),
    )
    manager = manager_with(CodexAccountSessionManager, client)

    body, status = start_browser(manager, login_id="new-login")
    assert status == 202
    assert body["login_id"] == "new-login"

    result, status = codex_account_get(
        "/api/codex/account/login/result", "login_id=new-login",
        owner_ref="owner-a", manager=manager)

    assert status == 202
    assert result["state"] == "pending"
    assert ("account", False) not in client.calls
    assert client.closed is False


def test_exact_login_completed_notification_finishes_and_closes_session():
    client = FakeClient(
        login=browser_login("login-1"), notifications=[completed("login-1")])
    manager = manager_with(CodexAccountSessionManager, client)

    start_browser(manager)
    result, status = codex_account_get(
        "/api/codex/account/login/result", "login_id=login-1",
        owner_ref="owner-a", manager=manager)

    assert status == 200
    assert result["state"] == "authenticated"
    assert result["login_id"] == "login-1"
    assert client.closed is True
    unknown, unknown_status = codex_account_get(
        "/api/codex/account/login/result", "login_id=login-1",
        owner_ref="owner-a", manager=manager)
    assert unknown_status == 404
    assert unknown["state"] == "unknown_login"


def test_competing_login_notification_is_ignored_and_second_start_is_refused():
    first = FakeClient(
        login=browser_login("login-1"), notifications=[completed("other-login")])
    second = FakeClient(login=browser_login("login-2"))
    factory = ClientFactory(first, second)
    manager = CodexAccountSessionManager(client_factory=factory)

    start_browser(manager)
    result, status = codex_account_get(
        "/api/codex/account/login/result", "login_id=login-1",
        owner_ref="owner-a", manager=manager)
    refused, refused_status = start_browser(manager, login_id="login-2")

    assert status == 202
    assert result["state"] == "pending"
    assert first.closed is False
    assert refused_status == 409
    assert refused["state"] == "already_pending"
    assert second not in factory.created


def test_login_handles_are_owner_scoped_for_result_and_cancel():
    client = FakeClient(login=browser_login("login-1"))
    manager = manager_with(CodexAccountSessionManager, client)

    start_browser(manager, owner="owner-a")
    result, result_status = codex_account_get(
        "/api/codex/account/login/result", "login_id=login-1",
        owner_ref="owner-b", manager=manager)
    cancel, cancel_status = codex_account_post(
        "/api/codex/account/login/cancel", {"login_id": "login-1"},
        owner_ref="owner-b", manager=manager, visible_ui_action=True)

    assert result_status == 404
    assert result["state"] == "unknown_login"
    assert cancel_status == 404
    assert cancel["state"] == "unknown_login"
    assert ("cancel", "login-1") not in client.calls
    assert client.closed is False


def test_cancel_closes_pending_client_after_visible_action():
    client = FakeClient(login=browser_login("login-1"))
    manager = manager_with(CodexAccountSessionManager, client)

    start_browser(manager)
    body, status = codex_account_post(
        "/api/codex/account/login/cancel", {"login_id": "login-1"},
        owner_ref="owner-a", manager=manager, visible_ui_action=True)

    assert status == 200
    assert body["state"] == "canceled"
    assert ("cancel", "login-1") in client.calls
    assert client.closed is True


def test_expired_login_closes_client_without_completion_claim():
    now = [100.0]
    client = FakeClient(login=browser_login("login-1"))
    manager = manager_with(
        CodexAccountSessionManager, client, clock=lambda: now[0], ttl_seconds=5)

    start_browser(manager)
    now[0] = 106.0
    body, status = codex_account_get(
        "/api/codex/account/login/result", "login_id=login-1",
        owner_ref="owner-a", manager=manager)

    assert status == 410
    assert body["state"] == "expired"
    assert client.closed is True


def test_untrusted_login_url_is_rejected_and_redacted():
    client = FakeClient(login=browser_login(
        "login-1", "https://evil.example.test/login?token=sk-SECRET"))
    manager = manager_with(CodexAccountSessionManager, client)

    body, status = start_browser(manager)

    assert status == 502
    assert body["state"] == "failed"
    assert "SECRET" not in repr(body)
    assert client.closed is True


def test_secret_shaped_raw_login_id_is_rejected_without_redacted_session():
    fake_secret = "sk-" + ("X" * 16)
    client = FakeClient(login=browser_login(fake_secret))
    manager = manager_with(CodexAccountSessionManager, client)

    body, status = start_browser(manager)

    assert status == 502
    assert body["state"] == "failed"
    assert "login_id" not in body
    assert "[redacted]" not in repr(body)
    assert client.closed is True


def test_allowed_host_url_with_secret_shaped_query_is_rejected():
    fake_secret = "sk-" + ("Y" * 16)
    client = FakeClient(login=browser_login(
        "login-1", f"https://auth.openai.com/login?state={fake_secret}"))
    manager = manager_with(CodexAccountSessionManager, client)

    body, status = start_browser(manager)

    assert status == 502
    assert body["state"] == "failed"
    assert "auth_url" not in body
    assert fake_secret not in repr(body)
    assert client.closed is True


def test_legitimate_opaque_login_id_and_url_are_preserved_exactly():
    login = "login_ABC.123-xyz:future~opaque"
    url = "https://auth.openai.com/oauth/authorize?state=abc123&nonce=n-42"
    client = FakeClient(login=browser_login(login, url))
    manager = manager_with(CodexAccountSessionManager, client)

    body, status = start_browser(manager)

    assert status == 202
    assert body["login_id"] == login
    assert body["auth_url"] == url
    assert client.closed is False


def test_global_pending_cap_rejects_without_creating_extra_client():
    first = FakeClient(login=browser_login("login-1"))
    second = FakeClient(login=browser_login("login-2"))
    third = FakeClient(login=browser_login("login-3"))
    factory = ClientFactory(first, second, third)
    manager = CodexAccountSessionManager(
        client_factory=factory, max_pending_sessions=2)

    assert start_browser(manager, owner="owner-a")[1] == 202
    assert start_browser(manager, owner="owner-b", login_id="login-2")[1] == 202
    body, status = start_browser(manager, owner="owner-c", login_id="login-3")

    assert status == 503
    assert body["state"] == "throttled"
    assert third not in factory.created
    assert first.closed is False
    assert second.closed is False


def test_read_status_sweeps_expired_sessions_for_other_owners():
    now = [100.0]
    old_a = FakeClient(login=browser_login("login-1"))
    old_b = FakeClient(login=browser_login("login-2"))
    reader = FakeClient()
    manager = CodexAccountSessionManager(
        client_factory=ClientFactory(old_a, old_b, reader),
        clock=lambda: now[0], ttl_seconds=5)

    start_browser(manager, owner="owner-a")
    start_browser(manager, owner="owner-b", login_id="login-2")
    now[0] = 106.0
    body, status = codex_account_get(
        "/api/codex/account", "", owner_ref="owner-c", manager=manager)

    assert status == 200
    assert body["state"] == "ready"
    assert old_a.closed is True
    assert old_b.closed is True
    assert reader.closed is True


def test_notification_overflow_closes_pending_login_as_unknown_failure():
    client = FakeClient(
        login=browser_login("login-1"), notification_overflow=True)
    manager = manager_with(CodexAccountSessionManager, client)

    start_browser(manager)
    body, status = codex_account_get(
        "/api/codex/account/login/result", "login_id=login-1",
        owner_ref="owner-a", manager=manager)

    assert status == 502
    assert body["state"] == "client_failed"
    assert body["reason"] == "notification overflow"
    assert client.closed is True


def test_client_failure_during_login_result_closes_session_and_redacts_error():
    client = FakeClient(login=browser_login("login-1"), fail_pop=True)
    manager = manager_with(CodexAccountSessionManager, client)

    start_browser(manager)
    body, status = codex_account_get(
        "/api/codex/account/login/result", "login_id=login-1",
        owner_ref="owner-a", manager=manager)

    assert status == 502
    assert body["state"] == "client_failed"
    assert "SECRET" not in repr(body)
    assert client.closed is True


def test_logout_requires_visible_action_and_cleans_owner_sessions():
    pending = FakeClient(login=browser_login("login-1"))
    logout = FakeClient()
    manager = CodexAccountSessionManager(client_factory=ClientFactory(pending, logout))

    start_browser(manager)
    rejected, rejected_status = codex_account_post(
        "/api/codex/account/logout", {}, owner_ref="owner-a", manager=manager)
    body, status = codex_account_post(
        "/api/codex/account/logout", {}, owner_ref="owner-a",
        manager=manager, visible_ui_action=True)

    assert rejected_status == 403
    assert rejected["state"] == "rejected"
    assert status == 200
    assert body["state"] == "logout_requested"
    assert ("logout", None) in logout.calls
    assert pending.closed is True
    assert logout.closed is True
