"""Synthetic OAuth completion controls; no provider or OS credential access."""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import pytest

from harness import oauth_service as svc, oauth_signin as signin


@pytest.fixture
def flow(monkeypatch):
    store, opened, bodies = {}, [], []
    real_open = urllib.request.urlopen
    monkeypatch.setenv('FLYWHEEL_OPENAI_OAUTH_CLIENT_ID', 'synthetic-client')
    monkeypatch.setenv('FLYWHEEL_OPENAI_OAUTH_AUTHORIZE_URL', 'https://synthetic.invalid/auth')
    monkeypatch.setenv('FLYWHEEL_OPENAI_OAUTH_EXCHANGE_URL', 'https://synthetic.invalid/token')
    monkeypatch.setattr(signin.keychain, 'keychain_available', lambda: True)
    monkeypatch.setattr(signin.keychain, 'resolve_credential', lambda n: store.get(n, ''))
    monkeypatch.setattr(signin.keychain, 'credential_source', lambda n: 'keychain' if n in store else 'absent')
    monkeypatch.setattr(signin.keychain, 'keychain_set', lambda n, v: store.update({n: v}) or {'stored': n})
    monkeypatch.setattr(signin.keychain, 'keychain_delete', lambda n: store.pop(n, None) or {})
    monkeypatch.setattr(signin.webbrowser, 'open', lambda url: opened.append(url) or True)

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return b'{"access_token":"SYNTHETIC_TOKEN"}'

    monkeypatch.setattr(signin.urllib.request, 'urlopen', lambda *a, **k: Response())

    def deliver(query=None, wrong_path=False):
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(opened[-1]).query)
        callback = (q.get('redirect_uri') or q.get('callback_url'))[0]
        if wrong_path:
            callback = callback.rsplit('/', 1)[0] + '/wrong'
        query = query if query is not None else urllib.parse.urlencode({
            'code': 'SYNTHETIC_CODE', **({'state': q['state'][0]} if 'state' in q else {})})
        try:
            response = real_open(callback + '?' + query, timeout=3)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            bodies.append(response.read().decode())
            return response.status

    with svc._LOCK:
        svc._JOBS.clear()
    yield store, opened, deliver, bodies
    if hasattr(svc, 'cancel'):
        for provider in ('openai', 'openrouter'):
            svc.cancel(provider)
    deadline = time.monotonic() + 3
    while any(t.name.startswith('signin-') for t in threading.enumerate()) and time.monotonic() < deadline:
        time.sleep(.01)


def settle(provider='openai'):
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        job = svc._job(provider)
        if job.get('state') not in ('running', None):
            return job
        time.sleep(.01)
    pytest.fail('synthetic sign-in did not finish')


def start(flow):
    finished = threading.Event()
    result = {}
    def begin():
        result.update(svc.begin('openai'))
        finished.set()
    thread = threading.Thread(target=begin)
    thread.start()
    try:
        assert finished.wait(1), 'begin blocked waiting for the browser'
        assert result['ok'] and result['mode'] == 'browser'
        deadline = time.monotonic() + 1
        while not flow[1] and time.monotonic() < deadline:
            time.sleep(.01)
        assert flow[1]
    except BaseException:
        if flow[1]:
            flow[2]()
        raise
    finally:
        thread.join(3)


def test_registered_pending_beyond_client_timeout_then_stored(flow):
    start(flow)
    time.sleep(15.1)
    row = next(r for r in svc.auth_rows()['providers'] if r['provider'] == 'openai')
    assert row['pending'] and not row['present']
    assert flow[2]() == 200
    assert 'Signed in' not in flow[3][-1]
    assert settle()['state'] == 'done'
    assert flow[0] == {'CHATGPT_OAUTH_TOKEN': 'SYNTHETIC_TOKEN'}
    assert 'SYNTHETIC_TOKEN' not in json.dumps(svc.auth_rows())


@pytest.mark.parametrize('query', ['code=BAD', 'code=BAD&state=wrong',
    'code=BAD&state=x&state=y', 'code=A&code=B', 'code=A&error=access_denied'])
def test_invalid_callback_does_not_consume_valid_result(flow, query):
    start(flow)
    assert flow[2](query) == 400
    assert svc._job('openai')['state'] == 'running'
    assert not flow[0]
    assert flow[2]() == 200
    assert settle()['state'] == 'done'


def test_wrong_nonce_then_valid_callback(flow):
    start(flow)
    assert flow[2](wrong_path=True) == 404
    assert not flow[0]
    flow[2]()
    assert settle()['state'] == 'done'


@pytest.mark.parametrize('failure', ['store', 'exchange'])
def test_callback_never_claims_success_before_rejected_completion(flow, monkeypatch, failure):
    if failure == 'store':
        monkeypatch.setattr(signin.keychain, 'keychain_set', lambda *a: {'error': 'SYNTHETIC_SECRET'})
    else:
        def reject(*a, **k): raise urllib.error.URLError('SYNTHETIC_SECRET')
        monkeypatch.setattr(signin.urllib.request, 'urlopen', reject)
    start(flow)
    flow[2]()
    assert 'Signed in' not in flow[3][-1]
    assert settle()['state'] == 'failed'
    assert not flow[0]
    assert 'SYNTHETIC_SECRET' not in json.dumps(svc.auth_rows())


@pytest.mark.parametrize('raises', [False, True])
def test_browser_failure_is_prompt_and_sanitized(flow, monkeypatch, raises):
    servers = []
    original = signin._pkce_begin
    def begin(*args, **kwargs):
        result = original(*args, **kwargs)
        servers.append(result[0])
        return result
    monkeypatch.setattr(signin, '_pkce_begin', begin)
    def browser(url):
        if raises:
            raise RuntimeError('SYNTHETIC_SECRET')
        return False
    monkeypatch.setattr(signin.webbrowser, 'open', browser)
    result = svc.begin('openai')
    assert result['ok']
    job = settle()
    assert job['state'] == 'failed' and 'browser' in job['error']
    assert 'SYNTHETIC_SECRET' not in json.dumps(job)
    assert not flow[0]
    assert servers[0].socket.fileno() == -1


def test_cancel_waiting_never_stores(flow):
    start(flow)
    worker = next(t for t in threading.enumerate() if t.name == 'signin-openai')
    assert svc.cancel('openai')['ok']
    worker.join(3)
    assert not worker.is_alive()
    assert settle()['state'] == 'cancelled'
    assert not flow[0]


def test_cancel_during_exchange_prevents_late_store(flow, monkeypatch):
    exchanging, release = threading.Event(), threading.Event()
    real = signin.urllib.request.urlopen
    def delayed(*args, **kwargs):
        exchanging.set()
        assert release.wait(3)
        return real(*args, **kwargs)
    monkeypatch.setattr(signin.urllib.request, 'urlopen', delayed)
    start(flow)
    worker = next(t for t in threading.enumerate() if t.name == 'signin-openai')
    flow[2]()
    assert exchanging.wait(2)
    try:
        assert svc.cancel('openai')['ok']
    finally:
        release.set()
        worker.join(3)
    assert not worker.is_alive()
    assert settle()['state'] == 'cancelled'
    assert not flow[0]


def test_cancel_completed_does_not_claim_reversal(flow):
    start(flow)
    flow[2]()
    assert settle()['state'] == 'done'
    out = svc.cancel('openai')
    assert not out['ok'] and out['state'] == 'already_completed'
    assert flow[0]
