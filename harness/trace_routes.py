"""Every `/api/traces/*` route, and the scaffold route moved out of the gateway.

`harness/gateway.py` is frozen at its line count, so trace custody routes
live here and in the modules this file imports with literal
`from harness.x import` statements, so a frozen build finds them.

Capture routes (`/api/traces/capture/*`, harness/trace_routes_capture.py) do
not take the bearer token: the hello takes no credential and every other
capture route needs a signed request. Other `/api/traces/*` routes sit under
private custody and pass the bearer check in the gateway first; none takes
an owner or a path from the request (I12).
"""
from __future__ import annotations

import json
import re

from harness import trace_routes_capture as capture
from harness.capture_hooks import protocol

_TURN = re.compile(r"/api/traces/turns/(turn_[0-9a-f]{32})\Z")


def _scaffold(handler):
    """The bearer-authenticated scaffold for other callers, as before the move."""
    req, bad = handler._req_json()
    if bad:
        return bad
    prompt, answer = str(req.get("prompt") or ""), str(req.get("answer") or "")
    if not prompt and not answer:
        return handler._json({"error": "provide 'prompt' and/or 'answer'"}, 400)
    from harness.scaffold import scaffold_answer, scaffold_turn
    cites = req.get("citations")
    return handler._json(scaffold_answer(answer, scaffold_turn(prompt),
                                         citations=cites if isinstance(cites, list) else None))


def _body(handler, allowed: set) -> dict | None:
    """A JSON object whose keys are all in `allowed` (I12: no owner, no path)."""
    length = handler._content_length()
    if length is None or length > 64 * 1024:
        return None
    try:
        doc = json.loads(handler.rfile.read(length) or b"{}")
    except ValueError:
        return None
    return doc if type(doc) is dict and set(doc) <= allowed else None


def _presence_post(handler, path: str):
    from harness import trace_presence as presence
    state = handler.flywheel_home / "state"
    body = _body(handler, {"ref"} if path.endswith("/approve") else {"kind", "plan_digest"})
    if body is None:
        return handler._json(capture.error("INVALID_REQUEST", "unexpected fields"), 422)
    try:
        if path.endswith("/approve"):
            presence.approve_from_desktop(state, handler.owner_ref, body.get("ref"))
            return handler._json({"schema": "flywheel.presence-approval/v1", "ok": True})
        kind, digest = body.get("kind"), body.get("plan_digest")
        ref = presence.confirm(state, handler.owner_ref, kind, digest,
                               f"{kind} {str(digest)[:12]}")
    except presence.PresenceError as exc:
        code = 422 if exc.code == "PRESENCE_INVALID" else 403
        return handler._json(capture.error(exc.code, "presence refused"), code)
    status = presence.presence_status(state, handler.owner_ref)
    return handler._json({"schema": "flywheel.presence-challenge-result/v1", "ref": ref,
                          "method": status["method"],
                          "presence_statement": status["statement"]})


def _turns(handler, path: str):
    from harness.trace_turn_store import TurnStore
    store = TurnStore(handler.flywheel_home, handler.owner_ref)
    if path == "/api/traces/turns":
        return handler._json({"schema": "flywheel.captured-turns/v1", "turns": store.turns()})
    match = _TURN.fullmatch(path)
    if match is None:
        return handler._json(capture.error("INVALID_REQUEST", "malformed turn ref"), 422)
    try:
        return handler._json(store.read_turn(match.group(1)))
    except FileNotFoundError:
        return handler._json(capture.error("NOT_FOUND", "no such turn"), 404)


def route_get(handler, path: str, qs: str):
    if path.startswith(protocol.PREFIX) and not capture.host_ok(handler):
        return handler._json(capture.REFUSED, 401)
    if path == protocol.HELLO_PATH:
        return capture.hello(handler, qs)
    if path == protocol.PING_PATH:
        raw, sent = capture.signed_body(handler, "GET")
        return sent if raw is None else handler._json({"schema": "flywheel.capture-ping/v1",
                                                       "ok": True})
    if path == "/api/traces/presence/pending":
        from harness.trace_presence import PresenceStore
        pending = PresenceStore(handler.flywheel_home / "state", handler.owner_ref).pending()
        return handler._json({"schema": "flywheel.presence-pending/v1", "pending": pending})
    if path == "/api/traces/turns" or path.startswith("/api/traces/turns/"):
        return _turns(handler, path)
    return handler._json(capture.error("NOT_FOUND", "no such trace route"), 404)


def route_post(handler, path: str):
    if path == "/api/scaffold":
        return _scaffold(handler)
    if path.startswith(protocol.PREFIX) and not capture.host_ok(handler):
        return handler._json(capture.REFUSED, 401)
    if path in (protocol.PROMPT_PATH, protocol.STOP_PATH, protocol.FREEZE_PATH):
        raw, sent = capture.signed_body(handler, "POST")
        if raw is None:
            return sent
        if path == protocol.FREEZE_PATH:
            return capture.freeze(handler, raw)
        return capture.turn(handler, "prompt" if path == protocol.PROMPT_PATH else "stop", raw)
    if path in ("/api/traces/presence", "/api/traces/presence/approve"):
        return _presence_post(handler, path)
    return handler._json(capture.error("NOT_FOUND", "no such trace route"), 404)
