"""Each check of the signed capture channel refuses on its own: a request
whose time is outside the skew window, one naming a server nonce this
gateway never issued, and one whose body changed under a valid signature
header. A correct request passes first, so each refusal is the check's."""
import json

import pytest

from harness.capture_hooks import protocol
from harness.gateway_request_sig import SKEW_S, ChannelState

TOKEN = "planted-fake-gateway-token-0000000000"
HOST, PORT = "127.0.0.1", 48123
PATH = protocol.PREFIX + "prompt"
BODY = json.dumps({"client": "codex", "commitment": "c" * 64}).encode()
NOW = 1_800_000_000.0


@pytest.fixture
def channel():
    state = ChannelState(clock=lambda: NOW)
    sn = state.hello(TOKEN, "a" * 32, HOST, PORT)["sn"]
    return state, sn


def _header(sn, *, ts=NOW, nonce="b" * 32, body=BODY):
    _, k_c = protocol.derive_keys(TOKEN)
    return protocol.auth_header(k_c, "POST", PATH, body, int(ts), nonce, sn, HOST, PORT)


def _verify(state, header, body=BODY):
    return state.verify(TOKEN, header, "POST", PATH, body, HOST, PORT)


def test_a_correct_request_passes(channel):
    state, sn = channel
    assert _verify(state, _header(sn))


@pytest.mark.parametrize("offset", [SKEW_S + 1, -(SKEW_S + 1)])
def test_a_request_outside_the_time_window_is_refused(channel, offset):
    state, sn = channel
    assert not _verify(state, _header(sn, ts=NOW + offset))
    assert _verify(state, _header(sn, ts=NOW + offset / abs(offset) * (SKEW_S - 1),
                                  nonce="c" * 32))


def test_a_server_nonce_this_gateway_never_issued_is_refused(channel):
    state, _ = channel
    assert not _verify(state, _header("d" * 32))


def test_a_changed_body_under_a_valid_header_is_refused(channel):
    state, sn = channel
    header = _header(sn)
    assert not _verify(state, header, body=BODY.replace(b"codex", b"clxde"))
    assert _verify(state, header)
