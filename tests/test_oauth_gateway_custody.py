"""Auth custody through the real local HTTP dispatcher; synthetic owner only."""
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from harness import gateway, oauth_service
from tests.http_fixture_client import request as local_request


@pytest.fixture
def http_gateway(tmp_path, monkeypatch):
    calls = []
    for name in ('begin', 'submit', 'sign_out', 'cancel'):
        def action(*args, _name=name, **kwargs):
            calls.append(_name)
            return {'ok': True}
        monkeypatch.setattr(oauth_service, name, action)
    monkeypatch.setattr(oauth_service, 'auth_rows', lambda: calls.append('rows') or {'providers': []})
    monkeypatch.setattr(gateway, '_projected_world', lambda *a: {'public': True})
    monkeypatch.setattr(gateway._Handler, 'flywheel_home', tmp_path / 'home')
    monkeypatch.setattr(gateway._Handler, 'run_root', str(tmp_path / 'runs'))
    monkeypatch.setattr(gateway._Handler, 'root', tmp_path, raising=False)
    monkeypatch.setattr(gateway._Handler, 'auth_token', '')
    server = ThreadingHTTPServer(('127.0.0.1', 0), gateway._Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    def request(path, token=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        # Real owner custody verifies filesystem permissions before dispatch.
        # This is an authentication contract test, not a three-second latency SLA.
        return local_request(server.server_port, path, headers=headers, timeout=8,
            data=None if path.split('?')[0] in ('/api/auth', '/api/world') else b'{"provider":"openai"}')
    yield request, calls
    server.shutdown()
    thread.join(3)
    server.server_close()
    assert not thread.is_alive()


@pytest.mark.parametrize('path', ['/api/auth', '/api/auth?x=1', '/api/auth/login',
    '/api/auth/token', '/api/auth/logout', '/api/auth/cancel'])
def test_auth_requires_configured_owner_then_dispatches(http_gateway, monkeypatch, path):
    request, calls = http_gateway
    assert request(path)[0] == 401
    monkeypatch.setattr(gateway._Handler, 'auth_token', 'synthetic-owner')
    assert request(path, 'wrong')[0] == 401
    assert calls == []
    status, body = request(path, 'synthetic-owner')
    assert status == 200, body
    assert len(calls) == 1
    assert 'synthetic-owner' not in body


@pytest.mark.parametrize('path', ['/api/auth//cancel', '/api/auth/cancel/',
    '/api/auth%2fcancel', '/api/%61uth/cancel', '/api/auth/../auth/cancel'])
def test_route_variants_never_reach_credential_action_without_owner(http_gateway, path):
    request, calls = http_gateway
    assert request(path)[0] in (401, 404)
    assert calls == []


def test_unrelated_public_auth_off_compatibility_remains(http_gateway):
    status, body = http_gateway[0]('/api/world')
    assert status == 200 and json.loads(body) == {'public': True}
