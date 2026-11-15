"""Hosted resource-server acceptance via the real ASGI HTTP transport."""
import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

pytest.importorskip('fastmcp')
from fastmcp.server.auth.providers.jwt import RSAKeyPair
from starlette.testclient import TestClient


@pytest.fixture(scope='module')
def keys():
    return RSAKeyPair.generate()


def config(keys, **changes):
    from articulate.hosted_mcp import HostedConfig
    values = dict(base_url='https://articulate.example', issuer='https://auth.example',
                  public_key=keys.public_key, audience='https://articulate.example/mcp')
    values.update(changes)
    return HostedConfig(**values)


def token(keys, **changes):
    values = dict(issuer='https://auth.example', audience='https://articulate.example/mcp',
                  scopes=['articulate:use'])
    values.update(changes)
    return keys.create_token(**values)


def client(keys, **changes):
    from articulate.hosted_mcp import build_app
    return TestClient(build_app(config(keys, **changes)))


def rpc(c, credential, method='tools/list', params=None):
    headers = {'Accept': 'application/json, text/event-stream'}
    if credential is not None:
        headers['Authorization'] = 'Bearer ' + credential
    return c.post('/mcp', json={'jsonrpc': '2.0', 'id': 1, 'method': method,
                              'params': params or {}}, headers=headers)


def call(c, credential, name, **arguments):
    r = rpc(c, credential, 'tools/call', {'name': name, 'arguments': arguments})
    assert r.status_code == 200, r.text
    return r.json()['result']


def data(result):
    return result.get('structuredContent') or json.loads(result['content'][0]['text'])


def test_startup_requires_complete_auth_configuration():
    from articulate.hosted_mcp import HostedConfig
    with pytest.raises(ValueError):
        HostedConfig.from_env({})


@pytest.mark.parametrize('changes', [
    {'base_url': 'http://public.example'}, {'issuer': 'http://auth.example'},
    {'audience': ''}, {'public_key': None}, {'max_chars': 0}, {'max_concurrent': 0},
])
def test_invalid_configuration(keys, changes):
    with pytest.raises(ValueError):
        config(keys, **changes)


@pytest.mark.parametrize('base', ['https://ARTICULATE.example',
                                 'https://articulate.example:443'])
def test_noncanonical_resource_origin_rejected(keys, base):
    with pytest.raises(ValueError, match='canonical'):
        config(keys, base_url=base, audience=base + '/mcp')


@pytest.mark.parametrize('base', ['https://articulate.example',
                                 'https://articulate.example/'])
def test_resource_audience_matches_discovery(keys, base):
    resource = base.rstrip('/') + '/mcp'
    with client(keys, base_url=base, audience=resource) as c:
        metadata = c.get('/.well-known/oauth-protected-resource/mcp').json()
        assert metadata['resource'] == resource
        assert rpc(c, token(keys, audience=metadata['resource'])).status_code == 200


@pytest.mark.parametrize('kind', ['absent', 'invalid', 'audience', 'issuer', 'expired', 'scope', 'no_expiry', 'signature', 'nan_expiry', 'infinite_expiry', 'boolean_expiry'])
def test_auth_rejects_invalid_credentials(keys, kind):
    credentials = {
        'absent': None, 'invalid': 'invalid',
        'audience': token(keys, audience='https://other.example/mcp'),
        'issuer': token(keys, issuer='https://other.example'),
        'expired': token(keys, expires_in_seconds=-100),
        'scope': token(keys, scopes=['other']),
        'no_expiry': token(keys, additional_claims={'exp': None}),
        'signature': token(RSAKeyPair.generate()),
        'nan_expiry': token(keys, additional_claims={'exp': float('nan')}),
        'infinite_expiry': token(keys, additional_claims={'exp': float('inf')}),
        'boolean_expiry': token(keys, additional_claims={'exp': True}),
    }
    with client(keys) as c:
        r = rpc(c, credentials[kind])
    assert r.status_code in (401, 403)
    assert 'www-authenticate' in r.headers


