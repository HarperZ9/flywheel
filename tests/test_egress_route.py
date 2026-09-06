"""The endpoint a confined run is given, per backend.

The policy and the proxy are tested elsewhere. What is asserted here is the
part that differs by host: where the listener is, what the confined process
is told to dial, and what happens when a route cannot be made at all.
"""
import os
import socket
import threading

import pytest

from harness.egress_policy import EgressPolicy
from harness.egress_proxy import EgressProxy
from harness.egress_route import (EgressRoute, RouteUnavailable, SUN_PATH_LIMIT,
                                  bridge_argv, fits_sun_path, open_route)

HAS_UNIX = hasattr(socket, "AF_UNIX")
UNIX_ONLY = pytest.mark.skipif(
    not HAS_UNIX, reason="the bwrap route is a pathname unix socket")


class _Origin:
    """The far side of an allowed connection. Echoes whatever arrives."""

    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(4)
        self.address = self.sock.getsockname()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        self.sock.settimeout(0.5)
        while not self.stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except (socket.timeout, TimeoutError):
                continue
            except OSError:
                return
            threading.Thread(target=self._echo, args=(conn,),
                             daemon=True).start()

    def _echo(self, conn):
        with conn:
            while True:
                try:
                    data = conn.recv(4096)
                except OSError:
                    return
                if not data:
                    return
                conn.sendall(data)

    def close(self):
        self.stop.set()
        self.thread.join(timeout=3)
        self.sock.close()


@pytest.fixture
def origin():
    server = _Origin()
    yield server
    server.close()


def proxy_for(policy, origin):
    """A proxy that resolves every name to the test origin.

    Resolution and dialling are injected so the route can be exercised
    without the tests asking the network anything, which would make them
    depend on what a resolver happens to answer today.
    """
    return EgressProxy(
        policy,
        resolve=lambda host, port: ["93.184.216.34"],
        connect_to=lambda address, port: socket.create_connection(
            origin.address, timeout=5))


def talk(port, request):
    conn = socket.create_connection(("127.0.0.1", port), timeout=5)
    conn.settimeout(5)
    try:
        conn.sendall(request)
        return conn.recv(256)
    finally:
        conn.close()


def test_the_seatbelt_route_listens_on_the_port_it_reports(origin):
    """The endpoint and the port are two ways of saying one thing.

    The profile is written from the port and the run dials the endpoint. If
    those disagreed the kernel would open a hole onto nothing and the run
    would fail against a policy that looks correct in the record.
    """
    policy = EgressPolicy(hosts=("pypi.org",))
    with open_route(policy, "seatbelt", "unused",
                    proxy=proxy_for(policy, origin)) as route:
        assert route.route.endpoint == f"127.0.0.1:{route.route.port}"
        answer = talk(route.route.port,
                      b"CONNECT pypi.org:443 HTTP/1.1\r\n\r\n")
    assert answer.startswith(b"HTTP/1.1 200")


def test_a_host_nobody_named_is_refused_over_the_route(origin):
    policy = EgressPolicy(hosts=("pypi.org",))
    with open_route(policy, "seatbelt", "unused",
                    proxy=proxy_for(policy, origin)) as route:
        answer = talk(route.route.port,
                      b"CONNECT evil.example:443 HTTP/1.1\r\n\r\n")
        written = route.record()
    assert b"403" in answer
    assert [(one["host"], one["allowed"]) for one in written["attempts"]] == [
        ("evil.example", False)]


def test_the_record_says_what_was_asked_for_and_not_only_what_was_allowed(
        origin):
    """A refusal is the part of the record worth having.

    An allowed request is visible in the run's own output anyway. What the
    run tried and could not reach is only knowable here.
    """
    policy = EgressPolicy(hosts=("pypi.org",))
    with open_route(policy, "seatbelt", "unused",
                    proxy=proxy_for(policy, origin)) as route:
        talk(route.route.port, b"CONNECT pypi.org:443 HTTP/1.1\r\n\r\n")
        talk(route.route.port, b"CONNECT files.example:443 HTTP/1.1\r\n\r\n")
        written = route.record()
    assert written["hosts"] == ["pypi.org"]
    assert sorted(one["reason"] for one in written["attempts"]) == [
        "allowed", "not-allowed"]


def test_closing_the_route_closes_the_way_in(origin):
    """The policy stops applying when the run ends, so the door shuts with
    it. A listener still answering afterwards is an unconfined proxy."""
    policy = EgressPolicy(hosts=("pypi.org",))
    route = open_route(policy, "seatbelt", "unused",
                       proxy=proxy_for(policy, origin))
    port = route.route.port
    route.close()
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=2).close()


