"""Cancel/commit ordering controls, with a synthetic temporary credential store."""
# ruff: noqa: F811 -- pytest injects the imported shared fixture by name.
import threading
import time

from harness import oauth_service as svc, oauth_signin as signin
from tests.test_oauth_completion import flow, start, settle  # noqa: F401


def test_signout_orders_replacement_begin_after_local_delete(flow, monkeypatch):
    start(flow)
    deleting, release, second_done = threading.Event(), threading.Event(), threading.Event()
    original = signin.keychain.keychain_delete
    def delete(name):
        deleting.set()
        assert release.wait(3)
        original(name)
        return {'deleted': name}
    monkeypatch.setattr(signin.keychain, 'keychain_delete', delete)
    out = threading.Thread(target=lambda: svc.sign_out('openai'))
    out.start()
    assert deleting.wait(2)
    second = threading.Thread(target=lambda: (svc.begin('openai'), second_done.set()))
    second.start()
    try:
        assert not second_done.wait(.15)
        assert len(flow[1]) == 1
    finally:
        release.set()
        out.join(3)
        second.join(3)
    assert not out.is_alive() and not second.is_alive()
    deadline = time.monotonic() + 2
    while len(flow[1]) != 2 and time.monotonic() < deadline:
        time.sleep(.01)
    assert len(flow[1]) == 2
    flow[2]()
    assert settle()['state'] == 'done'
    assert flow[0]


def test_old_exchange_cannot_overwrite_replacement_job_or_store(flow, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = signin.urllib.request.urlopen
    def exchange(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return original(*args, **kwargs)
    monkeypatch.setattr(signin.urllib.request, 'urlopen', exchange)
    start(flow)
    worker = next(t for t in threading.enumerate() if t.name == 'signin-openai')
    flow[2]()
    assert entered.wait(2)
    try:
        assert svc.cancel('openai')['ok']
        assert svc.begin('openai')['ok']
    finally:
        release.set()
        worker.join(3)
    assert not worker.is_alive()
    assert svc._job('openai')['state'] == 'running'
    assert not flow[0]


def test_duplicate_begin_claims_only_one_live_attempt(flow):
    start(flow)
    assert svc.begin('openai')['ok']
    assert len(flow[1]) == 1
    flow[2]()
    assert settle()['state'] == 'done'


def test_store_wins_before_cancel_reports_already_completed(flow, monkeypatch):
    storing, release = threading.Event(), threading.Event()
    original = signin.keychain.keychain_set
    def write(*args):
        storing.set()
        assert release.wait(3)
        return original(*args)
    monkeypatch.setattr(signin.keychain, 'keychain_set', write)
    start(flow)
    flow[2]()
    assert storing.wait(2)
    result = {}
    cancel = threading.Thread(target=lambda: result.update(svc.cancel('openai')))
    cancel.start()
    try:
        cancel.join(.1)
        assert cancel.is_alive()
    finally:
        release.set()
        cancel.join(3)
    assert not cancel.is_alive()
    assert result['state'] == 'already_completed' and not result['ok']
    assert settle()['state'] == 'done' and flow[0]


def test_worker_start_failure_closes_remote_listener(flow, monkeypatch):
    servers = []
    original = signin._pkce_begin
    def begin(*args, **kwargs):
        result = original(*args, **kwargs)
        servers.append(result[0])
        return result
    def fail_start(self):
        raise RuntimeError('SYNTHETIC_SECRET')
    monkeypatch.setattr(signin, '_pkce_begin', begin)
    monkeypatch.setattr(threading.Thread, 'start', fail_start)
    result = svc.begin('openai', callback_base='http://127.0.0.1:1')
    assert not result['ok'] and 'SYNTHETIC_SECRET' not in str(result)
    assert servers[0].socket.fileno() == -1
    assert svc._job('openai')['state'] == 'failed'


def test_cancel_between_remote_bind_and_worker_start_closes_listener(flow, monkeypatch):
    servers, workers = [], []
    original_begin, original_start = signin._pkce_begin, threading.Thread.start
    def begin(*args, **kwargs):
        result = original_begin(*args, **kwargs)
        servers.append(result[0])
        return result
    def start_worker(self):
        if self.name == 'signin-openai':
            assert svc.cancel('openai')['ok']
            workers.append(self)
        return original_start(self)
    monkeypatch.setattr(signin, '_pkce_begin', begin)
    monkeypatch.setattr(threading.Thread, 'start', start_worker)
    assert svc.begin('openai', callback_base='http://127.0.0.1:1')['ok']
    workers[0].join(3)
    try:
        assert not workers[0].is_alive()
        assert servers[0].socket.fileno() == -1
    finally:
        servers[0].server_close()


def test_completion_during_presence_read_preserves_pending_until_next_poll(flow, monkeypatch):
    svc._set_job('openai', 'running')
    original = signin.status
    def completing_status():
        rows = original()
        flow[0]['CHATGPT_OAUTH_TOKEN'] = 'SYNTHETIC_TOKEN'
        svc._set_job('openai', 'done')
        return rows
    monkeypatch.setattr(signin, 'status', completing_status)
    row = next(r for r in svc.auth_rows()['providers'] if r['provider'] == 'openai')
    assert row['pending'] and row['last'] == 'running' and not row['present']
    row = next(r for r in svc.auth_rows()['providers'] if r['provider'] == 'openai')
    assert not row['pending'] and row['last'] == 'done' and row['present']