def test_resource_metadata_and_disclosure(keys):
    with client(keys) as c:
        challenge = rpc(c, None)
        assert 'resource_metadata=' in challenge.headers['www-authenticate']
        metadata = c.get('/.well-known/oauth-protected-resource/mcp').json()
        assert metadata['resource'] == 'https://articulate.example/mcp'
        assert metadata['authorization_servers'] == ['https://auth.example']
        assert metadata['scopes_supported'] == ['articulate:use']
        r = rpc(c, token(keys))
    assert r.status_code == 200
    tools = r.json()['result']['tools']
    assert {t['name'] for t in tools} == {'check', 'score', 'edit_plan', 'edit_submit'}
    for tool in tools:
        assert 'hosted service' in tool['description']
        assert tool['annotations']['openWorldHint'] is True
        schemes = [{'type': 'oauth2', 'scopes': ['articulate:use']}]
        assert tool['securitySchemes'] == schemes
        assert tool['_meta']['securitySchemes'] == schemes
        assert not ({'backend', 'path', 'config'} & tool['inputSchema']['properties'].keys())


def test_real_check_score_plan_submit(keys, monkeypatch):
    import articulate.editing
    def forbidden(*args, **kwargs):
        raise AssertionError('backend route must never run')
    monkeypatch.setattr(articulate.editing, 'run_edit', forbidden)
    with client(keys) as c:
        auth = token(keys)
        text = 'The result is 42.'
        assert 'verdict' in data(call(c, auth, 'check', text=text))
        assert data(call(c, auth, 'score', text=text))['words'] > 0
        plan = data(call(c, auth, 'edit_plan', text=text))
        assert plan['status'] == 'host_edit_required'
        result = data(call(c, auth, 'edit_submit', text=text, rewrite=text, plan_id=plan['plan_id']))
        assert result['text'] == text
        assert result['receipt']['backend'] == 'host'


@pytest.mark.parametrize('arguments', [
    {'text': 'hello', 'backend': 'openai'}, {'text': 'hello', 'path': '/etc/passwd'},
    {'text': 123}, {'text': 'x' * 101}, {'text': 'hello', 'profile': {'slop': 'off'}},
])
def test_bad_arguments_fail_without_echo(keys, arguments):
    with client(keys, max_chars=100) as c:
        r = rpc(c, token(keys), 'tools/call', {'name': 'check', 'arguments': arguments})
    assert r.status_code == 400
    assert 'hello' not in r.text


def test_request_byte_limit(keys):
    with client(keys, max_body_bytes=512) as c:
        r = rpc(c, token(keys), 'tools/call', {'name': 'check', 'arguments': {'text': 'x' * 600}})
    assert r.status_code == 413


def test_rate_limit(keys):
    with client(keys, requests_per_minute=2) as c:
        assert rpc(c, token(keys)).status_code == 200
        assert rpc(c, token(keys)).status_code == 200
        assert rpc(c, token(keys)).status_code == 429


def test_no_text_in_logs_or_raw_error(keys, caplog, monkeypatch):
    from articulate import mcp_server
    secret = 'unique private submitted passage'
    def fail(text, **kwargs):
        logging.getLogger('unexpected.library').warning('body=%s', text)
        raise RuntimeError(text)
    monkeypatch.setattr(mcp_server, 'do_check', fail)
    with client(keys) as c, caplog.at_level(logging.DEBUG):
        result = call(c, token(keys), 'check', text=secret)
        invalid = rpc(c, token(keys), 'tools/call', {'name': 'check', 'arguments': {'text': {'body': secret}}})
    assert secret not in json.dumps(result)
    assert secret not in invalid.text
    assert secret not in caplog.text


