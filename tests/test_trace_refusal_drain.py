"""The trace routes' own refusals leave no unread request bytes either.

Correctness review F12 of 1.1.0: the whole suite in one process failed
``test_trace_delete_route.py::test_planning_needs_the_bearer_token`` with
ConnectionAbortedError where it expected 401, because a POST refused before
its body is read can be reset on Windows before the client reads the answer.
The gateway now drains what a route left (``gateway_body_drain``). These cases
cover the refusals the trace work added: the bearer check on a custody route,
and a custody body over its 64 KiB limit answered 422 without being read.
"""
from __future__ import annotations

from tests.test_gateway_body_drain import BODY, _exchange, _wait_for, server  # noqa: F401


def test_a_custody_route_refused_for_its_token_leaves_nothing_unread(server):  # noqa: F811
    port = server.server_port
    reply = _exchange(port, ["POST /api/traces/delete/plan HTTP/1.1", f"Host: 127.0.0.1:{port}",
                             "Content-Type: application/json",
                             f"Content-Length: {len(BODY)}"], BODY)
    assert reply.startswith(b"HTTP/1.0 401 ")
    _wait_for(server, 1)
    assert server.unread == [0]


def test_a_custody_body_over_its_limit_is_drained_after_the_refusal(server):  # noqa: F811
    port = server.server_port
    token = server.RequestHandlerClass.auth_token
    big = b"{" + b" " * (100 * 1024) + b"}"
    reply = _exchange(port, ["POST /api/traces/delete/plan HTTP/1.1", f"Host: 127.0.0.1:{port}",
                             f"Authorization: Bearer {token}",
                             "Content-Type: application/json",
                             f"Content-Length: {len(big)}"], big)
    assert reply.split(b"\r\n", 1)[0].split(b" ")[1] in (b"401", b"422")
    _wait_for(server, 1)
    assert server.unread == [0]
