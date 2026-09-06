"""scheduler.py -- runs that start on a clock, with nobody in the room.

Every hosted peer can start a run on a schedule. The part none of them
publishes is what happened to the occurrences that did not run. A laptop
sleeps, a container is evicted, a token expires overnight, and the next
morning a dashboard says the job ran. It did run. It ran once, six hours
late, standing for an instant it never names, and the eleven occurrences
underneath it are gone.

So the unit here is the occurrence, not the run. A schedule names an
anchor and an interval, which makes every future instant computable from
two fields. Firing seals a record that carries the instant it stands for
next to the instant it actually happened, so lateness is a number rather
than a feeling. Occurrences that were passed over are named in the same
record, with the policy that passed over them.

What runs is not decided here. A schedule fires an event, and
`accountable_hooks` owns the registry that binds an event to argv. The
rules refusing a shell runner and secret-shaped text live there and are
not repeated here, because a security rule written in two files is a
security rule that can be repaired in one of them.

The chain is the falsifier. Each record cites the digest of the previous
record for its schedule, so a fire record deleted to hide a bad night
breaks `chain_intact` at the record after it.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .accountable_hooks import EVENTS
from .evidence_json import canonical_sha256
from .hash_chain import append_sealed, load_chain, seal
from .hash_chain import chain_intact as _chain_intact

SCHEDULE_SCHEMA = "flywheel.schedule/v1"
FIRE_SCHEMA = "flywheel.schedule-fire/v1"

#: What to do with occurrences that came due while nothing was running.
#: `all` replays them in order, `latest` runs the newest and names the
#: rest, `drop` runs none and names all of them. There is no default
#: policy: a schedule states which one it wants, because the answer is a
#: property of the job and guessing it is how a backlog turns into a
#: stampede.
CATCH_UP = ("all", "latest", "drop")

#: A schedule may not fire more often than this. A one-second interval
#: over a day is 86,400 subprocess launches, which is a denial of service
#: an operator writes by accident.
MIN_INTERVAL_SECONDS = 60

#: The most occurrences one evaluation will name. A schedule anchored a
#: year back would otherwise produce half a million strings before any
#: policy could refuse them. The count above the cap is reported rather
#: than dropped in silence.
MAX_BACKLOG = 256


def _refuse(message: str) -> None:
    raise ValueError(message)


def _parse(stamp: str) -> datetime:
    """Read an ISO-8601 instant and insist it carries a zone.

    A naive stamp compares against an aware one by raising, which would
    surface as a 500 on the route rather than as the refusal it is. A
    schedule without a zone is ambiguous twice a year anyway.
    """
    try:
        moment = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"not an ISO-8601 instant: {stamp!r}") from None
    if moment.tzinfo is None:
        _refuse(f"instant carries no timezone: {stamp!r}")
    return moment.astimezone(timezone.utc)


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def define_schedule(*, schedule_id: str, event: str, every_seconds: int,
                    starts_at: str, catch_up: str,
                    created_at: str) -> dict:
    """Seal a schedule. Every field is checked before it is stored."""
    if not str(schedule_id).startswith("sched_"):
        _refuse("schedule id is not a schedule ref")
    if event not in EVENTS:
        _refuse(f"unknown event: {event!r}")
    if not isinstance(every_seconds, int) or isinstance(every_seconds, bool):
        _refuse("every_seconds is a whole number of seconds")
    if every_seconds < MIN_INTERVAL_SECONDS:
        _refuse(f"the floor on a schedule interval is "
                f"{MIN_INTERVAL_SECONDS}s; asked for {every_seconds}s")
    if catch_up not in CATCH_UP:
        _refuse(f"catch_up is one of {CATCH_UP}, not {catch_up!r}")
    anchor = _parse(starts_at)
    schedule = {
        "schema": SCHEDULE_SCHEMA,
        "schedule_id": schedule_id,
        "event": event,
        "every_seconds": every_seconds,
        "starts_at": _stamp(anchor),
        "catch_up": catch_up,
        "created_at": created_at,
    }
    schedule["schedule_sha256"] = canonical_sha256(
        {k: v for k, v in schedule.items() if k != "schedule_sha256"})
    return schedule


def pending(schedule: dict, *, last_fired_for: str = "", now: str) -> dict:
    """Which occurrences are owed, and how many were too many to name.

    An occurrence is owed when its instant is at or before `now` and
    strictly after the instant the last fire stood for. Comparing against
    the instant rather than against the wall clock of that fire is what
    keeps a late run from swallowing the occurrence behind it.
    """
    anchor = _parse(schedule["starts_at"])
    step = timedelta(seconds=int(schedule["every_seconds"]))
    edge = anchor - timedelta(seconds=1)
    if last_fired_for:
        edge = max(edge, _parse(last_fired_for))
    horizon = _parse(now)
    if horizon < anchor:
        return {"occurrences": [], "due": 0, "truncated": 0}
    elapsed = (horizon - anchor) // step
    last_due = anchor + elapsed * step
    if last_due <= edge:
        return {"occurrences": [], "due": 0, "truncated": 0}
    first_index = max(0, ((edge - anchor) // step) + 1)
    due = int(elapsed - first_index) + 1
    shown = min(due, MAX_BACKLOG)
    start = first_index + (due - shown)
    occurrences = [_stamp(anchor + (start + i) * step) for i in range(shown)]
    return {"occurrences": occurrences, "due": due, "truncated": due - shown}


def plan_fires(schedule: dict, owed: dict) -> dict:
    """Split the owed occurrences into what runs and what is passed over.

    The passed-over list is the honest half. A policy that silently drops
    a backlog and a policy that runs it are the same log line otherwise.
    """
    policy = schedule.get("catch_up")
    if policy not in CATCH_UP:
        _refuse(f"the schedule carries an unknown catch_up: {policy!r}")
    occurrences = list(owed.get("occurrences", ()))
    if policy == "all":
        fire, skipped = occurrences, []
    elif policy == "latest":
        fire = occurrences[-1:]
        skipped = occurrences[:-1]
    else:
        fire, skipped = [], occurrences
    return {"policy": policy, "fire": fire, "skipped": skipped,
            "truncated": int(owed.get("truncated", 0))}


def fire_record(schedule: dict, *, scheduled_for: str, fired_at: str,
                prev_sha256: str, hook_receipts: list,
                skipped: list, truncated: int = 0) -> dict:
    """Seal one firing, cited to the record before it.

    `lateness_seconds` is the whole reason this record exists. A run that
    happened at all is the claim a dashboard makes; a run that happened
    four hours after the instant it stands for is a different fact, and
    only one of those two can be argued with.
    """
    scheduled = _parse(scheduled_for)
    actual = _parse(fired_at)
    record = {
        "schema": FIRE_SCHEMA,
        "schedule_id": schedule["schedule_id"],
        "schedule_sha256": schedule.get("schedule_sha256", ""),
        "event": schedule["event"],
        "scheduled_for": _stamp(scheduled),
        "fired_at": _stamp(actual),
        "lateness_seconds": int((actual - scheduled).total_seconds()),
        "hook_receipts": list(hook_receipts),
        "skipped": list(skipped),
        "truncated": int(truncated),
        "prev_sha256": prev_sha256,
    }
    return seal(record, digest_key="fire_sha256")


def chain_intact(records: list) -> bool:
    """Walk one schedule's records and check every citation.

    Returns False when a record was removed, reordered or rewritten. This
    is the control on the rest of the module: without it a bad night is
    erased by deleting a file, and every count above still reads clean.
    """
    return _chain_intact(records, schema=FIRE_SCHEMA,
                         digest_key="fire_sha256")


def last_fired_for(records: list) -> str:
    """The instant the newest record stands for, empty when none has."""
    return records[-1]["scheduled_for"] if records else ""


def schedules_path(run_root: Path) -> Path:
    return Path(run_root) / "schedules" / "schedules.json"


def fires_path(run_root: Path, schedule_id: str) -> Path:
    safe = "".join(c for c in schedule_id if c.isalnum() or c in "_-")
    return Path(run_root) / "schedules" / "fires" / f"{safe}.json"


def save_schedules(schedules: list, *, path: Path) -> Path:
    for schedule in schedules:
        if schedule.get("schema") != SCHEDULE_SCHEMA:
            _refuse("the schedule store holds only sealed schedules")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(schedules, indent=2, sort_keys=True),
                    encoding="utf-8")
    return path


def load_schedules(path: Path) -> list:
    path = Path(path)
    if not path.is_file():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        _refuse("the schedule store is not a list")
    for schedule in rows:
        if (not isinstance(schedule, dict)
                or schedule.get("schema") != SCHEDULE_SCHEMA
                or schedule.get("catch_up") not in CATCH_UP):
            _refuse("the schedule store holds an unknown or unsealed row")
    return rows


def load_fires(path: Path) -> list:
    return load_chain(path)


def append_fire(record: dict, *, path: Path) -> list:
    """Append one firing, refusing to write a history that does not verify."""
    return append_sealed(record, path=path, schema=FIRE_SCHEMA,
                         digest_key="fire_sha256")
