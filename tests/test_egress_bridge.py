"""The Linux entry point, asserted on a host that is not Linux.

Everything the bridge can get wrong is ordering, relaying and the exit
code, and none of those is Linux-specific. The unix socket is the one part
that is, so it is injected here and exercised for real in the test at the
bottom, which runs where such a socket exists.
"""
import socket
import sys
import threading

import pytest

from harness.egress_bridge import BIND_FAILED, bridge, main


def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class _Origin:
    """The host side of the route. Echoes whatever crosses it."""

    def __init__(self, family=socket.AF_INET, address=("127.0.0.1", 0)):
        self.sock = socket.socket(family)
        self.sock.bind(address)
        self.sock.listen(8)
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


def no_upstream():
    """A host proxy that is not there.

    What `_unix_upstream` raises when the socket is gone, which is the one
    failure the relay side has to survive without taking the run with it.
    """
    raise OSError("no upstream in this test")


@pytest.fixture
def origin():
    server = _Origin()
    yield server
    server.close()


def test_the_listener_is_up_before_the_command_starts():
    """The ordering this file exists for.

    A command started first would race its own proxy, and the connection it
    lost would fail for a reason nothing in the record explains. The command
    here proves the port answers at the moment it runs.
    """
    port = free_port()
    reached, closed = [], []

    def command(argv):
        conn = socket.create_connection(("127.0.0.1", port), timeout=5)
        conn.settimeout(5)
        reached.append(True)
        closed.append(conn.recv(16))
        conn.close()
        return 0

    assert bridge("unused", port, ["irrelevant"], connect=no_upstream,
                  spawn=command) == 0
    assert reached == [True]
    assert closed == [b""], (
        "a client whose upstream is unreachable has to be closed, not left "
        "waiting on a route that will never carry anything")


def test_the_exit_code_belongs_to_the_command_and_not_to_the_bridge():
    """A run reports what it did. A bridge that swallowed a failing status
    would turn a failed build into a passing one."""
    port = free_port()
    assert bridge("unused", port, ["x"], connect=no_upstream,
                  spawn=lambda argv: 7) == 7


def test_a_port_that_cannot_be_bound_refuses_to_run_the_command():
    """The command must not start without its route.

    It would run with a proxy address that answers nothing, and every
    request it made would fail somewhere inside whatever it was doing.
    """
    taken = socket.socket()
    taken.bind(("127.0.0.1", 0))
    taken.listen(1)
    started = []
    try:
        code = bridge("unused", taken.getsockname()[1], ["x"],
                      connect=no_upstream,
                      spawn=lambda argv: started.append(True) or 0)
    finally:
        taken.close()
    assert code == BIND_FAILED
    assert started == [], "the command ran without a route to the proxy"


def test_a_connection_inside_the_namespace_reaches_the_host_side(origin):
    """End to end with the crossing injected: bytes in, same bytes back."""
    port = free_port()
    carried = []

    def command(argv):
        conn = socket.create_connection(("127.0.0.1", port), timeout=5)
        conn.settimeout(5)
        conn.sendall(b"CONNECT pypi.org:443 HTTP/1.1\r\n\r\n")
        carried.append(conn.recv(64))
        conn.close()
        return 0

    bridge("unused", port, ["x"],
           connect=lambda: socket.create_connection(origin.address, timeout=5),
           spawn=command)
    assert carried == [b"CONNECT pypi.org:443 HTTP/1.1\r\n\r\n"]


def test_the_port_stops_answering_once_the_command_is_done():
    """The listener belongs to one run. A port still open afterwards is a
    route out of a sandbox that has already been reported as finished."""
    port = free_port()
    bridge("unused", port, ["x"], connect=no_upstream, spawn=lambda a: 0)
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=2).close()


def test_the_command_after_the_separator_is_the_command_that_runs():
    """`main` as the sandbox invokes it, including the exit code it hands
    back to the run that started it."""
    assert main(["--socket", "unused", "--port", str(free_port()), "--",
                 sys.executable, "-c", "raise SystemExit(5)"]) == 5


def test_no_command_is_an_error_rather_than_a_bridge_with_nothing_to_guard():
    with pytest.raises(SystemExit):
        main(["--socket", "unused", "--port", "9", "--"])


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"),
                    reason="pathname unix sockets are the Linux crossing")
def test_a_real_unix_socket_carries_the_connection(scratch):
    """The crossing itself, on a host that has one.

    Everything above injects this. Here it is a pathname socket, which is
    scoped to the filesystem rather than to the network namespace, and that
    scoping is the whole reason the route works.
    """
    path = str(scratch / "egress.sock")
    server = _Origin(family=socket.AF_UNIX, address=path)
    port = free_port()
    carried = []

    def command(argv):
        conn = socket.create_connection(("127.0.0.1", port), timeout=5)
        conn.settimeout(5)
        conn.sendall(b"over the boundary")
        carried.append(conn.recv(64))
        conn.close()
        return 0

    try:
        bridge(path, port, ["x"], spawn=command)
    finally:
        server.close()
    assert carried == [b"over the boundary"]
