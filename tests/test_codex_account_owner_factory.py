"""The managed account path must select a profile for the validated owner."""
import pytest

from codex_account_fakes import FakeClient, browser_login
from harness.codex_account_sessions import CodexAccountSessionManager


def test_status_uses_distinct_validated_owner_profiles():
    owners = []

    def factory(*, owner_ref):
        owners.append(owner_ref)
        return FakeClient(account={'account': None, 'requiresOpenaiAuth': True})

    manager = CodexAccountSessionManager(owner_client_factory=factory,
                                        key_source=lambda _: 'absent')
    for owner in ('owner-a', 'owner-b'):
        body, status = manager.read_status(owner)
        assert status == 200
        assert body['account']['effective_auth_source'] == 'none'
    assert owners == ['owner-a', 'owner-b']
    assert manager.read_status('')[1] == 400
    assert owners == ['owner-a', 'owner-b']


def test_login_and_logout_use_same_owner_factory():
    owners = []
    client = FakeClient(login=browser_login('managed-login'))

    def factory(*, owner_ref):
        owners.append(owner_ref)
        return client

    manager = CodexAccountSessionManager(owner_client_factory=factory)
    assert manager.start_login('owner-a', 'browser')[1] == 403
    assert owners == []
    body, status = manager.start_login('owner-a', 'browser', visible_ui_action=True)
    assert status == 202
    assert body['login_id'] == 'managed-login'
    assert manager.logout('owner-a', visible_ui_action=True)[1] == 200
    assert owners == ['owner-a', 'owner-a']


def test_broken_owner_factory_never_falls_back_to_ambient_process(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('ambient Codex process must not launch')

    monkeypatch.setattr('harness.codex_account_sessions.CodexAppServerClient.connect', forbidden)

    def factory(*, owner_ref):
        raise RuntimeError('profile unavailable')

    manager = CodexAccountSessionManager(owner_client_factory=factory)
    assert manager.read_status('owner-a')[1] == 503
    assert manager.start_login('owner-a', 'browser', visible_ui_action=True)[1] == 502


def test_ambiguous_factory_configuration_is_rejected():
    with pytest.raises(ValueError):
        CodexAccountSessionManager(client_factory=lambda: None,
                                   owner_client_factory=lambda **_: None)


def test_owned_profile_does_not_inherit_ambient_api_key_status(monkeypatch):
    monkeypatch.setattr('harness.codex_consumer_account._default_key_source',
                        lambda _: 'env')
    manager = CodexAccountSessionManager(
        owner_client_factory=lambda **_: FakeClient())
    body, status = manager.read_status('owner-a')
    assert status == 200
    assert body['account']['effective_auth_source'] == 'none'
    assert body['account']['usable_for_codex'] is False
