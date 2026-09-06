"""browser_route.py -- the browser and desktop control surface.

GET  /api/browser              every session under this run root, and whether
                               anything is bound that could actually act
GET  /api/browser/{run_id}     one session: its policy, every verdict, counts
POST /api/browser/session      open a session by fixing the policy first
POST /api/browser/action       attempt one act, admitted or refused

Opening a session before acting is not ceremony. The policy is the chain's
first record, so there is no window in which acts are judged by rules that
were not yet written down, and no way to widen the rules afterwards without
breaking the citation on everything they already judged.

`driver` in the answers is the honest part. When it is null the engine
recorded a decision and performed nothing, and the response says so rather
than letting a reader assume a screen moved.
"""
from __future__ import annotations

from .browser_control import (Refused, attempt, bound_driver, open_session,
                              session, sessions)
from .evidence_public import TransportError, error_response

ROSTER_SCHEMA = "flywheel.browser-roster/v1"
SESSION_SCHEMA = "flywheel.browser-session/v1"
ACK_SCHEMA = "flywheel.browser-ack/v1"


def _invalid(message: str) -> tuple[dict, int]:
    return error_response(TransportError("INVALID_REQUEST", message, 422))


def _unknown() -> tuple[dict, int]:
    return error_response(
        TransportError("NOT_FOUND", "unknown browser route", 404))


def handle_browser_get(path: str, *, run_root, clock) -> tuple[dict, int]:
    if path == "/api/browser":
        name, _ = bound_driver()
        return {"schema": ROSTER_SCHEMA, "read_at": clock(),
                "driver": name, "sessions": sessions(run_root)}, 200
    if not path.startswith("/api/browser/"):
        return _unknown()
    run_id = path[len("/api/browser/"):]
    if not run_id or "/" in run_id:
        return _unknown()
    try:
        body = session(run_root, run_id=run_id)
    except Refused as exc:
        return _invalid(str(exc))
    return dict(body, schema=SESSION_SCHEMA, read_at=clock()), 200


def handle_browser_post(path: str, body: dict, *, run_root,
                        clock) -> tuple[dict, int]:
    if path not in ("/api/browser/session", "/api/browser/action"):
        return _unknown()
    if not isinstance(body, dict):
        return _invalid("the request body must be an object")
    run_id = body.get("run_id")
    if not run_id:
        return _invalid("run_id names the session this belongs to")
    now = clock()
    try:
        if path == "/api/browser/session":
            record = open_session(run_root, run_id=run_id,
                                  policy=body.get("policy") or {}, at=now)
        else:
            record = attempt(run_root, run_id=run_id,
                             action=body.get("action") or {}, at=now)
    except Refused as exc:
        return _invalid(str(exc))
    return {"schema": ACK_SCHEMA, "recorded": True, "at": now,
            "event": record,
            "session": session(run_root, run_id=run_id)}, 200
