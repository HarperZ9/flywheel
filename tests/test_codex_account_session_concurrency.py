import threading

from codex_account_fakes import FakeClient, browser_login

from harness.codex_account_route import codex_account_get, codex_account_post
from harness.codex_account_sessions import CodexAccountSessionManager


class SlowLoginClient(FakeClient):
    def __init__(self, *, login, release, notifications=None):
        super().__init__(login=login, notifications=notifications)
        self.entered_login = threading.Event()
        self.release = release

    def start_chatgpt_login(self):
        self.calls.append(("login-browser", None))
        self.entered_login.set()
        assert self.release.wait(5)
        return self.login


class LockedFactory:
    def __init__(self, *clients):
        self.clients = list(clients)
        self.created = []
        self.lock = threading.Lock()

    def __call__(self):
        with self.lock:
            client = self.clients.pop(0)
            self.created.append(client)
            return client


def start_in_thread(manager, owner, results):
    body, status = codex_account_post(
        "/api/codex/account/login/start", {"mode": "browser"},
        owner_ref=owner, manager=manager, visible_ui_action=True)
    results.append((owner, status, body["state"]))


def login_completed(login_id):
    return {"method": "account/login/completed",
            "params": {"loginId": login_id, "success": True, "error": None}}


def session_count(manager):
    lock = getattr(manager, "_lock", None)
    if lock is None:
        return len(manager._sessions)
    with lock:
        return len(manager._sessions)


def test_concurrent_starts_reserve_global_capacity_before_launch():
    release = threading.Event()
    first = SlowLoginClient(login=browser_login("login-1"), release=release)
    second = SlowLoginClient(login=browser_login("login-2"), release=release)
    manager = CodexAccountSessionManager(
        client_factory=LockedFactory(first, second), max_pending_sessions=1)
    results = []

    t1 = threading.Thread(target=start_in_thread,
                          args=(manager, "owner-a", results))
    t1.start()
    assert first.entered_login.wait(5)
    t2 = threading.Thread(target=start_in_thread,
                          args=(manager, "owner-b", results))
    t2.start()
    release.set()
    t1.join(5)
    t2.join(5)

    assert sorted((status, state) for _owner, status, state in results) == [
        (202, "login_started"), (503, "throttled")]
    assert len(manager.client_factory.created) == 1
    assert session_count(manager) == 1


def test_guessed_reservation_handle_cannot_be_consumed_during_launch():
    release = threading.Event()
    client = SlowLoginClient(
        login=browser_login("login-1"), release=release,
        notifications=[login_completed("login-1")])
    manager = CodexAccountSessionManager(
        client_factory=LockedFactory(client), max_pending_sessions=1)
    results = []

    thread = threading.Thread(target=start_in_thread,
                              args=(manager, "owner-a", results))
    thread.start()
    assert client.entered_login.wait(5)
    result, result_status = codex_account_get(
        "/api/codex/account/login/result", "login_id=__reserved_1",
        owner_ref="owner-a", manager=manager)
    lookup, lookup_status = codex_account_post(
        "/api/codex/account/login/cancel", {"login_id": "__reserved_1"},
        owner_ref="owner-a", manager=manager, visible_ui_action=True)
    release.set()
    thread.join(5)
    real, real_status = codex_account_get(
        "/api/codex/account/login/result", "login_id=login-1",
        owner_ref="owner-a", manager=manager)

    assert result_status == 404
    assert lookup_status == 404
    assert result["state"] == "unknown_login"
    assert lookup["state"] == "unknown_login"
    assert results == [("owner-a", 202, "login_started")]
    assert real_status == 200
    assert real["state"] == "authenticated"
    assert ("cancel", "__reserved_1") not in client.calls
    assert client.closed is True


def test_concurrent_same_owner_start_reserves_owner_before_launch():
    release = threading.Event()
    first = SlowLoginClient(login=browser_login("login-1"), release=release)
    second = SlowLoginClient(login=browser_login("login-2"), release=release)
    manager = CodexAccountSessionManager(
        client_factory=LockedFactory(first, second), max_pending_sessions=4)
    results = []

    t1 = threading.Thread(target=start_in_thread,
                          args=(manager, "owner-a", results))
    t1.start()
    assert first.entered_login.wait(5)
    t2 = threading.Thread(target=start_in_thread,
                          args=(manager, "owner-a", results))
    t2.start()
    release.set()
    t1.join(5)
    t2.join(5)

    assert sorted((status, state) for _owner, status, state in results) == [
        (202, "login_started"), (409, "already_pending")]
    assert len(manager.client_factory.created) == 1
    assert session_count(manager) == 1
