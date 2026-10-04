"""The Rowan TTS server reads a POST body before it answers.

A Windows socket closed with unread received bytes sends a reset, and the
reset can discard a response the client has not read yet. The cancel route
ignores its body, so it answered and closed while "{}" was still in flight,
and test_missing_cancel_reports_not_found failed on a Windows runner with
WinError 10053. These tests hold the body back and check that no answer
arrives until the declared bytes are read.
"""
from __future__ import annotations

import json
import socket
from pathlib import Path

from test_rowan_local_tts_service import _Server


def _headers(server: _Server, path: str, length: int) -> bytes:
    return (
        f"POST {path} HTTP/1.1\r\nHost: 127.0.0.1:{server.port}\r\n"
        f"Authorization: Bearer {server.token}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {length}\r\nConnection: close\r\n\r\n"
    ).encode("ascii")


def _read_all(sock: socket.socket) -> bytes:
    chunks = []
    while chunk := sock.recv(65536):
        chunks.append(chunk)
    return b"".join(chunks)


def _held_body_exchange(server: _Server, path: str) -> tuple[bytes, bytes]:
    body = b"{}"
    with socket.create_connection(("127.0.0.1", server.port), timeout=5) as sock:
        sock.sendall(_headers(server, path, len(body)))
        sock.settimeout(0.3)
        try:
            early = sock.recv(65536)
        except TimeoutError:
            early = b""
        sock.settimeout(5)
        sock.sendall(body)
        return early, early + _read_all(sock)


def test_cancel_route_waits_for_the_declared_body(tmp_path: Path):
    with _Server(tmp_path) as server:
        early, reply = _held_body_exchange(server, "/v1/jobs/tts_missing/cancel")
    assert early == b"", "the server answered before reading the request body"
    head, _, payload = reply.partition(b"\r\n\r\n")
    assert head.startswith(b"HTTP/1.0 404")
    assert json.loads(payload)["code"] == "JOB_NOT_FOUND"


def test_unauthenticated_post_also_waits_for_the_declared_body(tmp_path: Path):
    with _Server(tmp_path) as server:
        server.token = "wrong-token"
        early, reply = _held_body_exchange(server, "/v1/stop")
    assert early == b"", "the server answered before reading the request body"
    assert reply.startswith(b"HTTP/1.0 401")
