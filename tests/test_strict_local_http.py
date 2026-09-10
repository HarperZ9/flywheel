"""Strict transport boundaries measured at owned receiving fixtures."""
import json
import socket
import sys
import threading

import pytest

from harness.model_endpoint_gate_cli import build_report
from harness.strict_local_http import StrictLocalHTTPPolicy, make_strict_local_http
from tests.model_endpoint_gate_fixtures import profile, write_profiles
from tests.strict_local_http_fixtures import gate_response, response, server


def transport(origin, **kwargs):
    return make_strict_local_http(StrictLocalHTTPPolicy(
        origin, frozenset({('GET', '/health'), ('POST', '/generate')}), **kwargs))


@pytest.mark.parametrize('backend', ['serve', 'ollama'])
def test_same_transport_injection_reaches_health_and_generation_once(tmp_path, backend):
    with server(gate_response) as fixture:
        paths = ('/health', '/generate') if backend == 'serve' else ('/api/tags', '/api/chat')
        selected = profile(backend)
        selected['endpoint_url'] = fixture.origin
        call = make_strict_local_http(StrictLocalHTTPPolicy(
            fixture.origin, frozenset({('GET', paths[0]), ('POST', paths[1])})))
        report = build_report(profile_artifact=str(write_profiles(tmp_path, [selected])),
                              models=[], backends=[], transport=call, timeout_seconds=2)
        assert report['verdict'] == 'MODEL_ENDPOINT_GATE_PASS'
        assert [(row['method'], row['path']) for row in fixture.requests] == [('GET', paths[0]), ('POST', paths[1])]
        assert len(fixture.connections) == 2
        assert json.loads(fixture.requests[1]['body'])


@pytest.mark.parametrize('suffix', ['/other', '/health?x=1', '/health#x', '/%68ealth', '//health', '/./health'])
def test_unapproved_path_is_rejected_before_connection(suffix):
    with server() as fixture:
        with pytest.raises(OSError, match='route_not_allowed'):
            transport(fixture.origin)('GET', fixture.origin + suffix, None, 1)
        assert not fixture.connections


def test_origin_port_method_and_credentials_cannot_change():
    with server() as allowed, server() as other:
        call = transport(allowed.origin)
        for method, url in [('GET', other.origin + '/health'), ('POST', allowed.origin + '/health'),
                            ('GET', allowed.origin.replace('http://', 'http://user:secret@') + '/health')]:
            with pytest.raises(OSError, match='route_not_allowed'):
                call(method, url, None, 1)
        assert not allowed.connections and not other.connections


@pytest.mark.parametrize('origin', ['http://localhost:80', 'https://127.0.0.1:80', 'http://127.1:80',
    'http://127.0.0.1', 'http://127.0.0.1:80/', 'http://192.0.2.1:80', 'http://127.0.0.1:80?x'])
def test_policy_requires_canonical_numeric_http_loopback_origin(origin):
    with pytest.raises(ValueError):
        StrictLocalHTTPPolicy(origin, frozenset({('GET', '/health')}))


def test_policy_deep_freezes_routes():
    routes = {('GET', '/health')}
    policy = StrictLocalHTTPPolicy('http://127.0.0.1:80', routes)
    routes.add(('POST', '/generate'))
    assert policy.allowed_routes == frozenset({('GET', '/health')})


@pytest.mark.parametrize('value', [True, 0, -1, float('nan'), float('inf'), 10 ** 500])
def test_invalid_timeouts_never_connect(value):
    with server() as fixture:
        with pytest.raises(ValueError):
            transport(fixture.origin, max_timeout_seconds=value)
        with pytest.raises(OSError, match='invalid_timeout'):
            transport(fixture.origin)('GET', fixture.origin + '/health', None, value)
        assert not fixture.connections


def test_request_cap_fails_before_io():
    with server() as fixture:
        with pytest.raises(OSError, match='request_too_large'):
            transport(fixture.origin, max_request_bytes=8)('POST', fixture.origin + '/generate', b'x' * 9, 1)
        assert not fixture.connections


@pytest.mark.parametrize('status', [200, 500])
def test_success_and_error_response_wire_caps(status):
    with server(lambda sock, *_: sock.sendall(response(b'{"error":"' + b'x' * 2000 + b'"}', status))) as fixture:
        with pytest.raises(OSError, match='response_too_large'):
            transport(fixture.origin, max_response_bytes=256)('GET', fixture.origin + '/health', None, 1)
        assert len(fixture.requests) == len(fixture.connections) == 1


def test_header_bytes_count_toward_response_cap():
    with server(lambda sock, *_: sock.sendall(response(headers=b'X-Large: ' + b'x' * 1024 + b'\r\n'))) as fixture:
        with pytest.raises(OSError, match='response_too_large'):
            transport(fixture.origin, max_response_bytes=256)('GET', fixture.origin + '/health', None, 1)
        assert len(fixture.requests) == 1