def test_chunked_body_limit_without_content_length(keys):
    with client(keys, max_body_bytes=512) as c:
        r = c.post('/mcp', content=iter([b'x' * 300, b'x' * 300]), headers={
            'Authorization': 'Bearer ' + token(keys), 'Content-Type': 'application/json',
            'Accept': 'application/json, text/event-stream'})
    assert r.status_code == 413


def test_distinct_asgi_chunks_stop_reading_at_byte_limit(keys):
    # HTTPX's synchronous transport may coalesce iterator content. Drive the
    # actual ASGI app with distinct receive events to verify the streaming cap.
    with client(keys, max_body_bytes=512) as c:
        received, sent = [], []
        async def receive():
            received.append(True)
            assert len(received) <= 2, 'read continued after crossing the bound'
            return {'type': 'http.request', 'body': b'x' * 300, 'more_body': True}
        async def send(message):
            sent.append(message)
        scope = {'type': 'http', 'method': 'POST', 'path': '/mcp', 'headers': []}
        c.portal.call(c.app, scope, receive, send)
    assert len(received) == 2
    assert sent[0]['status'] == 413


def test_slow_body_times_out_and_releases_concurrency_slot(keys):
    with client(keys, read_timeout=1, max_concurrent=1) as c:
        sent = []
        async def receive():
            await asyncio.Event().wait()
        async def send(message):
            sent.append(message)
        scope = {'type': 'http', 'method': 'POST', 'path': '/mcp', 'headers': []}
        c.portal.call(c.app, scope, receive, send)
        assert sent[0]['status'] == 408
        assert rpc(c, token(keys)).status_code == 200


@pytest.mark.parametrize('headers, body, status', [
    ({'Content-Encoding': 'gzip'}, b'not a gzip body', 415),
    ({'Content-Length': '-1'}, b'{}', 413),
    ({'Content-Length': 'invalid'}, b'{}', 400),
    ({}, b'not JSON', 400),
    ({}, b'[]', 400),
])
def test_bad_http_bodies_fail_closed(keys, headers, body, status):
    with client(keys) as c:
        response = c.post('/mcp', content=body, headers=headers)
    assert response.status_code == status
    assert response.json() == {'error': 'Request rejected'}
    assert response.headers['cache-control'] == 'no-store'


def test_concurrency_limit(keys, monkeypatch):
    from articulate import mcp_server
    entered, release = Event(), Event()
    original = mcp_server.do_score
    def wait_score(text):
        entered.set()
        assert release.wait(5)
        return original(text)
    monkeypatch.setattr(mcp_server, 'do_score', wait_score)
    with client(keys, max_concurrent=1) as c, ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(call, c, token(keys), 'score', text='A short sentence.')
        try:
            assert entered.wait(5)
            assert rpc(c, token(keys)).status_code == 429
        finally:
            release.set()
        assert data(future.result())['words'] > 0


def test_forged_plan_cannot_supply_custom_settings(keys):
    from articulate.host_edit import edit_plan
    text = 'Preserve 42.'
    plan = edit_plan(text, profile={'slop': 'off', 'keep': ['arbitrary']})
    with client(keys) as c:
        result = data(call(c, token(keys), 'edit_submit', text=text, rewrite=text,
                           plan_id=plan['plan_id']))
    assert result['ok'] is False
    assert 'arbitrary' not in json.dumps(result)


@pytest.mark.parametrize('name', ['rfc-keywords', 'ux-microcopy', 'plain-language'])
def test_domain_profile_plan_round_trips(keys, name):
    text = 'The client MUST retry. The server should log 42 errors.'
    with client(keys) as c:
        auth = token(keys)
        plan = data(call(c, auth, 'edit_plan', text=text, profile=name))
        assert plan['status'] == 'host_edit_required'
        result = data(call(c, auth, 'edit_submit', text=text, rewrite=text, plan_id=plan['plan_id']))
    assert result.get('ok') is not False, result
    assert result['text'] == text
    assert result['receipt']['settings']['profile']['domain'] == name


