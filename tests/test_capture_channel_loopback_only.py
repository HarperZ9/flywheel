"""The capture channel answers only on a loopback listener to a loopback peer.

Security review of 1.1.0, finding 4: ``/api/traces/capture/*`` skips the
bearer check, and the hello answered on every bound interface. With the
gateway also bound to a LAN or tailnet address, a peer there could read the
owner's capture settings with no credential, fold spool records and create
the owner ref, and spend the one process-wide budget of 20 hellos a second so
every owner hook failed with HELLO_RATE_LIMITED. Hooks only ever connect to
loopback, and remote capture is out of scope, so nothing legitimate is lost.
"""
from __future__ import annotations

import pytest

from harness import trace_routes
from harness.capture_hooks import protocol


class _Handler:
    def __init__(self, home, server, client):
        self.flywheel_home = home
        self.server = type("S", (), {"server_address": (server, 8799)})()
        self.client_address = (client, 50123)
        self.headers = {"Host": f"{server}:8799"}
        self.allowed_hosts = frozenset({f"{server}:8799", "127.0.0.1:8799", server})
        self.auth_token = "t" * 43
        self.path = protocol.HELLO_PATH
        self.sent = []

    def _json(self, obj, code=200):
        self.sent.append(code)
        return code

    def _content_length(self):
        return 0


@pytest.mark.parametrize("server,client", [("100.64.0.1", "100.64.0.9"),
                                           ("127.0.0.1", "192.168.1.20"),
                                           ("192.168.1.5", "127.0.0.1")])
def test_a_capture_route_off_loopback_is_not_found_and_changes_nothing(
        tmp_path, server, client):
    home = tmp_path / "home"
    home.mkdir()
    handler = _Handler(home, server, client)
    assert trace_routes.route_get(handler, protocol.HELLO_PATH, "cn=" + "a" * 32) == 404
    assert trace_routes.route_get(handler, protocol.PING_PATH, "") == 404
    assert trace_routes.route_post(handler, protocol.PROMPT_PATH) == 404
    assert list(home.iterdir()) == []            # no owner ref, no ledger, no spool fold


def test_control_a_loopback_hello_is_served(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    handler = _Handler(home, "127.0.0.1", "127.0.0.1")
    code = trace_routes.route_get(handler, protocol.HELLO_PATH, "cn=bad")
    assert code == 422                            # reached the hello's own checks
