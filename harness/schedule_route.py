"""schedule_route.py -- the unattended-run surface.

GET  /api/schedule            every schedule, its chain verdict, what is owed
POST /api/schedule/define     seal a schedule and store it
POST /api/schedule/tick       evaluate what is owed and fire it

The tick is a pull, not a daemon. Whatever wakes the process, a system
timer or an operator, calls it and gets back a record of what ran. A
scheduler that owns its own thread inside a web server has to be trusted
about the hours nobody was watching; this one hands back the arithmetic
and the chain, and both can be re-checked after the fact.

Firing goes through the hook registry, so a schedule with no hook
registered for its event fires nothing and says so. That is not an error.
An event with no listener is the ordinary state of a system where the
timing and the work are owned by different registrations.
"""
from __future__ import annotations

from pathlib import Path

from .accountable_hooks import (event_blocked, load_registry, run_hooks,
                                subprocess_runner)
from .evidence_public import TransportError, error_response
from .scheduler import (append_fire, chain_intact, define_schedule,
                        fire_record, fires_path, last_fired_for, load_fires,
                        load_schedules, pending, plan_fires, save_schedules,
                        schedules_path)


def _invalid(message: str) -> tuple[dict, int]:
    return error_response(TransportError("INVALID_REQUEST", message, 422))


def _unknown() -> tuple[dict, int]:
    return error_response(
        TransportError("NOT_FOUND", "unknown schedule route", 404))


def _state(schedule: dict, *, run_root: Path, now: str) -> dict:
    """One schedule as a reader needs to see it: owed work and chain verdict."""
    records = load_fires(fires_path(run_root, schedule["schedule_id"]))
    owed = pending(schedule, last_fired_for=last_fired_for(records), now=now)
    return {"schedule": schedule,
            "fires": len(records),
            "chain_intact": chain_intact(records),
            "last_fired_for": last_fired_for(records),
            "pending": owed,
            "plan": plan_fires(schedule, owed)}


def handle_schedule_get(path: str, *, run_root: Path,
                        clock) -> tuple[dict, int]:
    if path != "/api/schedule":
        return _unknown()
    now = clock()
    schedules = load_schedules(schedules_path(run_root))
    states = [_state(s, run_root=run_root, now=now) for s in schedules]
    return {"schema": "flywheel.schedule-roster/v1",
            "read_at": now,
            "count": len(states),
            # A broken chain on any schedule is the roster's headline. A
            # reader scanning a list will not open every row, so the one
            # verdict that means the history cannot be trusted is lifted
            # to the top rather than left in a nested field.
            "any_chain_broken": any(not s["chain_intact"] for s in states),
            "schedules": states}, 200


def _define(body: dict, *, run_root: Path, clock) -> tuple[dict, int]:
    required = ("schedule_id", "event", "every_seconds", "starts_at",
                "catch_up")
    if any(body.get(field) is None for field in required):
        return _invalid("the schedule definition is incomplete")
    try:
        schedule = define_schedule(
            schedule_id=str(body["schedule_id"]), event=str(body["event"]),
            every_seconds=body["every_seconds"],
            starts_at=str(body["starts_at"]),
            catch_up=str(body["catch_up"]), created_at=clock())
    except ValueError as exc:
        return _invalid(str(exc))
    path = schedules_path(run_root)
    kept = [s for s in load_schedules(path)
            if s["schedule_id"] != schedule["schedule_id"]]
    save_schedules(kept + [schedule], path=path)
    return {"schema": "flywheel.schedule-ack/v1",
            "schedule": schedule,
            "defined_at": clock()}, 200


def _tick_one(schedule: dict, *, run_root: Path, now: str,
              timeout_s: float) -> dict:
    """Fire everything the policy admits for one schedule, in order."""
    path = fires_path(run_root, schedule["schedule_id"])
    records = load_fires(path)
    if not chain_intact(records):
        # Fail closed. Appending to a history that does not verify would
        # bury the break under a record that looks fine.
        return {"schedule_id": schedule["schedule_id"], "fired": 0,
                "refused": "the fire chain for this schedule is broken"}
    owed = pending(schedule, last_fired_for=last_fired_for(records), now=now)
    plan = plan_fires(schedule, owed)
    registry = load_registry(Path(run_root) / "hooks" / "registry.json")
    fired = []
    for occurrence in plan["fire"]:
        receipts = run_hooks(schedule["event"], registry,
                             runner=subprocess_runner(timeout_s=timeout_s),
                             context={"schedule_id": schedule["schedule_id"],
                                      "scheduled_for": occurrence})
        record = fire_record(
            schedule, scheduled_for=occurrence, fired_at=now,
            prev_sha256=records[-1]["fire_sha256"] if records else "",
            hook_receipts=receipts,
            skipped=plan["skipped"] if occurrence == plan["fire"][0] else [],
            truncated=plan["truncated"] if occurrence == plan["fire"][0]
            else 0)
        records = append_fire(record, path=path)
        fired.append({"scheduled_for": occurrence,
                      "lateness_seconds": record["lateness_seconds"],
                      "fire_sha256": record["fire_sha256"],
                      "event_blocked": event_blocked(receipts),
                      "hooks_run": len(receipts)})
    return {"schedule_id": schedule["schedule_id"],
            "policy": plan["policy"],
            "fired": len(fired),
            "skipped": plan["skipped"],
            "truncated": plan["truncated"],
            "runs": fired}


def handle_schedule_post(path: str, body: dict, *, run_root: Path,
                         clock, timeout_s: float = 30.0) -> tuple[dict, int]:
    action = path.rsplit("/", 1)[-1]
    if action == "define":
        return _define(body, run_root=run_root, clock=clock)
    if action == "tick":
        now = clock()
        wanted = body.get("schedule_id", "")
        schedules = [s for s in load_schedules(schedules_path(run_root))
                     if not wanted or s["schedule_id"] == wanted]
        results = [_tick_one(s, run_root=run_root, now=now,
                             timeout_s=timeout_s) for s in schedules]
        return {"schema": "flywheel.schedule-tick/v1",
                "ticked_at": now,
                "evaluated": len(results),
                "fired": sum(r.get("fired", 0) for r in results),
                "skipped": sum(len(r.get("skipped", ())) for r in results),
                "results": results}, 200
    return _unknown()
