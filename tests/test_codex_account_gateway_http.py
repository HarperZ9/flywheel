"""Codex account routes must pass through real private gateway HTTP."""

from __future__ import annotations

import json

import pytest

from tests.codex_account_http_fixture import (
    OWNER,
    TOKEN,
    CodexAccountGateway,
    FakeCodexAccountManager,
)


def _error_code(value) -> str:
    assert isinstance(value, dict), value
    error = value.get("error")
    assert isinstance(error, dict), value
    return error.get("code")


def _call_owner(call: dict) -> str | None:
    return call["kwargs"].get("owner_ref") or next(
        (
            item
            for item in call["args"]
            if isinstance(item, str) and item.startswith("owner_")
        ),
        None,
    )


@pytest.fixture
def account_gateway(tmp_path):
    gateway = CodexAccountGateway(tmp_path / "codex-account-home")
    try:
        yield gateway
    finally:
        gateway.close()


def test_codex_account_routes_are_private_before_manager_invocation(
    account_gateway,
):
    attempts = (
        {"token": None},
        {"token": "wrong-token"},
        {"host": "attacker.invalid"},
    )

    for attempt in attempts:
        status, value = account_gateway.json_request(
            "/api/codex/account",
            **attempt,
        )
        assert status == 401
        assert _error_code(value) == "AUTH_REQUIRED"
        assert TOKEN not in json.dumps(value)

    assert account_gateway.manager.calls == []


def test_codex_account_gets_use_authenticated_owner_without_ui_action(
    account_gateway,
):
    status, account = account_gateway.json_request("/api/codex/account")
    assert status == 200, account
    assert account["method"] == "read_status"
    assert account["owner_ref"] == OWNER

    status, result = account_gateway.json_request(
        "/api/codex/account/login/result?login_id=login-browser-1",
    )
    assert status == 200, result
    assert result["method"] == "login_result"
    assert result["owner_ref"] == OWNER
    assert result["login_id"] == "login-browser-1"

    methods = [call["method"] for call in account_gateway.manager.calls]
    assert methods == ["read_status", "login_result"]
    for call in account_gateway.manager.calls:
        assert _call_owner(call) == OWNER
        assert call["kwargs"].get("visible_ui_action") is not True


def test_codex_account_post_mutations_mark_explicit_visible_api_action(
    account_gateway,
):
    cases = (
        (
            "/api/codex/account/login/start",
            {"mode": "browser"},
            "start_login",
            {"mode": "browser"},
        ),
        (
            "/api/codex/account/login/start",
            {"mode": "device"},
            "start_login",
            {"mode": "device"},
        ),
        (
            "/api/codex/account/login/cancel",
            {"login_id": "login-browser-1"},
            "cancel_login",
            {"login_id": "login-browser-1"},
        ),
        ("/api/codex/account/logout", {}, "logout", {}),
    )

    for path, body, method, expected in cases:
        status, value = account_gateway.json_request(path, body=body)
        assert status == 200, value
        assert value["method"] == method
        assert value["owner_ref"] == OWNER
        for key, expected_value in expected.items():
            assert value[key] == expected_value
        call = account_gateway.manager.calls[-1]
        assert call["method"] == method
        assert _call_owner(call) == OWNER
        assert call["kwargs"].get("visible_ui_action") is True


@pytest.mark.parametrize(
    ("path", "body", "content_type", "expected_status"),
    (
        (
            "/api/codex/account/login/start",
            {"mode": "browser"},
            "text/plain",
            401,
        ),
        (
            "/api/codex/account/login/start",
            b'{"mode":"' + b"x" * 8192 + b'"}',
            "application/json",
            413,
        ),
        ("/api/codex/account/login/start", b"", "application/json", 400),
        ("/api/codex/account/login/start", b'{"mode":', "application/json", 400),
        (
            "/api/codex/account/login/start",
            b'{"mode":"browser","mode":"device"}',
            "application/json",
            400,
        ),
        (
            "/api/codex/account/login/start",
            {"mode": "browser", "owner_ref": "owner_" + "b" * 32},
            "application/json",
            400,
        ),
        (
            "/api/codex/account/login/start",
            {"mode": 7},
            "application/json",
            400,
        ),
        (
            "/api/codex/account/login/cancel",
            {"login_id": 7},
            "application/json",
            400,
        ),
        (
            "/api/codex/account/logout",
            {"login_id": "login-browser-1"},
            "application/json",
            400,
        ),
    ),
)
def test_codex_account_post_rejects_bad_transport_and_shapes_without_side_effects(
    account_gateway,
    path,
    body,
    content_type,
    expected_status,
):
    status, value = account_gateway.json_request(
        path,
        body=body,
        content_type=content_type,
    )

    assert status == expected_status
    assert isinstance(value, dict), value
    if expected_status == 401:
        assert _error_code(value) == "AUTH_REQUIRED"
    assert account_gateway.manager.calls == []


@pytest.mark.parametrize(
    "path",
    (
        "/api/codex/account/login/result?login_id=login-1&login_id=login-2",
        "/api/codex/account/login/result?id=login-1",
        "/api/codex/account/login/result?login_id=login-1&alias=codex",
    ),
)
def test_codex_account_login_result_requires_exact_one_query_without_aliases(
    account_gateway,
    path,
):
    status, value = account_gateway.json_request(path)

    assert status == 400
    assert isinstance(value, dict), value
    assert account_gateway.manager.calls == []


@pytest.mark.parametrize(
    ("path", "body"),
    (
        ("/api/codex/account/sessions", None),
        ("/api/codex/account/login/approve", {"login_id": "login-1"}),
    ),
)
def test_codex_account_unknown_paths_are_404_without_manager_side_effects(
    account_gateway,
    path,
    body,
):
    status, value = account_gateway.json_request(path, body=body)

    assert status == 404
    assert isinstance(value, dict), value
    assert account_gateway.manager.calls == []
