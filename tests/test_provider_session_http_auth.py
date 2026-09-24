"""Native session routes authenticate before dispatch or owner-state access."""
import json
import threading
import time
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import pytest

from harness.gateway import _Handler


TOKEN = 'synthetic-provider-session-test-token'
ROUTES = [
    ('POST', '/api/provider-sessions/binding'),
    ('POST', '/api/provider-sessions/turn'),
    ('POST', '/api/provider-sessions/resume'),
    ('POST', '/api/provider-sessions/reconcile'),
    ('GET', '/api/provider-sessions/approvals?operation_ref=op-test'),
    ('POST', '/api/provider-sessions/approvals/respond'),
]


@pytest.fixture
def server(tmp_path):
    dispatched = []

    class Handler(_Handler):
        auth_token = TOKEN
        owner_ref = 'stale-owner-must-not-be-used'
        flywheel_home = tmp_path

        def _route_operation(self, method):
            dispatched.append((method, self.path, self.owner_ref))
            self._json({'owner_ref': self.owner_ref})
            return True

        def log_message(self, *_args):
            pass

    http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(
        target=lambda: http.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()

    def request(method, path, *, token=TOKEN, host=None, content='application/json'):
        headers = {'Content-Type': content}
        if token is not None:
            headers['Authorization'] = 'Bearer ' + token
        if host is not None:
            headers['Host'] = host
        # Under heavy full-suite load on Windows a localhost connection can be
        # aborted by the OS mid-request (WinError 10053/10054). That is transport
        # flakiness, not a policy outcome, so retry a transient socket abort on a
        # fresh connection. The authorization assertions below are unchanged.
        last_exc = None
        for attempt in range(4):
            connection = HTTPConnection('127.0.0.1', http.server_port, timeout=5)
            try:
                connection.request(method, path, body='{}' if method == 'POST' else None,
                                   headers=headers)
                response = connection.getresponse()
                return response.status, json.loads(response.read())
            except (ConnectionAbortedError, ConnectionResetError, TimeoutError) as exc:
                last_exc = exc
                time.sleep(0.05 * (attempt + 1))
            finally:
                connection.close()
        raise last_exc

    try:
        yield Handler, request, dispatched, tmp_path
    finally:
        http.shutdown()
        http.server_close()
        thread.join(5)


@pytest.mark.parametrize('method,path', ROUTES)
@pytest.mark.parametrize('mode', ['auth-off', 'missing', 'wrong', 'host'])
def test_native_routes_refuse_before_dispatch_and_owner_access(server, method, path, mode):
    handler, request, dispatched, home = server
    if mode == 'auth-off':
        handler.auth_token = None
    status, body = request(method, path,
        token=None if mode in {'auth-off', 'missing'} else ('wrong' if mode == 'wrong' else TOKEN),
        host='foreign.invalid' if mode == 'host' else None)
    assert status == 401
    assert body['error']['code'] == 'AUTH_REQUIRED'
    assert dispatched == []
    assert not (home / 'owner.ref').exists()


@pytest.mark.parametrize('method,path', ROUTES)
def test_native_routes_bind_fresh_authenticated_owner(server, method, path):
    _, request, dispatched, home = server
    status, body = request(method, path)
    assert status == 200
    owner = (home / 'owner.ref').read_text().strip()
    assert body == {'owner_ref': owner}
    assert owner != 'stale-owner-must-not-be-used'
    assert dispatched == [(method, path, owner)]


def test_native_mutation_rejects_simple_content_type(server):
    _, request, dispatched, home = server
    status, body = request('POST', '/api/provider-sessions/turn', content='text/plain')
    assert status == 401 and body['error']['code'] == 'AUTH_REQUIRED'
    assert not dispatched and not (home / 'owner.ref').exists()
