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


def _presence_post(handler):
    """A challenge answered by the adopted method, inside the gateway. The
    prompt text comes from the plan, grant or settings bound to the digest,
    never from the request (I17)."""
    from harness import trace_presence as presence
    from harness.trace_presence_summary import describe
    state = handler.flywheel_home / "state"
    body = _body(handler, {"kind", "plan_digest"})
    if body is None:
        return handler._json(capture.error("INVALID_REQUEST", "unexpected fields"), 422)
    kind, digest = body.get("kind"), body.get("plan_digest")
    try:
        if kind not in presence.KINDS or type(digest) is not str or len(digest) != 64:
            raise presence.PresenceError("PRESENCE_INVALID")
        summary = describe(handler.flywheel_home, handler.owner_ref, kind, digest)
        ref = presence.confirm(state, handler.owner_ref, kind, digest, summary)
    except presence.PresenceError as exc:
        code = {"PRESENCE_INVALID": 422, "PRESENCE_UNDESCRIBED": 404}.get(exc.code, 403)
        return handler._json(capture.error(exc.code, "presence refused"), code)
    status = presence.presence_status(state, handler.owner_ref)
    return handler._json({"schema": "flywheel.presence-challenge-result/v1", "ref": ref,
                          "method": status["method"], "summary": summary,
                          "presence_statement": status["statement"]})


def _delete_post(handler, path: str):
    from harness.trace_delete_apply import apply_plan
    from harness.trace_delete_plan import PlanError, make_plan
    from harness.trace_presence import PresenceError
    apply = path.endswith("/apply")
    body = _body(handler, {"plan_digest", "presence_ref"} if apply
                 else {"trace_refs", "turn_refs", "import_refs", "session"})
    if body is None:
        return handler._json(capture.error("INVALID_REQUEST", "unexpected fields"), 422)
    try:
        if apply:
            report = apply_plan(handler.flywheel_home, handler.owner_ref,
                                body.get("plan_digest"), body.get("presence_ref"))
            return handler._json({"schema": "flywheel.trace-delete-report/v1", **report})
        return handler._json(make_plan(handler.flywheel_home, handler.owner_ref, body))
    except PresenceError as exc:
        return handler._json(capture.error(exc.code, "presence required"), 403)
    except PlanError as exc:
        status = {"NOT_FOUND": 404, "INVALID_SELECTION": 422}.get(exc.code, 409)
        return handler._json(capture.error(exc.code, "deletion refused"), status)


def _export_post(handler):
    """Export through a one-use grant the local CLI wrote (I12): the body
    names the grant, never a path."""
    from harness.trace_export import export
    from harness.trace_export_dest import ExportError, take_grant
    from harness.trace_presence import PresenceError
    body = _body(handler, {"grant_ref", "presence_ref", "sync_presence_ref"})
    if body is None:
        return handler._json(capture.error("INVALID_REQUEST", "unexpected fields"), 422)
    try:
        out, options = take_grant(handler.flywheel_home, handler.owner_ref,
                                  body.get("grant_ref"))
        report = export(handler.flywheel_home, handler.owner_ref, out, body.get("presence_ref"),
                        sync_presence_ref=body.get("sync_presence_ref"), **options)
    except PresenceError as exc:
        return handler._json(capture.error(exc.code, "presence required"), 403)
    except ExportError as exc:
        status = 404 if exc.code == "GRANT_NOT_FOUND" else 409
        return handler._json(capture.error(exc.code, "export refused"), status)
    return handler._json({"schema": "flywheel.trace-export-report/v1", **report})


def _bench_post(handler):
    """Bench replay (7.8): endpoints are required, and a replay needs
    presence bound to the grant whose summary lists every goal."""
    from harness.trace_bench_grant import handle
    body = _body(handler, {"endpoints", "grant_digest", "presence_ref"})
    if body is None:
        return handler._json(capture.error("INVALID_REQUEST", "unexpected fields"), 422)
    doc, status = handle(handler.flywheel_home, handler.owner_ref, body)
    return handler._json(doc, status)


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


def _off_loopback(handler, path: str):
    if path.startswith(protocol.PREFIX) and not capture.loopback_only(handler):
        return handler._json(capture.error("NOT_FOUND", "no such trace route"), 404)
    return None


def route_get(handler, path: str, qs: str):
    refused = _off_loopback(handler, path)
    if refused is not None:
        return refused
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
    refused = _off_loopback(handler, path)
    if refused is not None:
        return refused
    if path.startswith(protocol.PREFIX) and not capture.host_ok(handler):
        return handler._json(capture.REFUSED, 401)
    if path in (protocol.PROMPT_PATH, protocol.STOP_PATH, protocol.FREEZE_PATH,
                protocol.SESSION_PATH):
        raw, sent = capture.signed_body(handler, "POST")
        if raw is None:
            return sent
        if path == protocol.FREEZE_PATH:
            return capture.freeze(handler, raw)
        if path == protocol.SESSION_PATH:
            return capture.session(handler, raw)
        return capture.turn(handler, "prompt" if path == protocol.PROMPT_PATH else "stop", raw)
    if path == "/api/traces/presence":
        return _presence_post(handler)
    if path in ("/api/traces/delete/plan", "/api/traces/delete/apply"):
        return _delete_post(handler, path)
    if path == "/api/traces/export":
        return _export_post(handler)
    if path == "/api/traces/bench":
        return _bench_post(handler)
    return handler._json(capture.error("NOT_FOUND", "no such trace route"), 404)
