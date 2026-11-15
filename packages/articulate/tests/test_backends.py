"""Backend routing, wire contracts, and fail-closed privacy controls."""
import importlib
import json
import os
import subprocess
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from articulate import claude_cli

_REAL_RESOLVE = claude_cli.resolve


@pytest.fixture
def backend(monkeypatch):
    spec = importlib.util.find_spec('articulate.backends')
    assert spec is not None, 'the editor needs a backend router'
    module = importlib.import_module('articulate.backends')
    for key in list(os.environ):
        if key.startswith(('ARTICULATE_', 'ANTHROPIC_', 'OPENAI_')):
            monkeypatch.delenv(key)
    def missing(*args, **kwargs):
        raise module.claude_cli.ClaudeUnavailable('not found')
    monkeypatch.setattr(module.claude_cli, 'resolve', missing)
    return module


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def blocked(*args, **kwargs):
        raise OSError('offline test boundary')
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open', blocked)


_REAL_OPEN = urllib.request.OpenerDirector.open


@pytest.fixture
def server(monkeypatch):
    calls, responses = [], {}
    class Handler(BaseHTTPRequestHandler):
        def handle_request(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            calls.append((self.command, self.path, dict(self.headers), json.loads(body) if body else None))
            status, data, headers = responses.get(self.path, (404, {}, {}))
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
        do_GET = do_POST = handle_request
        def log_message(self, *args):
            pass
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    # Guard even the local stub suite against accidental external requests.
    def local_open(opener, request, *args, **kwargs):
        url = request.full_url if hasattr(request, 'full_url') else request
        assert url.startswith('http://127.0.0.1:%d/' % httpd.server_port), 'test attempted non-stub HTTP'
        return _REAL_OPEN(opener, request, *args, **kwargs)
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open', local_open)
    try:
        yield 'http://127.0.0.1:%d' % httpd.server_port, responses, calls
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


@pytest.mark.parametrize('choice', ['none', 'host'])
def test_explicit_no_model_route_is_not_an_error(backend, choice):
    output, info = backend.complete('instructions', 'document', backend=choice)
    assert output == ''
    assert info.to_dict() == {'backend': choice, 'model': None, 'attempts': []}


def test_mcp_auto_never_tries_separately_billed_backends(backend, monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'secret')
    monkeypatch.setenv('ARTICULATE_BACKEND', 'anthropic')
    output, info = backend.complete('p', 't', context='mcp')
    assert info.backend == 'host'
    assert info.attempts == []


@pytest.mark.parametrize('advertised', [False, True])
def test_sampling_requires_advertised_capability(backend, advertised):
    calls = []
    def sampling(instructions, text, timeout):
        calls.append((instructions, text, timeout))
        return {'content': {'type': 'text', 'text': 'edited'}, 'model': 'host-model'}
    output, info = backend.complete('p', 't', 3, context='mcp', sampling=sampling,
                                    sampling_advertised=advertised)
    assert info.backend == ('sampling' if advertised else 'host')
    assert output == ('edited' if advertised else '')
    assert calls == ([('p', 't', 3)] if advertised else [])
    if advertised:
        assert info.model == 'host-model'


def test_failed_sampling_goes_to_host_without_disclosing_error(backend):
    def failed(*args):
        raise RuntimeError('private prompt token')
    _, info = backend.complete('p', 't', context='mcp', sampling=failed, sampling_advertised=True)
    assert info.backend == 'host'
    assert info.attempts[0]['backend'] == 'sampling'
    assert 'private prompt' not in repr(info)


@pytest.mark.parametrize('choice', ['auto','host','sampling','anthropic','claude-cli','openai','ollama','none'])
def test_local_only_refuses_every_nonlocal_route_before_io(backend, monkeypatch, choice):
    monkeypatch.setenv('ARTICULATE_LOCAL_ONLY', '1')
    monkeypatch.setenv('ARTICULATE_OLLAMA_URL', 'https://outside.example')
    def forbidden(*args, **kwargs):
        pytest.fail('local-only crossed a prohibited boundary')
    monkeypatch.setattr(backend, '_request', forbidden)
    monkeypatch.setattr(backend.claude_cli, 'resolve', forbidden)
    _, info = backend.complete('p', 't', backend=choice, context='mcp', sampling=forbidden,
                               sampling_advertised=True)
    assert info.backend == 'none'


@pytest.mark.parametrize('url', ['http://127.0.0.1.evil.test', 'http://2130706433',
                                'http://localhost.evil.test', 'http://user:secret@127.0.0.1',
                                'file:///private', 'http://192.168.1.1'])
def test_local_only_rejects_ambiguous_or_nonloopback_urls(backend, monkeypatch, url):
    monkeypatch.setenv('ARTICULATE_LOCAL_ONLY', 'true')
    monkeypatch.setenv('ARTICULATE_OLLAMA_URL', url)
    def forbidden(*args, **kwargs):
        pytest.fail('invalid URL reached transport')
    monkeypatch.setattr(backend, '_request', forbidden)
    _, info = backend.complete('p', 't', backend='ollama')
    assert info.backend == 'none'
    assert 'secret' not in repr(info)


def test_anthropic_wire_contract(backend, monkeypatch, server):
    url, responses, calls = server
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-key')
    monkeypatch.setattr(backend, 'ANTHROPIC_URL', url + '/v1/messages')
    responses['/v1/messages'] = (200, {'model': 'claude-test', 'content': [{'type':'text','text':'edited'}]}, {})
    output, info = backend.complete('instructions', 'document', backend='anthropic')
    assert (output, info.backend, info.model) == ('edited', 'anthropic', 'claude-test')
    method, path, headers, body = calls[0]
    assert method == 'POST'
    assert {key.lower(): value for key, value in headers.items()}['x-api-key'] == 'test-key'
    assert body['system'] == 'instructions'
    assert body['messages'] == [{'role':'user','content':'document'}]


def test_openai_custom_endpoint_never_receives_default_openai_key(backend, monkeypatch, server):
    url, responses, calls = server
    monkeypatch.setenv('ARTICULATE_OPENAI_BASE_URL', url + '/v1')
    monkeypatch.setenv('OPENAI_API_KEY', 'must-not-leak')
    monkeypatch.setenv('ARTICULATE_MODEL', 'installed-model')
    responses['/v1/chat/completions'] = (200, {'model':'actual-model','choices':[{'message':{'content':'edited'}}]}, {})
    output, info = backend.complete('p', 't', backend='openai')
    assert (output, info.backend, info.model) == ('edited','openai','actual-model')
    assert 'Authorization' not in calls[0][2]
    assert calls[0][3]['model'] == 'installed-model'


def test_ollama_picks_installed_preference_and_ignores_proxies(backend, monkeypatch, server):
    url, responses, calls = server
    monkeypatch.setenv('ARTICULATE_OLLAMA_URL', url)
    monkeypatch.setenv('ARTICULATE_LOCAL_ONLY', '1')
    for name in ['HTTP_PROXY','HTTPS_PROXY','ALL_PROXY']:
        monkeypatch.setenv(name, 'http://127.0.0.1:1')
    monkeypatch.setenv('NO_PROXY', '')
    responses['/api/tags'] = (200, {'models':[{'name':'unlisted:1b'},{'name':'qwen3:8b'}]}, {})
    responses['/api/chat'] = (200, {'model':'qwen3:8b','message':{'content':'edited'}}, {})
    output, info = backend.complete('p','t',backend='ollama')
    assert (output, info.backend, info.model) == ('edited','ollama','qwen3:8b')
    assert [item[1] for item in calls] == ['/api/tags','/api/chat']
    assert calls[1][3]['model'] == 'qwen3:8b'
    assert calls[1][3]['stream'] is False


def test_ollama_missing_configured_model_never_pulls(backend, monkeypatch, server):
    url, responses, calls = server
    monkeypatch.setenv('ARTICULATE_LOCAL_ONLY','1')
    monkeypatch.setenv('ARTICULATE_OLLAMA_URL',url)
    monkeypatch.setenv('ARTICULATE_LOCAL_MODEL','not-installed')
    responses['/api/tags'] = (200, {'models':[{'name':'qwen3:8b'}]}, {})
    _, info = backend.complete('p','t')
    assert info.backend == 'none'
    assert [item[1] for item in calls] == ['/api/tags']


def test_redirect_does_not_forward_credentials(backend, monkeypatch, server):
    url, responses, calls = server
    monkeypatch.setenv('ANTHROPIC_API_KEY','secret')
    monkeypatch.setattr(backend,'ANTHROPIC_URL',url+'/v1/messages')
    responses['/v1/messages'] = (307, {}, {'Location':url+'/stolen'})
    _, info = backend.complete('p','t',backend='anthropic')
    assert info.backend == 'none'
    assert '/stolen' not in [item[1] for item in calls]
    assert 'secret' not in repr(info)


def test_http_error_payload_is_not_in_attempts(backend, monkeypatch, server):
    url, responses, _ = server
    monkeypatch.setenv('ANTHROPIC_API_KEY','secret')
    monkeypatch.setattr(backend,'ANTHROPIC_URL',url+'/v1/messages')
    responses['/v1/messages'] = (429, {'error':'private prompt secret'}, {})
    _, info = backend.complete('p','t',backend='anthropic',context='mcp')
    assert info.backend == 'host'
    assert '429' in info.attempts[0]['reason']
    assert 'private prompt' not in repr(info)


def test_missing_cli_falls_through_to_none(backend):
    _, info = backend.complete('p','t',backend='claude-cli')
    assert info.backend == 'none'
    assert info.attempts[0]['backend'] == 'claude-cli'
    assert 'not found' in info.attempts[0]['reason']


def test_credit_error_with_null_subscription_has_precise_safe_reason(backend, monkeypatch):
    monkeypatch.setattr(backend.claude_cli,'auth_status',lambda **kwargs: {'loggedIn':True,'subscriptionType':None})
    monkeypatch.setattr(backend.claude_cli,'run',lambda *args,**kwargs:
                        subprocess.CompletedProcess([],1,'credit balance is too low','secret'))
    _, info = backend.complete('p','t',backend='claude-cli')
    assert info.backend == 'none'
    reason = info.attempts[0]['reason']
    assert 'no subscription' in reason and 'no API credit' in reason
    assert 'claude login' in reason and 'ANTHROPIC_API_KEY' in reason and 'local' in reason
    assert 'secret' not in repr(info)


def test_logged_out_cli_never_attempts_completion(backend, monkeypatch):
    monkeypatch.setattr(backend.claude_cli,'auth_status',lambda **kwargs: {'loggedIn':False})
    def forbidden(*args, **kwargs):
        pytest.fail('logged-out CLI attempted a model call')
    monkeypatch.setattr(backend.claude_cli,'run',forbidden)
    _, info = backend.complete('p','t',backend='claude-cli')
    assert info.backend == 'none'
    assert 'not logged in' in info.attempts[0]['reason']


def test_auth_preflight_uses_isolated_safe_runner(backend, tmp_path, monkeypatch):
    monkeypatch.setattr(backend.claude_cli, 'resolve', _REAL_RESOLVE)
    seen = []
    def runner(argv, **kwargs):
        seen.append((argv, kwargs['cwd']))
        assert os.listdir(kwargs['cwd']) == []
        return subprocess.CompletedProcess(argv,0,json.dumps({'loggedIn':True,'subscriptionType':None}), '')
    status = backend.claude_cli.auth_status(environ={'ARTICULATE_CLAUDE_CLI':'/opt/claude'},
                 exists=lambda path: path == '/opt/claude',windows=False,runner=runner,tmpdir=str(tmp_path))
    assert status['loggedIn'] is True
    assert seen[0][0] == ['/opt/claude','auth','status','--json']
    assert not os.path.exists(seen[0][1])