def test_a_backend_with_no_route_is_refused_rather_than_given_one(tmp_path):
    with pytest.raises(RouteUnavailable):
        open_route(EgressPolicy(hosts=("pypi.org",)), "none", tmp_path)


@pytest.mark.skipif(HAS_UNIX, reason="the refusal only happens without one")
def test_a_host_without_pathname_sockets_gets_no_linux_route(tmp_path):
    """Windows reaches this. The point is that it refuses instead of
    falling back to something that would let the run out unfiltered."""
    with pytest.raises(RouteUnavailable):
        open_route(EgressPolicy(hosts=("pypi.org",)), "bwrap", tmp_path)


def test_the_proxy_variables_all_point_at_the_port_the_run_can_reach():
    where = EgressRoute("bwrap", "/tmp/x/egress.sock", 8931).env()
    assert set(where) == {"HTTP_PROXY", "HTTPS_PROXY", "http_proxy",
                          "https_proxy", "ALL_PROXY", "all_proxy", "NO_PROXY"}
    assert {where[name] for name in where if name != "NO_PROXY"} == {
        "http://127.0.0.1:8931"}


def test_an_inherited_no_proxy_cannot_carve_a_host_out_of_the_route():
    """`NO_PROXY` is a list of hosts a client is told to reach directly. One
    inherited from the operator's shell would be a hole in the policy that
    nothing in this repository wrote."""
    assert EgressRoute("seatbelt", "127.0.0.1:1", 1).env()["NO_PROXY"] == ""


def test_the_bridge_command_names_the_socket_and_the_port_and_then_stops():
    argv = bridge_argv(EgressRoute("bwrap", "/scratch/egress.sock", 8931),
                       python="/usr/bin/python3")
    assert argv[0] == "/usr/bin/python3"
    assert argv[1].endswith("egress_bridge.py")
    assert argv[2:] == ["--socket", "/scratch/egress.sock", "--port", "8931",
                        "--"]
    assert argv[-1] == "--", (
        "the confined command is appended after this, so anything following "
        "the separator has to be the command and not another bridge flag")


@pytest.mark.parametrize("length,fits", [(SUN_PATH_LIMIT, True),
                                         (SUN_PATH_LIMIT + 1, False)])
def test_a_path_the_kernel_would_truncate_is_not_a_path_that_fits(length,
                                                                  fits):
    """`bind` truncates a long path instead of refusing it, so the socket
    exists under a name the caller never asked for and the bridge connects
    to nothing."""
    assert fits_sun_path("a" * length) is fits


def test_the_field_is_counted_in_bytes_and_not_in_characters():
    """A non-ASCII directory name spends more than one byte per character,
    and the kernel field is bytes."""
    assert fits_sun_path("é" * (SUN_PATH_LIMIT // 2)) is True
    assert fits_sun_path("é" * (SUN_PATH_LIMIT // 2 + 1)) is False


@UNIX_ONLY
def test_the_linux_route_listens_in_the_scratch_directory(tmp_path, origin):
    """The scratch directory is already bind-mounted writable into the run,
    so the socket needs no new bubblewrap argument to be reachable."""
    policy = EgressPolicy(hosts=("pypi.org",))
    with open_route(policy, "bwrap", tmp_path,
                    proxy=proxy_for(policy, origin)) as route:
        assert route.route.endpoint == str(tmp_path / "egress.sock")
        assert os.path.exists(route.route.endpoint)
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.settimeout(5)
        conn.connect(route.route.endpoint)
        conn.sendall(b"CONNECT pypi.org:443 HTTP/1.1\r\n\r\n")
        answer = conn.recv(64)
        conn.close()
    assert answer.startswith(b"HTTP/1.1 200")


@UNIX_ONLY
def test_the_socket_does_not_outlive_the_run(tmp_path, origin):
    policy = EgressPolicy(hosts=("pypi.org",))
    route = open_route(policy, "bwrap", tmp_path,
                       proxy=proxy_for(policy, origin))
    path = route.route.endpoint
    route.close()
    assert not os.path.exists(path)


@UNIX_ONLY
def test_the_linux_port_is_inside_the_namespace_and_not_on_the_host(
        tmp_path, origin):
    """Nothing on the host answers on that port, and that is correct: the
    bridge binds it inside a namespace the host does not share."""
    policy = EgressPolicy(hosts=("pypi.org",))
    with open_route(policy, "bwrap", tmp_path,
                    proxy=proxy_for(policy, origin)) as route:
        assert not route.route.endpoint.startswith("127.0.0.1")
        with pytest.raises(OSError):
            socket.create_connection(("127.0.0.1", route.route.port),
                                     timeout=2).close()
