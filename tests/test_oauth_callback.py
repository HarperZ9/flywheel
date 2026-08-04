"""Falsifiers for the loopback sign-in channel (harness/oauth_callback.py).

127.0.0.1 is shared with every other local process, so the listener is
treated as hostile ground. An adversarial review proved the first draft could
be aborted by a stray GET, injected with an attacker-chosen code, and have a
captured code blanked by a later request. These pin the fixes.
"""
import threading
import urllib.error
import urllib.request

from harness.oauth_callback import CallbackServer


def _get(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return None


def test_captures_code_on_the_nonce_path():
    server = CallbackServer()
    threading.Timer(0.2, lambda: _get(server.callback_url + "?code=abc123")).start()
    assert server.wait_for_code(timeout=10) == "abc123"


def test_callback_url_is_loopback_with_a_nonce_path():
    server = CallbackServer()
    try:
        assert server.callback_url.startswith("http://127.0.0.1:")
        assert f"/cb/{server.nonce}" in server.callback_url
        assert len(server.nonce) >= 16
    finally:
        server.server_close()


def test_nonces_differ_between_runs():
    a, b = CallbackServer(), CallbackServer()
    try:
        assert a.nonce != b.nonce
    finally:
        a.server_close()
        b.server_close()


def test_stray_local_request_cannot_abort_or_inject():
    # A local GET on the wrong path must neither stop the listener nor become
    # the captured code: the real approval still wins.
    server = CallbackServer()
    port = server.server_address[1]
    threading.Timer(0.2, lambda: _get(f"http://127.0.0.1:{port}/x?code=ATTACKER")).start()
    threading.Timer(0.5, lambda: _get(f"http://127.0.0.1:{port}/favicon.ico")).start()
    threading.Timer(0.9, lambda: _get(server.callback_url + "?code=REAL")).start()
    assert server.wait_for_code(timeout=15) == "REAL"


def test_stray_request_gets_404_and_the_listener_keeps_waiting():
    server = CallbackServer()
    port = server.server_address[1]
    seen = {}
    threading.Timer(0.2, lambda: seen.update(
        {"stray": _get(f"http://127.0.0.1:{port}/nope")})).start()
    threading.Timer(0.6, lambda: _get(server.callback_url + "?code=REAL")).start()
    assert server.wait_for_code(timeout=15) == "REAL"
    assert seen["stray"] == 404


def test_captured_code_is_never_overwritten():
    server = CallbackServer()
    threading.Timer(0.2, lambda: _get(server.callback_url + "?code=REAL")).start()
    threading.Timer(0.6, lambda: _get(server.callback_url)).start()  # no code
    assert server.wait_for_code(timeout=15) == "REAL"


def test_provider_denial_is_reported_not_captured():
    server = CallbackServer()
    threading.Timer(0.2, lambda: _get(server.callback_url + "?error=access_denied")).start()
    assert server.wait_for_code(timeout=10) is None
    assert server.error == "access_denied"


def test_does_not_allow_address_reuse():
    # SO_REUSEADDR would let a second local process co-bind the same port.
    assert CallbackServer.allow_reuse_address is False


def test_timeout_returns_none_and_closes_the_socket():
    server = CallbackServer()
    assert server.wait_for_code(timeout=0.5) is None
    # The socket is closed on every exit path: a second close must not raise,
    # and the port must no longer answer.
    server.server_close()
    assert _get(server.callback_url) is None