def test_redirect_and_environment_proxy_produce_no_second_request(monkeypatch):
    with server() as target, server() as proxy:
        def redirect(sock, *_):
            sock.sendall(response(status=302, headers=f'Location: {target.origin}/health\r\n'.encode()))
        with server(redirect) as fixture:
            for name in ('http_proxy', 'HTTP_PROXY', 'https_proxy', 'HTTPS_PROXY', 'ALL_PROXY', 'all_proxy'):
                monkeypatch.setenv(name, proxy.origin)
            monkeypatch.setenv('NO_PROXY', '')
            monkeypatch.setenv('no_proxy', '')
            with pytest.raises(OSError, match='redirect_not_allowed'):
                transport(fixture.origin)('GET', fixture.origin + '/health', None, 1)
            assert len(fixture.requests) == len(fixture.connections) == 1
            assert not target.connections and not proxy.connections


@pytest.mark.parametrize('raw', [b'', b'NOT HTTP\r\n\r\n', response(b'{"ok":true,"ok":false}'),
                                response(b'{"error":"\xff"}'), response(b'[]'),
                                b'HTTP/1.1 200 OK\r\nContent-Length: 20\r\n\r\n{}'])
def test_malformed_and_early_eof_responses_have_fixed_safe_errors(raw):
    with server(lambda sock, *_: sock.sendall(raw)) as fixture:
        with pytest.raises(OSError) as caught:
            transport(fixture.origin)('GET', fixture.origin + '/health', None, 1)
        assert str(caught.value) in {'invalid_http_response', 'invalid_json_response'}
        assert len(fixture.connections) == 1


def test_chunked_response_and_connection_close_remain_supported():
    raw = b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\nb\r\n{"ok":true}\r\n0\r\n\r\n'
    with server(lambda sock, *_: sock.sendall(raw)) as fixture:
        assert transport(fixture.origin)('GET', fixture.origin + '/health', None, 1) == (200, {'ok': True})
        assert len(fixture.connections) == 1


def test_numeric_connection_does_not_invoke_resolver(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('resolver must not be reached')

    with server() as fixture:
        monkeypatch.setattr(socket, 'getaddrinfo', denied)
        assert transport(fixture.origin)('GET', fixture.origin + '/health', None, 1)[0] == 200
        assert len(fixture.connections) == 1


@pytest.mark.parametrize('cap', [True, 0, -1, 1.5, float('nan')])
@pytest.mark.parametrize('name', ['max_request_bytes', 'max_response_bytes'])
def test_caps_are_positive_integers(name, cap):
    with pytest.raises(ValueError):
        transport('http://127.0.0.1:80', **{name: cap})


@pytest.mark.parametrize('limits', [
    {'max_timeout_seconds': 1e308},
    {'max_timeout_seconds': threading.TIMEOUT_MAX + 1},
    {'max_response_bytes': sys.maxsize},
    {'max_request_bytes': sys.maxsize},
])
def test_policy_rejects_bounds_outside_platform_representable_range(limits):
    with pytest.raises(ValueError, match='invalid_strict_local_http_policy'):
        transport('http://127.0.0.1:80', **limits)


def test_huge_finite_caller_timeout_is_shortened_to_safe_policy():
    with server() as fixture:
        assert transport(fixture.origin)('GET', fixture.origin + '/health', None, 1e308)[0] == 200
        assert len(fixture.requests) == 1


def test_threading_limit_is_not_assumed_to_be_a_socket_timeout_limit():
    with server() as fixture:
        with pytest.raises(ValueError, match='invalid_strict_local_http_policy'):
            transport(fixture.origin, max_timeout_seconds=threading.TIMEOUT_MAX)(
                'GET', fixture.origin + '/health', None, threading.TIMEOUT_MAX)
        assert not fixture.connections


def test_largest_admitted_timeout_cap_is_one_day():
    with pytest.raises(ValueError):
        transport('http://127.0.0.1:80', max_timeout_seconds=86401)
    with server() as fixture:
        assert transport(fixture.origin, max_timeout_seconds=86400)(
            'GET', fixture.origin + '/health', None, 1e308)[0] == 200


def test_platform_overflow_is_normalized_with_progression(monkeypatch):
    from harness import strict_local_http as module

    def overflow(*args):
        raise OverflowError('private-platform-canary')

    monkeypatch.setattr(module._DeadlineSocket, 'settimeout', overflow)
    with server() as fixture:
        with pytest.raises(OSError, match='^invalid_transport_limit$') as caught:
            transport(fixture.origin)('GET', fixture.origin + '/health', None, 1)
        assert not caught.value.terminal_event['connection_started']
        assert not caught.value.terminal_event['request_send_started']
        assert not fixture.connections
