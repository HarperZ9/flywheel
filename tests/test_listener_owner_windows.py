"""SP-02: before sending anything, a hook checks that the listener on the
endpoint's port is the process the endpoint file names and runs as this user."""
import os
import socket
import sys

import pytest

from harness.capture_hooks.listener_owner import check_listener, method

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows TCP table")


@pytest.fixture
def listening():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    try:
        yield sock.getsockname()[1]
    finally:
        sock.close()


def test_the_gateways_own_pid_and_user_pass(listening):
    assert method() == "windows-owner-pid"
    assert check_listener("127.0.0.1", listening, os.getpid()) is None


def test_a_mismatched_pid_fails(listening):
    assert check_listener("127.0.0.1", listening, os.getpid() + 4) == "LISTENER_MISMATCH"


def test_a_port_nobody_listens_on_is_not_running():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    assert check_listener("127.0.0.1", port, os.getpid()) == "GATEWAY_NOT_RUNNING"


def test_an_ipv6_listener_is_found_in_the_ipv6_table():
    if not socket.has_ipv6:
        pytest.skip("no IPv6")
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    try:
        sock.bind(("::1", 0))
    except OSError:
        pytest.skip("no ::1")
    sock.listen(1)
    try:
        assert check_listener("::1", sock.getsockname()[1], os.getpid()) is None
    finally:
        sock.close()
