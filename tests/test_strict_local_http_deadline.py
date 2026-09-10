"""Absolute socket deadlines, including header and body trickle controls."""
import socket
import time

import pytest

from harness.strict_local_http import StrictLocalHTTPPolicy, make_strict_local_http
from tests.strict_local_http_fixtures import server


@pytest.mark.parametrize('mode', ['stalled_headers', 'stalled_body', 'trickle_headers', 'trickle_body', 'trickle_chunk'])
def test_absolute_deadline_cannot_be_reset_by_partial_receives(mode):
    def respond(sock, row, stop):
        if mode == 'stalled_headers':
            stop.wait(3)
            return
        if mode == 'trickle_headers':
            sock.sendall(b'HTTP/1.1 200 OK\r\nX-Slow: ')
        elif mode == 'trickle_chunk':
            sock.sendall(b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n')
        else:
            sock.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 1000\r\n\r\n')
        if mode == 'stalled_body':
            stop.wait(3)
            return
        while not stop.wait(0.03):
            sock.sendall(b'1\r\nx\r\n' if mode == 'trickle_chunk' else b'x')

    with server(respond) as fixture:
        call = make_strict_local_http(StrictLocalHTTPPolicy(
            fixture.origin, frozenset({('GET', '/health')}), max_timeout_seconds=0.2))
        started = time.monotonic()
        with pytest.raises(TimeoutError, match='deadline_exceeded'):
            call('GET', fixture.origin + '/health', None, 10)
        elapsed = time.monotonic() - started
        assert 0.1 <= elapsed < 0.9, (mode, elapsed)
        assert len(fixture.connections) == len(fixture.requests) == 1


def test_caller_can_shorten_but_not_extend_deadline():
    with server(lambda sock, row, stop: stop.wait(3)) as fixture:
        call = make_strict_local_http(StrictLocalHTTPPolicy(
            fixture.origin, frozenset({('GET', '/health')}), max_timeout_seconds=10))
        started = time.monotonic()
        with pytest.raises(TimeoutError):
            call('GET', fixture.origin + '/health', None, 0.15)
        assert time.monotonic() - started < 0.85
        assert len(fixture.connections) == 1


def test_send_to_nonreading_receiver_has_same_absolute_deadline(monkeypatch):
    from harness import strict_local_http as module
    original_init = module._DeadlineSocket.__init__

    def small_buffer(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024)

    monkeypatch.setattr(module._DeadlineSocket, '__init__', small_buffer)
    with server(read_request=False) as fixture:
        call = make_strict_local_http(StrictLocalHTTPPolicy(
            fixture.origin, frozenset({('POST', '/generate')}),
            max_request_bytes=4 << 20, max_timeout_seconds=0.2))
        started = time.monotonic()
        with pytest.raises(TimeoutError, match='deadline_exceeded'):
            call('POST', fixture.origin + '/generate', b'x' * (4 << 20), 10)
        assert time.monotonic() - started < 0.9
        assert len(fixture.connections) == 1
        assert not fixture.requests  # Receiver accepted TCP but never read HTTP.
