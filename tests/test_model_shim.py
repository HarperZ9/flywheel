"""Falsifier for harness/model_shim.py -- the harness-side server for
BuildLang's `Model` capability wire contract (see the module docstring in
harness/model_shim.py for the full contract restatement).

Covers: (a) echo mode end to end over a real socket, spawned as a subprocess
with --once --port 0, including the client-side trailing-newline-trim
semantics the wire contract specifies; (b) the two ways a connection can be
a protocol violation (overlong line, EOF before a newline) both close
without a reply; (c) the sanitizer collapses a \r/\n-bearing completion to
one line, exercised through handle_connection with urllib mocked at the
network boundary -- no live ollama call, ever; (d) --echo and --ollama are
refused together and refused absent, at the argparse level.
"""
from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from harness import model_shim
from harness.oracle import spawn_killable

REPO_ROOT = Path(__file__).resolve().parent.parent


def _spawn_shim(*extra_args: str) -> subprocess.Popen:
    cmd = [sys.executable, "-m", "harness.model_shim", "--port", "0", *extra_args]
    return spawn_killable(cmd, cwd=str(REPO_ROOT), stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, bufsize=1)


def _cleanup(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        try:
            proc.kill()
        except Exception:
            pass
    try:
        proc.wait(timeout=5)
    except Exception:
        pass


def _read_bound_port(proc: subprocess.Popen) -> int:
    line = proc.stdout.readline()
    assert line, f"shim produced no port line; stderr={proc.stderr.read()!r}"
    return int(line.strip())


def _read_to_close(sock: socket.socket) -> bytes:
    data = bytearray()
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            return bytes(data)
        data += chunk


def _trim_trailing_newline(data: bytes) -> str:
    """Mirror the client-side trim the wire contract specifies: exactly one
    trailing \n, and a \r immediately before it, if present."""
    if data.endswith(b"\n"):
        data = data[:-1]
    if data.endswith(b"\r"):
        data = data[:-1]
    return data.decode("utf-8")


@pytest.fixture
def echo_server():
    proc = _spawn_shim("--echo", "--once")
    try:
        port = _read_bound_port(proc)
        yield port
    finally:
        _cleanup(proc)


def test_echo_mode_end_to_end_over_real_socket(echo_server):
    port = echo_server
    prompt = "what is the airspeed velocity of an unladen swallow"
    sock = socket.create_connection(("127.0.0.1", port), timeout=10)
    try:
        sock.sendall((prompt + "\n").encode("utf-8"))
        sock.shutdown(socket.SHUT_WR)
        raw = _read_to_close(sock)
    finally:
        sock.close()
    completion = _trim_trailing_newline(raw)
    assert completion == f"echo: {prompt}"
    # the wire write itself carries exactly one trailing \n, no \r
    assert raw == f"echo: {prompt}\n".encode("utf-8")


def test_overlong_prompt_line_closes_without_reply(echo_server):
    port = echo_server
    sock = socket.create_connection(("127.0.0.1", port), timeout=10)
    try:
        # one byte past the 1 MiB cap, no newline -- must be refused before
        # a newline could ever legally arrive
        sock.sendall(b"a" * (model_shim.MAX_PROMPT_BYTES + 1))
        raw = _read_to_close(sock)
    finally:
        sock.close()
    assert raw == b""


def test_eof_before_newline_closes_without_reply(echo_server):
    port = echo_server
    sock = socket.create_connection(("127.0.0.1", port), timeout=10)
    try:
        sock.sendall(b"partial prompt, never terminated")
        sock.shutdown(socket.SHUT_WR)  # EOF on the server's read side
        raw = _read_to_close(sock)
    finally:
        sock.close()
    assert raw == b""


def test_ollama_response_sanitized_to_one_line():
    """No network: urlopen is mocked at the urllib boundary. Confirms the
    \r/\n-bearing "response" field ollama_complete returns comes out of
    handle_connection as a single sanitized line on the wire."""
    fake_body = b'{"response": "hello\\nworld\\r\\nagain"}'

    class _FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return fake_body

    with mock.patch.object(model_shim.urllib.request, "urlopen",
                           return_value=_FakeResp()) as m:
        client_sock, server_sock = socket.socketpair()
        try:
            client_sock.sendall(b"prompt\n")
            model_shim.handle_connection(
                server_sock, mode="ollama", model="dummy-model",
                endpoint="http://127.0.0.1:99999", timeout=1.0)
            server_sock.close()
            raw = _read_to_close(client_sock)
        finally:
            client_sock.close()
    m.assert_called_once()
    assert raw == b"hello world  again\n"
    assert b"\r" not in raw
    assert raw.count(b"\n") == 1  # only the one trailing terminator


def test_ollama_http_failure_is_fail_closed_empty_reply():
    """An ollama error must write nothing -- read-to-close yields b"", never
    a fabricated completion. No network: urlopen raises directly."""
    import urllib.error

    with mock.patch.object(model_shim.urllib.request, "urlopen",
                           side_effect=urllib.error.URLError("connection refused")):
        client_sock, server_sock = socket.socketpair()
        try:
            client_sock.sendall(b"prompt\n")
            model_shim.handle_connection(
                server_sock, mode="ollama", model="dummy-model",
                endpoint="http://127.0.0.1:99999", timeout=1.0)
            server_sock.close()
            raw = _read_to_close(client_sock)
        finally:
            client_sock.close()
    assert raw == b""


def test_echo_and_ollama_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        model_shim.build_arg_parser().parse_args(
            ["--echo", "--ollama", "llama3", "--once"])


def test_exactly_one_mode_is_required():
    with pytest.raises(SystemExit):
        model_shim.build_arg_parser().parse_args(["--once"])