def test_altered_domain_profile_is_still_rejected(keys):
    from articulate import domains
    from articulate.host_edit import edit_plan
    text = 'Preserve 42.'
    prof = domains.load_profile('rfc-keywords')
    prof['rule_packs'] = ()
    plan = edit_plan(text, profile=prof)
    with client(keys) as c:
        result = data(call(c, token(keys), 'edit_submit', text=text, rewrite=text,
                           plan_id=plan['plan_id']))
    assert result['ok'] is False


def test_results_are_not_cacheable(keys):
    with client(keys) as c:
        r = rpc(c, token(keys))
    assert r.headers['cache-control'] == 'no-store'


def test_malformed_protocol_payload_does_not_echo_body(keys, caplog):
    secret = 'private invalid initialize payload'
    with client(keys) as c, caplog.at_level(logging.DEBUG):
        r = rpc(c, token(keys), 'initialize', {'protocolVersion': {'secret': secret}})
    assert secret not in r.text
    assert secret not in caplog.text


def test_local_configuration_and_backend_are_never_used(keys, monkeypatch):
    from articulate import backends
    import subprocess
    def forbidden(*args, **kwargs):
        pytest.fail('Hosted tool attempted a backend or subprocess')
    monkeypatch.setattr(backends, 'complete', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setenv('ARTICULATE_BACKEND', 'claude')
    with client(keys) as c:
        for name in ('check', 'score', 'edit_plan'):
            assert 'error' not in data(call(c, token(keys), name, text='A short sentence.'))


@pytest.mark.parametrize('limit, connections', [(1, 1), (4, 4)])
def test_uvicorn_idle_connections_do_not_bypass_request_boundary(keys, monkeypatch, limit, connections):
    import uvicorn
    from uvicorn.protocols.http.h11_impl import H11Protocol
    from uvicorn.server import ServerState
    from articulate import hosted_mcp

    captured = {}
    monkeypatch.setattr(hosted_mcp.HostedConfig, 'from_env',
                        classmethod(lambda cls: config(keys, max_concurrent=limit)))
    def capture(app, **kwargs):
        captured.update(app=app, options=kwargs)
    # Capture the real entrypoint's options; no socket or listener is created.
    monkeypatch.setattr(uvicorn, 'run', capture)
    hosted_mcp.main()

    class MemoryTransport(asyncio.Transport):
        def __init__(self):
            self.output = bytearray()
            self.closed = False
        def get_extra_info(self, name, default=None):
            return default
        def is_closing(self):
            return self.closed
        def close(self):
            self.closed = True
        def write(self, data):
            self.output.extend(data)
        def pause_reading(self):
            pass
        def resume_reading(self):
            pass

    async def exercise():
        app = captured['app']
        uvconfig = uvicorn.Config(app, **captured['options'])
        uvconfig.load()
        state = ServerState()
        protocols = []
        async with app.lifespan(app):
            try:
                for _ in range(connections):
                    protocol = H11Protocol(uvconfig, state, {})
                    transport = MemoryTransport()
                    protocol.connection_made(transport)
                    protocols.append(protocol)
                body = b'{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
                request = (b'POST /mcp HTTP/1.1\r\nHost: articulate.example\r\n'
                           b'Content-Type: application/json\r\n'
                           b'Accept: application/json, text/event-stream\r\n'
                           b'Authorization: Bearer ' + token(keys).encode() +
                           b'\r\nContent-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body)
                protocols[-1].data_received(request)
                await asyncio.gather(*list(state.tasks))
                response = bytes(transport.output)
                assert response.startswith(b'HTTP/1.1 200'), response
                assert b'cache-control: no-store' in response.lower()
                assert b'edit_submit' in response
            finally:
                for protocol in protocols:
                    protocol.connection_lost(None)
    asyncio.run(exercise())
