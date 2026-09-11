"""Single-send HTTP for finite, trusted loopback test requests.

An early refusal can close an HTTP/1.0 connection before urllib sends its
separate POST body. On Windows that late write can abort the pending 401
read (WinError 10053). Stage these small fixture requests together, keeping
the real server, response parser, and all transport exceptions observable.
This is not a streaming client or a production HTTP transport.
"""
import http.client
import math
import socket


def request(port, path, *, data=None, headers=None, timeout=3):
    """Send exactly once; return the actual status/body, with no retries."""
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or timeout <= 0):
        raise ValueError('timeout must be a finite positive number')
    method = 'GET' if data is None else 'POST'
    body = data or b''
    fields = {'Host': f'127.0.0.1:{port}', 'Connection': 'close',
              'Content-Length': str(len(body)), **(headers or {})}
    head = f'{method} {path} HTTP/1.1\r\n'
    head += ''.join(f'{key}: {value}\r\n' for key, value in fields.items())
    wire = (head + '\r\n').encode('ascii') + body
    with socket.create_connection(('127.0.0.1', port), timeout=timeout) as conn:
        conn.sendall(wire)
        with http.client.HTTPResponse(conn) as response:
            response.begin()
            return response.status, response.read().decode()
