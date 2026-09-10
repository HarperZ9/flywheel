"""The finite loopback client must not hide failures or retry actions."""
import http.client
import io

import pytest

from tests.http_fixture_client import request


class Socket:
    def __init__(self, response, error=None):
        self.response = response
        self.error = error
        self.sent = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def sendall(self, data):
        self.sent.append(data)
        if self.error:
            raise self.error

    def makefile(self, *args):
        return io.BytesIO(self.response)


def socket_for(monkeypatch, response, error=None):
    sock = Socket(response, error)
    connections = []

    def connect(address, timeout):
        connections.append((address, timeout))
        return sock

    monkeypatch.setattr('tests.http_fixture_client.socket.create_connection', connect)
    return sock, connections


def test_headers_and_body_share_one_send_and_401_is_preserved(monkeypatch):
    sock, connections = socket_for(monkeypatch,
        b'HTTP/1.0 401 Unauthorized\r\nContent-Length: 2\r\n\r\n{}')
    assert request(8799, '/api/auth/login', data=b'{"provider":"openai"}',
                   headers={'Authorization': 'Bearer synthetic'}) == (401, '{}')
    assert connections == [(('127.0.0.1', 8799), 3)]
    assert len(sock.sent) == 1
    head, body = sock.sent[0].split(b'\r\n\r\n', 1)
    assert head.startswith(b'POST /api/auth/login HTTP/1.1\r\n')
    assert b'Content-Length: 21' in head
    assert b'Authorization: Bearer synthetic' in head
    assert body == b'{"provider":"openai"}'


@pytest.mark.parametrize(('wire', 'exception'), [
    (b'', http.client.RemoteDisconnected),
    (b'not HTTP\r\n', http.client.BadStatusLine),
    (b'HTTP/1.0 200 OK\r\nContent-Length: 4\r\n\r\nx', http.client.IncompleteRead),
])
def test_broken_responses_propagate_without_retry(monkeypatch, wire, exception):
    sock, connections = socket_for(monkeypatch, wire)
    with pytest.raises(exception):
        request(8799, '/api/auth')
    assert len(connections) == len(sock.sent) == 1


def test_socket_abort_propagates_without_retry(monkeypatch):
    sock, connections = socket_for(monkeypatch, b'', ConnectionAbortedError(10053, 'synthetic'))
    with pytest.raises(ConnectionAbortedError):
        request(8799, '/api/auth/login', data=b'{}')
    assert len(connections) == len(sock.sent) == 1


def test_unexpected_status_is_not_translated_to_success(monkeypatch):
    socket_for(monkeypatch, b'HTTP/1.0 503 Unavailable\r\nContent-Length: 4\r\n\r\noops')
    assert request(8799, '/api/auth') == (503, 'oops')
