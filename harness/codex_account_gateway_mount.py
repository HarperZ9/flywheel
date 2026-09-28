"""Private, bounded HTTP mount for explicit Codex account actions.

The gateway authenticates the caller before dispatch. An explicit POST selects
an account action; it does not attest that a human physically clicked a button.
Account reads never initiate login, logout, or browser navigation.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qsl

_BASE = "/api/codex/account"
_POST_FIELDS = {
    _BASE + "/login/start": {"mode"},
    _BASE + "/login/cancel": {"login_id"},
    _BASE + "/logout": set(),
}
MAX_BODY_BYTES = 8192


def _reply_error(handler, state: str, status: int):
    return handler._json({"schema": "flywheel.codex-account-route/v1",
                          "state": state}, status)


def _manager(handler):
    injected = getattr(handler, "codex_account_manager", None)
    if injected is not None:
        return injected
    from .codex_account_route import DEFAULT_MANAGER
    return DEFAULT_MANAGER


def account_get(handler, path: str):
    query = handler.path.partition("?")[2]
    if path not in {_BASE, _BASE + "/login/result"}:
        return _reply_error(handler, "not_found", 404)
    try:
        if len(query) > 4096:
            raise ValueError("query too large")
        pairs = parse_qsl(query, keep_blank_values=True, strict_parsing=True,
                          max_num_fields=3, errors="strict")
        if path == _BASE:
            if pairs:
                raise ValueError("unexpected query")
            result = _manager(handler).read_status(handler.owner_ref)
        else:
            if (len(pairs) != 1 or pairs[0][0] != "login_id"
                    or not pairs[0][1] or len(pairs[0][1]) > 256):
                raise ValueError("exact login handle required")
            result = _manager(handler).login_result(handler.owner_ref, pairs[0][1])
    except (ValueError, UnicodeError):
        return _reply_error(handler, "bad_request", 400)
    return handler._json(*result)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def account_post(handler, path: str):
    fields = _POST_FIELDS.get(path)
    if fields is None:
        return _reply_error(handler, "not_found", 404)
    if "?" in handler.path:
        return _reply_error(handler, "bad_request", 400)
    media_type = handler.headers.get("Content-Type", "").split(";")[0].strip()
    if media_type.lower() != "application/json":
        return _reply_error(handler, "bad_request", 415)
    length = handler._content_length()
    if length is None or length < 1:
        return _reply_error(handler, "bad_request", 400)
    if length > MAX_BODY_BYTES:
        return _reply_error(handler, "bad_request", 413)
    try:
        payload = json.loads(handler.rfile.read(length),
                             object_pairs_hook=_unique_object)
        if (not isinstance(payload, dict) or set(payload) != fields
                or any(not isinstance(value, str) for value in payload.values())):
            raise ValueError("invalid action fields")
    except (ValueError, UnicodeError):
        return _reply_error(handler, "bad_request", 400)
    manager = _manager(handler)
    owner = handler.owner_ref
    if path.endswith("/login/start"):
        result = manager.start_login(owner, payload["mode"], visible_ui_action=True)
    elif path.endswith("/login/cancel"):
        result = manager.cancel_login(owner, payload["login_id"],
                                      visible_ui_action=True)
    else:
        result = manager.logout(owner, visible_ui_action=True)
    return handler._json(*result)
