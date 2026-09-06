"""runner_pool.py -- machines the operator owns, taking dispatched runs.

Every hosted peer will run your job on its hardware, and none of them can
say what that machine was told to accept. The console lists rows, and a row
is a claim by the party being audited.

So membership here is an append-only chain. A machine joins by consuming a
ticket the operator minted, and it may advertise only the labels that ticket
granted, which is the reason a runner cannot enlarge itself. Dispatch matches
labels. A claim carries a lease with an instant on it, so a machine that dies
holding work returns that work by arithmetic.

Delete the enrollment of a runner that ran something and the citation breaks
at the record after it, so the next write is refused rather than accepted
onto a rewritten history.

What is not claimed: this does not attest what the machine is. A runner is
whatever answered with a valid ticket, and a compromised host with a real
ticket is a real member of the pool. The property is operator control over
membership, not remote attestation of hardware.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from .hash_chain import append_sealed, head_digest, load_chain, seal
from .hash_chain import chain_intact as _chain_intact

EVENT_SCHEMA = "flywheel.runner-event/v1"
DIGEST_KEY = "event_sha256"

#: The longest a runner may hold work before the pool takes it back. An
#: unbounded lease is the same thing as losing the job, because the only
#: way out is an operator noticing a queue that stopped moving.
MAX_LEASE_SECONDS = 3600

#: The shortest lease worth writing. Below this a slow network turns a
#: healthy runner into an expired one while its first heartbeat is in
#: flight, and the job gets handed to a second machine that also runs it.
MIN_LEASE_SECONDS = 30

#: How many labels one ticket may grant. Labels are a matching key, not a
#: description, and a hundred of them on one machine means the operator has
#: stopped choosing which work lands where.
MAX_LABELS = 16

_ID_EXTRA = "_-."


def _refuse(message: str) -> None:
    raise ValueError(message)


def _ident(value, field: str) -> str:
    """A pool id is a path segment and a chain key, so it is bounded here."""
    text = str(value or "").strip()
    if not text or len(text) > 64:
        _refuse(f"{field} must be 1 to 64 characters")
    if not all(c.isalnum() or c in _ID_EXTRA for c in text):
        _refuse(f"{field} may hold letters, digits, dot, dash and underscore")
    return text


def _labels(value, field: str = "labels") -> list:
    if not isinstance(value, (list, tuple)):
        _refuse(f"{field} must be a list")
    if len(value) > MAX_LABELS:
        _refuse(f"{field} may name at most {MAX_LABELS} entries")
    return sorted({_ident(v, f"{field} entry") for v in value})


def _lease(value) -> int:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        _refuse("lease_seconds must be a whole number of seconds")
    if not MIN_LEASE_SECONDS <= seconds <= MAX_LEASE_SECONDS:
        _refuse(f"lease_seconds must be {MIN_LEASE_SECONDS} to "
                f"{MAX_LEASE_SECONDS}")
    return seconds


def _parse(stamp: str) -> datetime:
    """Read an ISO-8601 instant and insist it carries a zone.

    A naive stamp compares against an aware one by raising, which arrives at
    the route as a 500 rather than as the refusal it is.
    """
    try:
        moment = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        _refuse(f"not an ISO-8601 instant: {stamp!r}")
    if moment.tzinfo is None:
        _refuse(f"instant carries no timezone: {stamp!r}")
    return moment.astimezone(timezone.utc)


def _stamp(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def chain_path(run_root) -> Path:
    return Path(run_root) / "runners" / "pool-chain.json"


def load_events(run_root) -> list:
    return load_chain(chain_path(run_root))


def chain_intact(records) -> bool:
    return _chain_intact(records, schema=EVENT_SCHEMA, digest_key=DIGEST_KEY)


def pool_state(records, *, now: str) -> dict:
    """Fold the chain into tickets, runners and jobs as of one instant.

    Expiry is computed here rather than written, because the instant a lease
    lapses nothing is running to record it. A job whose lease is behind `now`
    reads as queued again, and the count of those is reported so a pool
    losing machines looks different from a pool that is merely busy.
    """
    moment = _parse(now)
    tickets, runners, jobs = {}, {}, {}
    for record in records:
        kind = record.get("kind")
        if kind == "ticket":
            tickets[record["ticket_id"]] = {"labels": list(record["labels"]),
                                            "used_by": None}
        elif kind == "enroll":
            held = tickets.setdefault(record["ticket_id"],
                                      {"labels": [], "used_by": None})
            held["used_by"] = record["runner_id"]
            runners[record["runner_id"]] = {"labels": list(record["labels"]),
                                            "enrolled": True,
                                            "enrolled_at": record["at"]}
        elif kind == "retire" and record["runner_id"] in runners:
            runners[record["runner_id"]]["enrolled"] = False
        elif kind == "dispatch":
            jobs[record["job_id"]] = {"requires": list(record["requires"]),
                                      "state": "queued", "runner_id": None,
                                      "lease_expires": None, "ok": None}
        elif kind == "claim" and record["job_id"] in jobs:
            jobs[record["job_id"]].update(state="leased",
                                          runner_id=record["runner_id"],
                                          lease_expires=record["lease_expires"])
        elif kind == "complete" and record["job_id"] in jobs:
            jobs[record["job_id"]].update(state="done", ok=bool(record["ok"]),
                                          lease_expires=None)
    lapsed = 0
    for job in jobs.values():
        if job["state"] == "leased" and _parse(job["lease_expires"]) <= moment:
            job.update(state="queued", runner_id=None, lease_expires=None)
            lapsed += 1
    return {"tickets": tickets, "runners": runners, "jobs": jobs,
            "leases_lapsed": lapsed}


def _open(run_root, *, now: str):
    path = chain_path(run_root)
    records = load_chain(path)
    if records and not chain_intact(records):
        _refuse("the runner chain is broken")
    return path, records, pool_state(records, now=now)


def _write(path, records, record: dict) -> dict:
    sealed = seal(dict(record, schema=EVENT_SCHEMA,
                       prev_sha256=head_digest(records, digest_key=DIGEST_KEY)),
                  digest_key=DIGEST_KEY)
    append_sealed(sealed, path=path, schema=EVENT_SCHEMA, digest_key=DIGEST_KEY)
    return sealed


def mint_ticket(run_root, *, ticket_id, labels, at: str) -> dict:
    """Grant one machine permission to join, carrying named labels.

    The route reaching this sits under private custody, so a machine that can
    talk to the gateway still cannot write itself a ticket.
    """
    ticket_id = _ident(ticket_id, "ticket_id")
    granted = _labels(labels)
    path, records, state = _open(run_root, now=at)
    if ticket_id in state["tickets"]:
        _refuse(f"ticket {ticket_id} was already minted")
    return _write(path, records, {"kind": "ticket", "at": at,
                                  "ticket_id": ticket_id, "labels": granted})


def enroll(run_root, *, runner_id, ticket_id, labels, at: str) -> dict:
    """Join the pool by consuming a ticket, claiming a subset of its labels."""
    runner_id = _ident(runner_id, "runner_id")
    ticket_id = _ident(ticket_id, "ticket_id")
    wanted = _labels(labels)
    path, records, state = _open(run_root, now=at)
    ticket = state["tickets"].get(ticket_id)
    if ticket is None:
        _refuse(f"no ticket {ticket_id}")
    if ticket["used_by"]:
        _refuse(f"ticket {ticket_id} was spent by {ticket['used_by']}")
    if runner_id in state["runners"] and state["runners"][runner_id]["enrolled"]:
        _refuse(f"{runner_id} is already enrolled")
    ungranted = [lab for lab in wanted if lab not in ticket["labels"]]
    if ungranted:
        _refuse(f"ticket {ticket_id} does not grant {', '.join(ungranted)}")
    return _write(path, records, {"kind": "enroll", "at": at,
                                  "runner_id": runner_id,
                                  "ticket_id": ticket_id, "labels": wanted})


def retire(run_root, *, runner_id, at: str) -> dict:
    """Drop a machine from the pool. Its history stays; its future stops."""
    runner_id = _ident(runner_id, "runner_id")
    path, records, state = _open(run_root, now=at)
    runner = state["runners"].get(runner_id)
    if runner is None or not runner["enrolled"]:
        _refuse(f"{runner_id} is not an enrolled runner")
    return _write(path, records, {"kind": "retire", "at": at,
                                  "runner_id": runner_id})


def dispatch(run_root, *, job_id, requires, at: str) -> dict:
    """Queue work for whichever enrolled machine carries the labels."""
    job_id = _ident(job_id, "job_id")
    needed = _labels(requires, "requires")
    path, records, state = _open(run_root, now=at)
    if job_id in state["jobs"]:
        _refuse(f"job {job_id} was already dispatched")
    return _write(path, records, {"kind": "dispatch", "at": at,
                                  "job_id": job_id, "requires": needed})


def claim(run_root, *, job_id, runner_id, lease_seconds, at: str) -> dict:
    """Take queued work under a lease that expires on its own."""
    job_id = _ident(job_id, "job_id")
    runner_id = _ident(runner_id, "runner_id")
    seconds = _lease(lease_seconds)
    path, records, state = _open(run_root, now=at)
    runner = state["runners"].get(runner_id)
    if runner is None or not runner["enrolled"]:
        _refuse(f"{runner_id} is not an enrolled runner")
    job = state["jobs"].get(job_id)
    if job is None:
        _refuse(f"no dispatched job {job_id}")
    if job["state"] == "done":
        _refuse(f"job {job_id} is finished")
    if job["state"] == "leased":
        _refuse(f"job {job_id} is held by {job['runner_id']} until "
                f"{job['lease_expires']}")
    missing = [lab for lab in job["requires"] if lab not in runner["labels"]]
    if missing:
        _refuse(f"{runner_id} does not carry {', '.join(missing)}")
    expires = _stamp(_parse(at) + timedelta(seconds=seconds))
    return _write(path, records, {"kind": "claim", "at": at, "job_id": job_id,
                                  "runner_id": runner_id,
                                  "lease_seconds": seconds,
                                  "lease_expires": expires})


def complete(run_root, *, job_id, runner_id, ok, at: str) -> dict:
    """Report the outcome, allowed only from the machine holding the lease."""
    job_id = _ident(job_id, "job_id")
    runner_id = _ident(runner_id, "runner_id")
    path, records, state = _open(run_root, now=at)
    job = state["jobs"].get(job_id)
    if job is None:
        _refuse(f"no dispatched job {job_id}")
    if job["state"] != "leased":
        _refuse(f"job {job_id} is {job['state']}, so nobody holds its lease")
    if job["runner_id"] != runner_id:
        _refuse(f"job {job_id} is held by {job['runner_id']}, not {runner_id}")
    return _write(path, records, {"kind": "complete", "at": at,
                                  "job_id": job_id, "runner_id": runner_id,
                                  "ok": bool(ok)})


def roster(run_root, *, now: str) -> dict:
    """The pool as of one instant, with the chain verdict at the top.

    A reader scanning machines will not open every row, so the one verdict
    meaning the history cannot be trusted is lifted out of the rows.
    """
    records = load_events(run_root)
    intact = chain_intact(records) if records else True
    state = pool_state(records, now=now) if intact else {
        "tickets": {}, "runners": {}, "jobs": {}, "leases_lapsed": 0}
    jobs = state["jobs"]
    return {"chain_intact": intact,
            "events": len(records),
            "now": now,
            "runners": [dict(body, runner_id=rid)
                        for rid, body in sorted(state["runners"].items())],
            "jobs": [dict(body, job_id=jid) for jid, body in sorted(jobs.items())],
            "queued": sum(1 for j in jobs.values() if j["state"] == "queued"),
            "leased": sum(1 for j in jobs.values() if j["state"] == "leased"),
            "leases_lapsed": state["leases_lapsed"],
            "tickets_unspent": sum(1 for t in state["tickets"].values()
                                   if not t["used_by"])}
