"""runner_route.py -- the self-hosted runner pool surface.

GET  /api/runners                the pool as of now: machines, work, verdict
POST /api/runners/tickets        mint one enrollment ticket (operator only)
POST /api/runners/enroll         join by spending a ticket
POST /api/runners/retire         drop a machine from the pool
POST /api/runners/dispatch       queue work behind a set of labels
POST /api/runners/claim          take queued work under a lease
POST /api/runners/complete       report the outcome of held work

The split between the ticket route and the rest is the whole custody story.
`/api/runners/tickets` sits under private custody, so minting needs the
owner's bearer token; everything else is reachable by the machines
themselves, which is what makes them useful. A runner that can talk to this
gateway can join the pool only with a ticket somebody else wrote.

Every refusal a caller can cause is a 422 with the sentence explaining it. A
broken chain is a 409 instead, because that is not a bad request, it is a
history that stopped being usable.
"""
from __future__ import annotations

from .evidence_public import TransportError, error_response
from .runner_pool import (chain_intact, claim, complete, dispatch, enroll,
                          load_events, mint_ticket, retire, roster)

ROSTER_SCHEMA = "flywheel.runner-roster/v1"
ACK_SCHEMA = "flywheel.runner-ack/v1"

#: Route suffix to the verb behind it. A table rather than a chain of ifs,
#: so adding a verb cannot silently miss the argument-shaping below.
VERBS = {"/api/runners/tickets": mint_ticket,
         "/api/runners/enroll": enroll,
         "/api/runners/retire": retire,
         "/api/runners/dispatch": dispatch,
         "/api/runners/claim": claim,
         "/api/runners/complete": complete}


def _invalid(message: str) -> tuple[dict, int]:
    return error_response(TransportError("INVALID_REQUEST", message, 422))


def _unknown() -> tuple[dict, int]:
    return error_response(
        TransportError("NOT_FOUND", "unknown runner route", 404))


def handle_runners_get(path: str, *, run_root, clock) -> tuple[dict, int]:
    """The pool at this instant.

    Leases lapse against the clock rather than against a sweep somebody has
    to run, so the answer depends on when it was asked and says so.
    """
    if path != "/api/runners":
        return _unknown()
    body = roster(run_root, now=clock())
    return dict(body, schema=ROSTER_SCHEMA), 200


def _arguments(path: str, body: dict) -> dict:
    """Shape one request body into the keyword arguments its verb takes.

    Read here rather than passed through, so a field the verb does not take
    cannot reach it and a field it does take cannot arrive under a name the
    caller invented.
    """
    if path == "/api/runners/tickets":
        return {"ticket_id": body.get("ticket_id"),
                "labels": body.get("labels", [])}
    if path == "/api/runners/enroll":
        return {"runner_id": body.get("runner_id"),
                "ticket_id": body.get("ticket_id"),
                "labels": body.get("labels", [])}
    if path == "/api/runners/retire":
        return {"runner_id": body.get("runner_id")}
    if path == "/api/runners/dispatch":
        return {"job_id": body.get("job_id"),
                "requires": body.get("requires", [])}
    if path == "/api/runners/claim":
        return {"job_id": body.get("job_id"),
                "runner_id": body.get("runner_id"),
                "lease_seconds": body.get("lease_seconds", 300)}
    return {"job_id": body.get("job_id"),
            "runner_id": body.get("runner_id"),
            "ok": body.get("ok", True)}


def handle_runners_post(path: str, body: dict, *, run_root,
                        clock) -> tuple[dict, int]:
    verb = VERBS.get(path)
    if verb is None:
        return _unknown()
    if not isinstance(body, dict):
        return _invalid("the request body must be an object")
    records = load_events(run_root)
    if records and not chain_intact(records):
        # Fail closed. Writing onto a history that does not verify would put
        # the newest, most trusted-looking record directly on top of the
        # break, which is where a reader is least likely to look for it.
        return {"schema": ACK_SCHEMA, "accepted": False,
                "refused": "the runner chain is broken"}, 409
    now = clock()
    try:
        record = verb(run_root, at=now, **_arguments(path, body))
    except ValueError as exc:
        return _invalid(str(exc))
    return {"schema": ACK_SCHEMA, "accepted": True, "at": now,
            "event": record, "pool": roster(run_root, now=now)}, 200
