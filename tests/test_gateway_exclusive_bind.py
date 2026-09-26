"""N-23, N-24: a second socket cannot take the gateway's port while it runs.

Experiment X3 showed the plain ThreadingHTTPServer lets a same-user socket
with SO_REUSEADDR bind the listening port on Windows. The control below keeps
that finding reproducible, so the exclusive test cannot pass for the wrong
reason.
"""
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from harness.gateway_bind import ExclusiveThreadingHTTPServer

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows bind semantics")


def _second_bind(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


@windows_only
def test_a_reuseaddr_socket_cannot_bind_the_exclusive_gateway_port():
    server = ExclusiveThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    try:
        assert _second_bind(server.server_address[1]) is False
    finally:
        server.server_close()


@windows_only
def test_control_the_plain_server_lets_a_reuseaddr_socket_take_the_port():
    server = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    try:
        assert _second_bind(server.server_address[1]) is True
    finally:
        server.server_close()


def test_the_exclusive_server_still_serves_and_reports_its_bound_address():
    server = ExclusiveThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    try:
        host, port = server.server_address[:2]
        assert host == "127.0.0.1" and port > 0
        if sys.platform == "win32":
            assert server.allow_reuse_address is False
    finally:
        server.server_close()
