"""Every `/api/traces/*` route, and the scaffold route moved out of the gateway.

`harness/gateway.py` is frozen at its line count, so trace custody routes
live here and later packages add theirs here too. Each module this file uses
is imported with a literal `from harness.x import` so a frozen build finds it.

Capture routes (`/api/traces/capture/*`) do not take the bearer token. The
hello takes no credential at all and answers with a proof; every other
capture route needs a request signed under a key derived from the token
(harness/gateway_request_sig.py), checked before any body is parsed. Other
`/api/traces/*` routes sit under private custody and pass the bearer check
in the gateway first.
"""
from __future__ import annotations

import hashlib
import json

from harness.capture_hooks import protocol
from harness.gateway_auth import _host_of
from harness.gateway_request_sig import STATE

MAX_CAPTURE_BODY = 4 * 1024 * 1024
DEFAULT_EFFECTIVE = {"content": "off", "archive_transcripts": "off", "freeze_urls": "off",
                     "pending_ttl_hours": 24, "pending_change": False}
_REFUSED = {"schema": "flywheel.evidence-transport-error/v1",
            "error": {"code": "AUTH_REQUIRED", "message": "gateway authentication is required"}}


def _error(code: str, message: str) -> dict:
    return {"schema": "flywheel.evidence-transport-error/v1",
            "error": {"code": code, "message": message}}


def _bound(handler) -> tuple[str, int]:
    host, port = handler.server.server_address[:2]
    return host, port


def _host_ok(handler) -> bool:
    return _host_of(handler.headers) in handler.allowed_hosts


def _hello(handler, qs: str):
    from urllib.parse import parse_qs
    if not handler.auth_token:
        return handler._json(_error("CAPTURE_UNAVAILABLE", "the gateway has no token"), 503)
    cn = (parse_qs(qs).get("cn") or [""])[0]
    host, port = _bound(handler)
    body = STATE.hello(handler.auth_token, cn, host, port)
    if body is None:
        return handler._json(_error("INVALID_REQUEST", "hello refused"), 429)
    return handler._json({**body, "effective": effective(handler)})


def effective(handler) -> dict:
    """Capture settings in effect; FW-05 replaces the defaults with adoption."""
    return dict(DEFAULT_EFFECTIVE)


def _signed_body(handler, method: str):
    """(raw body, None) when the signature holds, else (None, response sent)."""
    raw = b""
    if method == "POST":
        length = handler._content_length()
        if length is None or length > MAX_CAPTURE_BODY:
            return None, handler._json(_error("INVALID_REQUEST", "body too large"), 413)
        ctype = (handler.headers.get("Content-Type", "") or "").split(";", 1)[0].strip()
        if ctype.lower() != "application/json":
            return None, handler._json(_REFUSED, 401)
        raw = handler.rfile.read(length)
    host, port = _bound(handler)
    if not STATE.verify(handler.auth_token, handler.headers.get("Authorization", ""),
                        method, handler.path, raw, host, port):
        return None, handler._json(_REFUSED, 401)
    from harness.operation_grants import load_or_create_owner_ref
    handler.owner_ref = load_or_create_owner_ref(handler.flywheel_home)
    return raw, None


def _capture_receipt(handler, raw: bytes):
    """A v1 turn receipt from hashes only. URL freezing is off on this path
    (FW-05b makes it a separate opt-in), so nothing is fetched and no URL is
    stored."""
    try:
        doc = json.loads(raw or b"{}")
    except ValueError:
        doc = None
    if type(doc) is not dict:
        return handler._json(_error("INVALID_REQUEST", "body is not a JSON object"), 422)
    prompt, answer = doc.get("prompt") or "", doc.get("answer") or ""
    if type(prompt) is not str or type(answer) is not str:
        return handler._json(_error("INVALID_REQUEST", "prompt and answer are text"), 422)
    from harness.scaffold import RECEIPT_SCHEMA
    from harness.store import put_entity
    receipt = {"schema": RECEIPT_SCHEMA,
               "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
               "answer_sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
               "sources_frozen": [], "degraded": [], "url_freeze": "off"}
    stored = put_entity("turn-receipt", receipt, home=handler.flywheel_home)
    return handler._json({"schema": RECEIPT_SCHEMA, "eid": stored["eid"],
                          "chain_hash": stored["chain_hash"]})


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
        return handler._json(_error("INVALID_REQUEST", "unexpected fields"), 422)
    try:
        if path.endswith("/approve"):
            presence.approve_from_desktop(state, handler.owner_ref, body.get("ref"))
            return handler._json({"schema": "flywheel.presence-approval/v1", "ok": True})
        kind, digest = body.get("kind"), body.get("plan_digest")
        ref = presence.confirm(state, handler.owner_ref, kind, digest,
                               f"{kind} {str(digest)[:12]}")
    except presence.PresenceError as exc:
        code = 422 if exc.code == "PRESENCE_INVALID" else 403
        return handler._json(_error(exc.code, "presence refused"), code)
    status = presence.presence_status(state, handler.owner_ref)
    return handler._json({"schema": "flywheel.presence-challenge-result/v1", "ref": ref,
                          "method": status["method"],
                          "presence_statement": status["statement"]})


def route_get(handler, path: str, qs: str):
    if path.startswith(protocol.PREFIX) and not _host_ok(handler):
        return handler._json(_REFUSED, 401)
    if path == protocol.HELLO_PATH:
        return _hello(handler, qs)
    if path == "/api/traces/presence/pending":
        from harness.trace_presence import PresenceStore
        pending = PresenceStore(handler.flywheel_home / "state", handler.owner_ref).pending()
        return handler._json({"schema": "flywheel.presence-pending/v1", "pending": pending})
    if path == protocol.PING_PATH:
        raw, sent = _signed_body(handler, "GET")
        return sent if raw is None else handler._json({"schema": "flywheel.capture-ping/v1",
                                                       "ok": True})
    return handler._json(_error("NOT_FOUND", "no such trace route"), 404)


def route_post(handler, path: str):
    if path == "/api/scaffold":
        return _scaffold(handler)
    if path.startswith(protocol.PREFIX) and not _host_ok(handler):
        return handler._json(_REFUSED, 401)
    if path in ("/api/traces/presence", "/api/traces/presence/approve"):
        return _presence_post(handler, path)
    if path == protocol.SCAFFOLD_PATH:
        raw, sent = _signed_body(handler, "POST")
        return sent if raw is None else _capture_receipt(handler, raw)
    return handler._json(_error("NOT_FOUND", "no such trace route"), 404)
