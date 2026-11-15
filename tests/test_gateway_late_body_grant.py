"""A body that arrives too late on a granted route consumes nothing in the grant store.

The fourth independent review listed, among what it had not examined: what a
`BodyTimeout` (a `BaseException`) leaves in the operation grant store when it
passes through the grant step and through `_route_operation`.

Examined here over real sockets. On both paths the body is read whole before
the grant store is opened, so a late body ends the request with 408 before
anything is consumed. The test prepares and approves one operation, sends its
final request with a body that never completes, and then sends the same final
request whole: it is served, so the grant was still there and no lock was
left behind. Two routes: /v1/chat/completions (the grant step in `_post`) and
/api/agent (`_route_operation`). No provider is called.
"""
import socket
import time

import pytest

from harness import gateway_read_timeout
from tests import gateway_route_sweep_support as sweep

LIMIT = 0.5
CASES = {
    "/v1/chat/completions": ("chat.complete", {
        "model": "ollama:stub-model", "messages": [{"role": "user", "content": "Say hi."}],
        "stream": False}),
    "/api/agent": ("agent.run", {
        "goal": "say hi", "endpoint": "ollama", "max_steps": 1, "allow_write": False,
        "allow_exec": False, "stream": False}),
}


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv(gateway_read_timeout.ENV, str(LIMIT))
    made = sweep.World(tmp_path / "w", monkeypatch)
    yield made
    made.close()


def _late(world, path: str, body: bytes) -> int:
    """Send the head and half of the body, then nothing; the status the gateway answers."""
    head = (f"POST {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n"
            f"Authorization: Bearer {sweep.TOKEN}\r\nContent-Length: {len(body)}\r\n\r\n")
    data = b""
    with socket.create_connection(("127.0.0.1", world.port), timeout=30) as sock:
        sock.sendall(head.encode() + body[:len(body) // 2])
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                more = sock.recv(65536)
            except OSError:
                break
            if not more:
                break
            data += more
    return int(data.split(b" ", 2)[1]) if data.startswith(b"HTTP/") else 0


@pytest.mark.timeout(180)
@pytest.mark.parametrize("path", sorted(CASES))
def test_a_late_body_leaves_the_grant_unconsumed_and_no_lock(world, path):
    action, operation = CASES[path]
    body = world.granted(action, operation)
    assert body is not None
    before = len(world.provider.requests)
    assert _late(world, path, body) == 408
    assert len(world.provider.requests) == before and world.entries() == []
    result = world.exercise("POST", path, body)     # the same grant, the whole body
    # The grant step passed: the grant was still there and no lock was left.
    assert result["status"] not in (401, 403, 408, 422), result
    if path == "/v1/chat/completions":
        assert result["status"] == 200 and len(result["provider_model"]) == 1
        assert len(result["started"]) == len(result["ended"]) == 1
    else:       # an agent run: an operation in a worker process, recorded in its own trace.
        # Where the worker can run, its request reaches the stub; on a CI runner the
        # operation ends before contact. No request leaves without a started trace record.
        assert result["started"] == []
        assert result["trace_started"] >= len(result["provider_model"]), result
    # And it is consumed now: the same body again is refused, with nothing sent.
    again = world.exercise("POST", path, body)
    assert again["status"] in (403, 409) and again["provider_model"] == [], again
