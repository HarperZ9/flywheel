"""Account operations must retain managed policy and process custody."""
from types import SimpleNamespace

import pytest

from harness.codex_account_state import Session, completion_for
from harness.codex_session_types import CodexNotification


class Transport:
    def __init__(self):
        self.calls = []
        self.notifications = []
        self.overflow = False

    def request(self, method, params=None):
        self.calls.append((method, params))
        return {'method': method}

    def pop_notification(self, *, timeout=0):
        return self.notifications.pop(0) if self.notifications else None

    def notification_overflowed(self):
        return self.overflow


def managed_session(*, cleanup=True):
    transport = Transport()
    state = {'checks': 0, 'closes': 0, 'drift': False}

    def check():
        state['checks'] += 1
        if state['drift']:
            raise RuntimeError('configuration drift')

    def close():
        state['closes'] += 1
        return cleanup

    session = SimpleNamespace(transport=transport,
        client=SimpleNamespace(check_configuration=check), close=close)
    return session, state


def account_client(session):
    from harness.codex_managed_account_client import ManagedCodexAccountClient
    return ManagedCodexAccountClient(session)


def test_account_requests_use_owned_transport_and_check_configuration():
    session, state = managed_session()
    client = account_client(session)
    client.get_account(refresh_token=False)
    client.list_models(include_hidden=False)
    assert session.transport.calls == [
        ('account/read', {}), ('model/list', {'includeHidden': False})]
    assert state['checks'] == 2


def test_drift_prevents_login_but_cancel_remains_available():
    session, state = managed_session()
    client = account_client(session)
    state['drift'] = True
    with pytest.raises(RuntimeError):
        client.start_chatgpt_login()
    assert session.transport.calls == []
    client.cancel_login('login-1')
    assert session.transport.calls == [('account/login/cancel', {'loginId': 'login-1'})]


def test_typed_notification_reaches_existing_owner_login_matcher():
    session, _ = managed_session()
    client = account_client(session)
    session.transport.notifications = [CodexNotification(
        1, 'account/login/completed', {'loginId': 'login-1', 'success': True})]
    login = Session('owner-1', 'login-1', 'browser', client, 999999)
    assert completion_for(login, client.pop_notification()) == {
        'loginId': 'login-1', 'success': True}
    assert client.pop_notification() is None


def test_close_owns_process_cleanup_and_refuses_reuse():
    session, state = managed_session()
    client = account_client(session)
    client.close()
    assert state['closes'] == 1
    with pytest.raises(RuntimeError):
        client.get_account()
    assert session.transport.calls == []


def test_failed_cleanup_is_reported_and_can_be_retried():
    session, state = managed_session(cleanup=False)
    client = account_client(session)
    with pytest.raises(RuntimeError, match='CLEANUP'):
        client.close()
    with pytest.raises(RuntimeError):
        client.start_device_code_login()
    session.close = lambda: True
    client.close()
    assert state['closes'] == 1


def test_notification_loss_is_exposed_to_existing_manager():
    session, _ = managed_session()
    client = account_client(session)
    session.transport.overflow = True
    assert client.notification_overflowed() is True


def test_account_facade_cannot_reinitialize_or_send_model_turns():
    session, _ = managed_session()
    client = account_client(session)
    with pytest.raises(RuntimeError):
        client.initialize()
    with pytest.raises(RuntimeError):
        client.transport.request('turn/start', {'input': []})
    assert session.transport.calls == []
