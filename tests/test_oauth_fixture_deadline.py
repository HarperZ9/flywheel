"""Custody HTTP fixture deadlines stay long enough to test real owner ACL work."""
import json
import threading
import time
from pathlib import Path

import pytest

from harness import gateway, operation_grants
from tests.test_oauth_gateway_custody import http_gateway


def _delay_owner_directory_acl(monkeypatch, delay_s):
    original = operation_grants._secure_owner_only
    acl_started = threading.Event()
    acl_released = threading.Event()
    acl_released.set()
    acl_calls = []

    def delayed(path, *, directory):
        original(path, directory=directory)
        if not directory:
            return
        acl_calls.append(Path(path))
        acl_started.set()
        time.sleep(delay_s)
        acl_released.wait(10)

    monkeypatch.setattr(operation_grants, '_secure_owner_only', delayed)
    return acl_started, acl_released, acl_calls


def _track_gateway_handler_completion(monkeypatch):
    original = gateway._Handler._gateway_method
    completed = threading.Event()

    def tracked(self, method, handler):
        try:
            return original(self, method, handler)
        finally:
            completed.set()

    monkeypatch.setattr(gateway._Handler, '_gateway_method', tracked)
    return completed


def _enable_owner_token(monkeypatch):
    monkeypatch.setattr(gateway._Handler, 'auth_token', 'synthetic-owner')


def test_authorized_cancel_survives_slow_owner_acl_under_custody_budget(http_gateway, monkeypatch):
    request, calls = http_gateway
    _enable_owner_token(monkeypatch)
    handler_completed = _track_gateway_handler_completion(monkeypatch)
    acl_started, _, acl_calls = _delay_owner_directory_acl(monkeypatch, 3.4)
    try:
        status, body = request('/api/auth/cancel', 'synthetic-owner')
    finally:
        assert handler_completed.wait(6)

    assert status == 200
    assert json.loads(body) == {'ok': True}
    assert acl_started.is_set()
    assert len(acl_calls) == 1
    assert calls == ['cancel']


def test_authorized_cancel_times_out_at_custody_budget_before_late_dispatch(http_gateway, monkeypatch):
    request, calls = http_gateway
    _enable_owner_token(monkeypatch)
    handler_completed = _track_gateway_handler_completion(monkeypatch)
    acl_started, acl_released, acl_calls = _delay_owner_directory_acl(monkeypatch, 9)
    acl_released.clear()

    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError):
            request('/api/auth/cancel', 'synthetic-owner')
        elapsed = time.monotonic() - started
        calls_at_client_return = list(calls)
    finally:
        acl_released.set()
        assert handler_completed.wait(11)

    # The client keeps its configured socket timeout even if the host schedules
    # this test late; a strict wall-clock upper bound would introduce a new race.
    assert elapsed >= 7.0
    assert acl_started.is_set()
    assert len(acl_calls) == 1
    assert calls_at_client_return == []
    assert calls == ['cancel']


def test_wrong_owner_never_reaches_acl_or_cancel_action(http_gateway, monkeypatch):
    request, calls = http_gateway
    _enable_owner_token(monkeypatch)
    acl_started, _, acl_calls = _delay_owner_directory_acl(monkeypatch, 0)

    status, body = request('/api/auth/cancel', 'wrong-owner')

    assert status == 401
    assert json.loads(body)['error']['code'] == 'AUTH_REQUIRED'
    assert not acl_started.is_set()
    assert acl_calls == []
    assert calls == []
