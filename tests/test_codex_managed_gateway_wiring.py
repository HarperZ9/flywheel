from __future__ import annotations

from harness import gateway


OWNER = "owner_" + "a" * 32


def _handler(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    run = tmp_path / "run"
    run.mkdir()

    class Handler(gateway._Handler):
        root = repo
        run_root = str(run)
        flywheel_home = home
        native_codex_config = None
        native_codex_components = None
        operation_service = None
        operation_process_factory = None
        codex_account_manager = None

    return Handler


def test_gateway_composition_installs_disabled_account_manager_without_default(tmp_path, monkeypatch):
    Handler = _handler(tmp_path)

    def forbidden_connect():
        raise AssertionError("ambient Codex connection was attempted")

    monkeypatch.setattr(
        "harness.codex_account_sessions.CodexAppServerClient.connect",
        forbidden_connect,
    )
    components = Handler._configure_operation_components(Handler.flywheel_home / "state")
    body, status = Handler.codex_account_manager.read_status(OWNER)

    assert status == 503
    assert body["state"] == "unavailable"
    assert body["reason"] == "AGENT_NATIVE_RUNTIME_DISABLED"
    assert Handler.operation_service is components.operation_service
    assert Handler.operation_process_factory is components.operation_process_factory
    assert Handler.operation_process_factory.provider_session_registry is components.provider_session_registry
    assert Handler.operation_process_factory.provider_session_adapters == {}


def test_gateway_lazy_rebuild_replaces_manager_factory_and_registry_together(tmp_path):
    Handler = _handler(tmp_path)
    handler = object.__new__(Handler)
    first_service, first_factory = handler._operation_components()
    first_manager = Handler.codex_account_manager
    first_registry = first_factory.provider_session_registry

    new_home = tmp_path / "home-b"
    new_home.mkdir()
    Handler.flywheel_home = new_home
    second_service, second_factory = handler._operation_components()

    assert second_service is Handler.operation_service
    assert second_factory is Handler.operation_process_factory
    assert second_service is not first_service
    assert second_factory is not first_factory
    assert Handler.codex_account_manager is not first_manager
    assert second_factory.provider_session_registry is not first_registry
    assert second_factory.provider_session_registry is Handler.native_codex_components.provider_session_registry
