"""Frozen request authority and budgets measured at an owned HTTP fixture."""
import io
import json
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from harness.gateway_agent_transport import AgentTransportError, BoundAgentTransport


@contextmanager
def server(response=b'{"model":"selected","usage":{"tokens":3}}', status=200,
           chunk_delay=None):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            requests.append((self.path, dict(self.headers),
                             self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(status)
            if status == 302:
                self.send_header('Location', '/redirected')
            self.send_header('Content-Length', str(len(response)))
            self.end_headers()
            try:
                if chunk_delay is None:
                    self.wfile.write(response)
                else:
                    for byte in response:
                        self.wfile.write(bytes([byte]))
                        self.wfile.flush()
                        time.sleep(chunk_delay)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

    fixture = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=fixture.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{fixture.server_port}', requests
    finally:
        fixture.shutdown()
        fixture.server_close()
        thread.join(timeout=2)


def transport(base_url, **overrides):
    options = dict(base_url=base_url, adapter='openai', model='selected',
                   deadline=time.monotonic() + 5, max_tokens=32, max_calls=2)
    options.update(overrides)
    return BoundAgentTransport(**options)


def body(**overrides):
    payload = dict(model='selected', max_tokens=32, messages=[], temperature=0)
    payload.update(overrides)
    return json.dumps(payload).encode()


def send(call, base_url, payload=None, **kwargs):
    return call(kwargs.get('method', 'POST'),
                kwargs.get('url', base_url + '/chat/completions'),
                kwargs.get('headers', {'Content-Type': 'application/json'}),
                body() if payload is None else payload, kwargs.get('timeout', 3))


def test_exact_payload_and_response_preserved_without_ambient_proxy(monkeypatch):
    monkeypatch.setenv('http_proxy', 'http://127.0.0.1:1')
    monkeypatch.setenv('HTTP_PROXY', 'http://127.0.0.1:1')
    monkeypatch.setenv('no_proxy', '')
    monkeypatch.setenv('NO_PROXY', '')
    with server() as (origin, requests):
        payload = body(temperature=0)
        status, response = send(transport(origin), origin, payload,
                                headers={'Authorization': 'Bearer synthetic',
                                         'Content-Type': 'application/json'})
    assert status == 200
    assert response == {'model': 'selected', 'usage': {'tokens': 3}}
    assert requests[0][0] == '/chat/completions'
    assert requests[0][2] == payload
    assert requests[0][1]['Authorization'] == 'Bearer synthetic'


@pytest.mark.parametrize('mutation', [
    {'model': 'other'}, {'max_tokens': 31}, {'max_tokens': 33},
    {'max_tokens': True}, {'stream': True}, {'n': 2}, {'max_completion_tokens': 99},
])
def test_changed_selection_or_output_authority_never_reaches_server(mutation):
    payload = dict(model='selected', max_tokens=32, messages=[], temperature=0)
    payload.update(mutation)
    with server() as (origin, requests):
        with pytest.raises(AgentTransportError, match='AGENT_BINDING_DRIFT'):
            send(transport(origin), origin, json.dumps(payload).encode())
        assert requests == []


@pytest.mark.parametrize('suffix', ['/other', '/chat/completions?key=secret',
                                     '/chat/completions#fragment'])
def test_route_drift_is_rejected_before_request(suffix):
    with server() as (origin, requests):
        with pytest.raises(AgentTransportError, match='AGENT_BINDING_DRIFT'):
            send(transport(origin), origin, url=origin + suffix)
        assert not requests


@pytest.mark.parametrize('headers', [{'Host': 'other.example'},
                                     {'Proxy-Authorization': 'synthetic'}])
def test_routing_headers_cannot_override_frozen_origin(headers):
    headers = {'Content-Type': 'application/json', **headers}
    with server() as (origin, requests):
        with pytest.raises(AgentTransportError, match='AGENT_BINDING_DRIFT'):
            send(transport(origin), origin, headers=headers)
        assert not requests


def test_redirect_is_not_followed():
    with server(status=302) as (origin, requests):
        with pytest.raises(AgentTransportError, match='EXTERNAL_ACTION_FAILED'):
            send(transport(origin), origin)
        assert len(requests) == 1
        assert requests[0][0] == '/chat/completions'


def test_attempt_budget_includes_unsuccessful_http_response():
    with server(b'{"error":"synthetic"}', status=400) as (origin, requests):
        call = transport(origin, max_calls=1)
        assert send(call, origin) == (400, {'error': 'synthetic'})
        with pytest.raises(AgentTransportError, match='AGENT_BINDING_DRIFT'):
            send(call, origin)
        assert call.calls == len(requests) == 1


@pytest.mark.parametrize('response', [b'{"x":NaN}', b'{"x":1e999}',
                                      b'{"x":1,"x":2}', b'[]', b'not-json'])
def test_response_must_be_finite_unambiguous_json_object(response):
    with server(response) as (origin, _):
        with pytest.raises(AgentTransportError, match='EXTERNAL_ACTION_FAILED'):
            send(transport(origin), origin)


def test_response_byte_cap():
    with server(b' ' * ((2 << 20) + 1)) as (origin, requests):
        with pytest.raises(AgentTransportError, match='EXTERNAL_ACTION_FAILED'):
            send(transport(origin), origin)
        assert len(requests) == 1


def test_request_byte_cap_and_nonfinite_json_stop_before_connection():
    with server() as (origin, requests):
        for payload in (b' ' * ((1 << 20) + 1),
                        b'{"model":"selected","max_tokens":32,"x":NaN}'):
            with pytest.raises(AgentTransportError, match='AGENT_BINDING_DRIFT'):
                send(transport(origin), origin, payload)
        assert not requests


def test_expired_deadline_prevents_connection():
    with server() as (origin, requests):
        call = transport(origin, deadline=10, clock=lambda: 10)
        with pytest.raises(AgentTransportError) as error:
            send(call, origin)
        assert error.value.code == 'OPERATION_DEADLINE_EXCEEDED'
        assert call.calls == 0
        assert not requests


def test_slow_real_http_response_cannot_extend_aggregate_deadline():
    from tests.test_gateway_agent_transport_dribble import ControlledDribble, run_dribble

    with ControlledDribble() as fixture:
        call, error = run_dribble(fixture)
        fixture.assert_expired_after_reads(call, error)


@pytest.mark.parametrize('missing', ['model', 'max_tokens'])
def test_dropped_selection_and_cap_fail_before_network(missing):
    payload = dict(model='selected', max_tokens=32, messages=[], temperature=0)
    del payload[missing]
    with server() as (origin, requests):
        with pytest.raises(AgentTransportError, match='AGENT_BINDING_DRIFT'):
            send(transport(origin), origin, json.dumps(payload).encode())
        assert not requests


def test_other_origin_or_method_cannot_reuse_authorized_transport():
    with server() as (origin, requests), server() as (other, other_requests):
        call = transport(origin)
        for change in ({'url': other + '/chat/completions'}, {'method': 'GET'}):
            with pytest.raises(AgentTransportError, match='AGENT_BINDING_DRIFT'):
                send(call, origin, **change)
        assert not requests and not other_requests


@pytest.mark.parametrize('config', [{}, {'maxOutputTokens': 64},
                                    {'maxOutputTokens': 32, 'candidateCount': 2}])
def test_gemini_generation_budget_cannot_drift(config):
    with server() as (origin, requests):
        with pytest.raises(AgentTransportError, match='AGENT_BINDING_DRIFT'):
            send(transport(origin, adapter='gemini'), origin,
                 json.dumps({'contents': [], 'generationConfig':
                             {'temperature': 0, **config}}).encode(),
                 url=origin + '/models/selected:generateContent')
        assert not requests


def test_deadline_is_checked_after_each_response_chunk():
    now = [0.0]

    class Response(io.BytesIO):
        status = 200
        headers = {}

        def read1(self, count):
            now[0] = 11
            return super().read1(count)

    class Opener:
        def open(self, request, timeout):
            assert timeout == 3
            return Response(b'{}')

    call = transport('http://127.0.0.1:1', deadline=10,
                     clock=lambda: now[0], opener=Opener())
    with pytest.raises(AgentTransportError, match='OPERATION_DEADLINE_EXCEEDED'):
        send(call, 'http://127.0.0.1:1')


@pytest.mark.parametrize('adapter,suffix,payload', [
    ('anthropic', '/v1/messages', body()),
    ('gemini', '/models/selected:generateContent',
     b'{"contents":[],"generationConfig":{"temperature":0,"maxOutputTokens":32}}'),
])
def test_native_adapter_exact_routes_and_output_caps(adapter, suffix, payload):
    headers = ({'x-api-key': 'synthetic', 'anthropic-version': '2023-06-01'}
               if adapter == 'anthropic' else {'x-goog-api-key': 'synthetic'})
    headers['Content-Type'] = 'application/json'
    with server() as (origin, requests):
        send(transport(origin, adapter=adapter), origin, payload,
             url=origin + suffix, headers=headers)
        assert requests[0][0] == suffix
        assert requests[0][2] == payload


def test_network_error_never_exposes_raw_diagnostics():
    class Opener:
        def open(self, *args, **kwargs):
            raise OSError('secret credential URL and upstream details')

    with pytest.raises(AgentTransportError) as error:
        send(transport('http://127.0.0.1:1', opener=Opener()), 'http://127.0.0.1:1')
    assert str(error.value) == error.value.code == 'EXTERNAL_ACTION_FAILED'


@pytest.mark.parametrize('deadline,expected', [
    (1, 'OPERATION_DEADLINE_EXCEEDED'), (10, 'EXTERNAL_ACTION_FAILED')])
def test_socket_timer_uses_selected_limit_even_before_clock_tick(deadline, expected):
    class Opener:
        def open(self, *args, **kwargs):
            raise TimeoutError('synthetic socket timer')

    call = transport('http://127.0.0.1:1', deadline=deadline,
                     clock=lambda: 0, opener=Opener())
    with pytest.raises(AgentTransportError, match=expected):
        send(call, 'http://127.0.0.1:1')


def test_gemini_model_path_component_is_quoted_exactly():
    with server() as (origin, requests):
        call = transport(origin, adapter='gemini', model='publisher/model:tag')
        payload = b'{"contents":[],"generationConfig":{"temperature":0,"maxOutputTokens":32}}'
        suffix = '/models/publisher%2Fmodel%3Atag:generateContent'
        send(call, origin, payload, url=origin + suffix)
        assert requests[0][0] == suffix
