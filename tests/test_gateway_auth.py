import io
import json
import os
import stat

import pytest

from harness.gateway_auth import (
    authenticate_owner, load_or_create_token, check, TOKEN_FILENAME, DEFAULT_HOSTS,
)

TOK = "t" * 43


def _h(**kw):
    return {k.replace("_", "-"): v for k, v in kw.items()}


def test_token_is_created_once_and_reused(tmp_path):
    a = load_or_create_token(tmp_path)
    b = load_or_create_token(tmp_path)
    assert a == b
    assert len(a) >= 32
    assert (tmp_path / TOKEN_FILENAME).exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_token_file_is_not_world_readable(tmp_path):
    load_or_create_token(tmp_path)
    mode = (tmp_path / TOKEN_FILENAME).stat().st_mode
    assert not (mode & stat.S_IRGRP)
    assert not (mode & stat.S_IROTH)


def test_correct_bearer_token_on_a_local_host_passes():
    ok, _ = check(_h(Authorization=f"Bearer {TOK}", Host="127.0.0.1:8799",
                     Content_Type="application/json"),
                  "POST", TOK, allowed_hosts=DEFAULT_HOSTS)
    assert ok is True


def test_missing_token_is_refused():
    ok, reason = check(_h(Host="127.0.0.1:8799"), "GET", TOK,
                       allowed_hosts=DEFAULT_HOSTS)
    assert ok is False
    assert reason == "no_token"


def test_wrong_token_is_refused():
    ok, reason = check(_h(Authorization="Bearer wrong", Host="127.0.0.1:8799"),
                       "GET", TOK, allowed_hosts=DEFAULT_HOSTS)
    assert ok is False
    assert reason == "bad_token"


def test_foreign_host_header_is_refused_even_with_a_valid_token():
    # DNS rebinding: a page resolves attacker.example to 127.0.0.1 and sends its
    # own Host. The Host check is the layer that does not assume the token stayed
    # secret.
    ok, reason = check(_h(Authorization=f"Bearer {TOK}", Host="attacker.example"),
                       "GET", TOK, allowed_hosts=DEFAULT_HOSTS)
    assert ok is False
    assert reason == "bad_host"


def test_ipv6_loopback_literal_is_accepted():
    ok, _ = check(_h(Authorization=f"Bearer {TOK}", Host="[::1]:8799"),
                  "GET", TOK, allowed_hosts=DEFAULT_HOSTS)
    assert ok is True


def test_state_changing_request_requires_a_json_content_type():
    # Blocks the CORS-simple cross-origin POST: a form-encoded or text/plain body
    # can be sent by any page without a preflight.
    ok, reason = check(_h(Authorization=f"Bearer {TOK}", Host="localhost:8799",
                          Content_Type="text/plain"),
                       "POST", TOK, allowed_hosts=DEFAULT_HOSTS)
    assert ok is False
    assert reason == "bad_content_type"


def test_content_type_parameters_are_tolerated():
    ok, _ = check(_h(Authorization=f"Bearer {TOK}", Host="localhost:8799",
                     Content_Type="application/json; charset=utf-8"),
                  "POST", TOK, allowed_hosts=DEFAULT_HOSTS)
    assert ok is True


def test_get_does_not_require_a_content_type():
    ok, _ = check(_h(Authorization=f"Bearer {TOK}", Host="localhost:8799"),
                  "GET", TOK, allowed_hosts=DEFAULT_HOSTS)
    assert ok is True


def test_every_state_changing_method_is_gated():
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        ok, reason = check(_h(Authorization=f"Bearer {TOK}", Host="localhost:8799"),
                           method, TOK, allowed_hosts=DEFAULT_HOSTS)
        assert ok is False, method
        assert reason == "bad_content_type"


def test_token_comparison_does_not_short_circuit():
    import inspect
    from harness import gateway_auth
    assert "compare_digest" in inspect.getsource(gateway_auth.check)


def test_refusal_reason_never_leaks_the_token():
    ok, reason = check(_h(Authorization="Bearer wrong", Host="localhost"),
                       "GET", TOK, allowed_hosts=DEFAULT_HOSTS)
    assert ok is False
    assert TOK not in reason
    assert "wrong" not in reason


def test_owner_is_loaded_only_after_bearer_auth_and_survives_rotation(tmp_path, monkeypatch):
    """Loading identity before auth or deriving it from token would weaken ownership."""
    from harness import gateway_auth
    calls = []
    real = gateway_auth.load_or_create_owner_ref
    monkeypatch.setattr(gateway_auth, "load_or_create_owner_ref",
                        lambda home: calls.append(home) or real(home))
    wrong, reason = authenticate_owner(
        _h(Authorization="Bearer wrong", Host="localhost"), "POST", TOK, tmp_path,
        allowed_hosts=DEFAULT_HOSTS)
    first, first_reason = authenticate_owner(
        _h(Authorization=f"Bearer {TOK}", Host="localhost",
           Content_Type="application/json"), "POST", TOK, tmp_path,
        allowed_hosts=DEFAULT_HOSTS)
    rotated = "r" * 43
    second, second_reason = authenticate_owner(
        _h(Authorization=f"Bearer {rotated}", Host="localhost",
           Content_Type="application/json"), "POST", rotated, tmp_path,
        allowed_hosts=DEFAULT_HOSTS)
    assert wrong is None and reason == "bad_token" and calls == [tmp_path, tmp_path]
    assert first == second and first_reason == second_reason == "ok"


@pytest.mark.parametrize(("method", "path"), [
    ("GET", "/api/journeys/list?limit=1"),
    ("POST", "/api/journeys/get"),
    ("POST", "/api/grants/approve-once"),
    ("POST", "/api/gateway-grants/prepare/plugin.probe"),
    ("POST", "/api/plugins/probe"),
    ("POST", "/v1/chat/completions"),
    ("GET", "/api/plugins/probe?name=gather"),
])
def test_private_routes_require_configured_auth_without_loading_owner(
        method, path, tmp_path, monkeypatch):
    from harness import gateway
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path, handler.command = path, method
    handler.auth_token = ""; handler.flywheel_home = tmp_path
    handler.headers = {}; handler.wfile = io.BytesIO(); statuses = []
    handler.send_response = statuses.append
    handler.send_header = lambda *_: None; handler.end_headers = lambda: None
    monkeypatch.setattr(gateway, "load_or_create_owner_ref",
                        lambda *_: pytest.fail("private refusal loaded owner custody"))
    assert handler._authorized() is False
    result = json.loads(handler.wfile.getvalue())
    assert statuses == [401] and result == {
        "schema": "flywheel.evidence-transport-error/v1", "error": {
            "code": "AUTH_REQUIRED", "message": "gateway authentication is required"}}
