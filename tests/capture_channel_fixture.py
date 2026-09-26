"""Shared fixture for the capture-channel tests: a real gateway on port 0.

The gateway runs in this process on a loopback port the OS picks, with a
temporary FLYWHEEL_HOME, and writes the endpoint file the hooks read. Hooks
run as subprocesses through `python -m harness.capture_hooks`, so they see
exactly what a mounted hook sees: the environment, the working directory and
the files on disk, nothing from this process.
"""
from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading

REPO = Path(__file__).resolve().parents[1]
UUID = "0f6d2c1e-4b7a-4c55-9a51-2f0e7c9d1a3b"


def hook_env(extra=None) -> dict:
    """The parent environment without any FLYWHEEL_* variable, plus `extra`."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("FLYWHEEL_")}
    env["PYTHONPATH"] = str(REPO)
    env.update(extra or {})
    return env


def run_hook(home: Path, event: str, payload: dict, *, client="claude-code",
             cwd: Path, env=None, timeout=60) -> subprocess.CompletedProcess:
    argv = [sys.executable, "-m", "harness.capture_hooks", event, "--client", client]
    if home is not None:
        argv += ["--home", str(home)]
    return subprocess.run(argv, input=json.dumps(payload).encode(), cwd=str(cwd),
                          env=env if env is not None else hook_env(),
                          capture_output=True, timeout=timeout)


def stop_event(answer="the final answer", session=UUID, **extra) -> dict:
    return {"session_id": session, "hook_event_name": "Stop",
            "last_assistant_message": answer, "stop_hook_active": False, **extra}


def prompt_event(prompt="a prompt", session=UUID, **extra) -> dict:
    return {"session_id": session, "hook_event_name": "UserPromptSubmit",
            "prompt": prompt, **extra}


@contextlib.contextmanager
def running_gateway(home: Path, monkeypatch):
    from harness import gateway
    from harness.gateway_auth import DEFAULT_HOSTS, load_or_create_token
    from harness.gateway_bind import ExclusiveThreadingHTTPServer
    from harness.gateway_endpoint_file import remove_endpoint, write_endpoint
    token = load_or_create_token(home)
    monkeypatch.setattr(gateway._Handler, "flywheel_home", home)
    monkeypatch.setattr(gateway._Handler, "auth_token", token)
    monkeypatch.setattr(gateway._Handler, "allowed_hosts", DEFAULT_HOSTS)
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    server = ExclusiveThreadingHTTPServer(("127.0.0.1", 0), gateway._Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    write_endpoint(home, host, port, os.getpid())
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        remove_endpoint(home)


class RecordingListener:
    """A listener that is not the gateway: it records every byte it receives
    and answers with a body the test chooses (or a relay to another port)."""

    def __init__(self, respond):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        self.received: list[bytes] = []
        self.respond = respond
        self._stop = False
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        self.sock.settimeout(0.2)
        while not self._stop:
            try:
                conn, _ = self.sock.accept()
            except (socket.timeout, OSError):
                continue
            with conn:
                conn.settimeout(2)
                data = b""
                try:
                    while b"\r\n\r\n" not in data:
                        chunk = conn.recv(65536)
                        if not chunk:
                            break
                        data += chunk
                except socket.timeout:
                    pass
                self.received.append(data)
                body = self.respond(data)
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                             b"Content-Length: " + str(len(body)).encode()
                             + b"\r\nConnection: close\r\n\r\n" + body)

    def close(self):
        self._stop = True
        self.thread.join(timeout=5)
        self.sock.close()


def spool_files(home: Path) -> list[Path]:
    root = home / "state" / "capture-failures" / "v1"
    return sorted(p for p in root.glob("f-*.json")) if root.exists() else []


def all_bytes_under(root: Path) -> bytes:
    out = b""
    for path in root.rglob("*"):
        if path.is_file():
            out += path.read_bytes()
    return out
