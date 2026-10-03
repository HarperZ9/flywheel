from __future__ import annotations

from io import BytesIO

from harness import gateway
from harness.codex_account_gateway_mount import account_get, account_post


OWNER = "owner_" + "a" * 32


class _ExplodingDefaultManager:
    def read_status(self, *_args, **_kwargs):
        raise AssertionError("ambient DEFAULT_MANAGER read_status used")

    def start_login(self, *_args, **_kwargs):
        raise AssertionError("ambient DEFAULT_MANAGER start_login used")


def _handler(tmp_path):
    repo = tmp_path / "repo"; repo.mkdir()
    home = tmp_path / "home-a"; home.mkdir()
    run = tmp_path / "run"; run.mkdir()

    class Handler(gateway._Handler):
        root = repo
        run_root = str(run)
        flywheel_home = home
        native_codex_config = None
        native_codex_components = None
        operation_service = None
        operation_process_factory = None
        codex_account_manager = None
        owner_ref = OWNER

        def _json(self, obj, code=200):
            return obj, code

    return Handler


def _instance(Handler, path="/api/codex/account"):
    handler = object.__new__(Handler)
    handler.path = path
    return handler


def test_account_get_without_injected_manager_uses_disabled_composition_not_default(
    tmp_path,
    monkeypatch,
):
    Handler = _handler(tmp_path)
    monkeypatch.setattr(
        "harness.codex_account_route.DEFAULT_MANAGER",
        _ExplodingDefaultManager(),
    )
    monkeypatch.setattr(
        "harness.codex_account_sessions.CodexAppServerClient.connect",
        lambda: (_ for _ in ()).throw(AssertionError("ambient connect used")),
    )

    body, status = account_get(_instance(Handler), "/api/codex/account")

    assert status == 503
    assert body["state"] == "unavailable"
    assert body["reason"] == "AGENT_NATIVE_RUNTIME_DISABLED"
    assert Handler.codex_account_manager is Handler.native_codex_components.codex_account_manager


def test_account_post_without_injected_manager_uses_disabled_composition_not_default(
    tmp_path,
    monkeypatch,
):
    Handler = _handler(tmp_path)
    monkeypatch.setattr(
        "harness.codex_account_route.DEFAULT_MANAGER",
        _ExplodingDefaultManager(),
    )
    handler = _instance(Handler, "/api/codex/account/login/start")
    handler.headers = {"Content-Type": "application/json"}
    handler.rfile = BytesIO(b'{"mode":"browser"}')
    handler._content_length = lambda: len(b'{"mode":"browser"}')

    body, status = account_post(handler, "/api/codex/account/login/start")

    assert status == 503
    assert body["state"] == "unavailable"
    assert body["reason"] == "AGENT_NATIVE_RUNTIME_DISABLED"
    assert Handler.codex_account_manager is Handler.native_codex_components.codex_account_manager


def test_account_only_flywheel_home_change_rebuilds_managed_components(tmp_path):
    Handler = _handler(tmp_path)

    first_body, first_status = account_get(_instance(Handler), "/api/codex/account")
    first_components = Handler.native_codex_components
    first_service = Handler.operation_service
    first_factory = Handler.operation_process_factory
    first_manager = Handler.codex_account_manager

    next_home = tmp_path / "home-b"; next_home.mkdir()
    Handler.flywheel_home = next_home
    second_body, second_status = account_get(_instance(Handler), "/api/codex/account")

    assert (first_status, first_body["reason"]) == (503, "AGENT_NATIVE_RUNTIME_DISABLED")
    assert (second_status, second_body["reason"]) == (503, "AGENT_NATIVE_RUNTIME_DISABLED")
    assert first_components.state_root == tmp_path / "home-a" / "state"
    assert Handler.native_codex_components.state_root == next_home / "state"
    assert Handler.operation_service is not first_service
    assert Handler.operation_process_factory is not first_factory
    assert Handler.codex_account_manager is not first_manager
    assert Handler.operation_process_factory.provider_session_registry is Handler.native_codex_components.provider_session_registry
