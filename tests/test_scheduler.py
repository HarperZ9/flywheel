"""Scheduled runs, and the part a scheduler usually does not publish.

Peers start runs on a clock. What none of their pages answers is what
became of the occurrences that never ran, so that is what these tests
pin: the arithmetic that says which instants were owed, the policy that
decides how many of them run, the lateness carried on each record, and
the chain that makes a deleted record visible.

The two controls worth reading first are
`test_a_deleted_record_breaks_the_chain` and
`test_a_late_fire_does_not_swallow_the_occurrence_behind_it`. Without
the first, a bad night is erased with rm. Without the second, one run
six hours late reports the same as six runs on time.
"""
import json

import pytest

from harness.scheduler import (MAX_BACKLOG, MIN_INTERVAL_SECONDS,
                               append_fire, chain_intact, define_schedule,
                               fire_record, last_fired_for, load_schedules,
                               pending, plan_fires, save_schedules)

ANCHOR = "2026-09-06T00:00:00Z"


def _sched(catch_up="all", every=3600, event="bench.completed",
           schedule_id="sched_a", starts_at=ANCHOR):
    return define_schedule(schedule_id=schedule_id, event=event,
                           every_seconds=every, starts_at=starts_at,
                           catch_up=catch_up, created_at=ANCHOR)


def test_a_schedule_is_sealed_and_normalised():
    s = _sched()
    assert s["schema"] == "flywheel.schedule/v1"
    assert s["schedule_sha256"]
    assert s["starts_at"] == ANCHOR
    reseal = define_schedule(schedule_id="sched_a", event="bench.completed",
                             every_seconds=3600,
                             starts_at="2026-09-06T02:00:00+02:00",
                             catch_up="all", created_at=ANCHOR)
    # The same instant written in another zone is the same schedule.
    assert reseal["schedule_sha256"] == s["schedule_sha256"]


@pytest.mark.parametrize("kwargs", [
    {"event": "on.everything"},
    {"every": MIN_INTERVAL_SECONDS - 1},
    {"catch_up": "whenever"},
    {"schedule_id": "a"},
    {"starts_at": "2026-09-06T00:00:00"},
    {"starts_at": "the sixth"},
])
def test_a_schedule_that_cannot_be_honoured_is_refused(kwargs):
    with pytest.raises(ValueError):
        _sched(**kwargs)


def test_the_interval_floor_stops_an_accidental_denial_of_service():
    """A one-second interval is 86,400 subprocess launches a day."""
    with pytest.raises(ValueError):
        _sched(every=1)
    assert _sched(every=MIN_INTERVAL_SECONDS)["every_seconds"] == 60


def test_owed_occurrences_are_counted_from_the_anchor():
    owed = pending(_sched(), now="2026-09-06T05:30:00Z")
    assert owed["due"] == 6
    assert owed["occurrences"][0] == ANCHOR
    assert owed["occurrences"][-1] == "2026-09-06T05:00:00Z"
    assert owed["truncated"] == 0


def test_nothing_is_owed_before_the_anchor():
    assert pending(_sched(), now="2026-09-05T23:59:59Z")["due"] == 0


def test_a_late_fire_does_not_swallow_the_occurrence_behind_it():
    """The resume point is the instant a record stands for, not its clock.

    If the cursor were the wall time of the last fire, one run six hours
    late would mark every occurrence under it as handled and they would
    never appear again. Resuming from `scheduled_for` keeps them owed.
    """
    owed = pending(_sched(), last_fired_for="2026-09-06T01:00:00Z",
                   now="2026-09-06T05:30:00Z")
    assert owed["occurrences"] == ["2026-09-06T02:00:00Z",
                                   "2026-09-06T03:00:00Z",
                                   "2026-09-06T04:00:00Z",
                                   "2026-09-06T05:00:00Z"]


def test_a_long_outage_reports_what_it_could_not_name():
    """A year-old anchor would otherwise build half a million strings.

    The cap is on the list, never on the count. `due` stays true and
    `truncated` says how far the list falls short of it, so an operator
    reading the roster sees the size of the outage rather than a number
    that quietly stopped growing.
    """
    owed = pending(_sched(every=60), now="2026-09-07T00:00:00Z")
    assert owed["due"] == 1441
    assert len(owed["occurrences"]) == MAX_BACKLOG
    assert owed["truncated"] == 1441 - MAX_BACKLOG
    # The list keeps the newest occurrences, which are the ones a policy
    # of "latest" has to choose between.
    assert owed["occurrences"][-1] == "2026-09-07T00:00:00Z"


def test_each_policy_splits_the_backlog_it_says_it_does():
    owed = pending(_sched(), now="2026-09-06T03:30:00Z")
    assert len(owed["occurrences"]) == 4
    everything = plan_fires(_sched("all"), owed)
    assert len(everything["fire"]) == 4 and everything["skipped"] == []
    newest = plan_fires(_sched("latest"), owed)
    assert newest["fire"] == ["2026-09-06T03:00:00Z"]
    assert len(newest["skipped"]) == 3
    none = plan_fires(_sched("drop"), owed)
    assert none["fire"] == [] and len(none["skipped"]) == 4


def test_a_schedule_with_an_unknown_policy_is_refused_at_plan_time():
    broken = dict(_sched(), catch_up="sometimes")
    with pytest.raises(ValueError):
        plan_fires(broken, {"occurrences": [ANCHOR]})


def test_a_fire_record_carries_the_instant_and_the_lateness():
    s = _sched()
    record = fire_record(s, scheduled_for="2026-09-06T01:00:00Z",
                         fired_at="2026-09-06T07:30:00Z", prev_sha256="",
                         hook_receipts=[], skipped=["2026-09-06T00:00:00Z"])
    assert record["lateness_seconds"] == 6 * 3600 + 1800
    assert record["scheduled_for"] != record["fired_at"]
    assert record["skipped"] == ["2026-09-06T00:00:00Z"]
    assert record["schedule_sha256"] == s["schedule_sha256"]
    assert record["fire_sha256"]


def _chain(n=3):
    s = _sched()
    records, prev = [], ""
    for i in range(n):
        record = fire_record(s, scheduled_for=f"2026-09-06T0{i}:00:00Z",
                             fired_at=f"2026-09-06T0{i}:00:05Z",
                             prev_sha256=prev, hook_receipts=[], skipped=[])
        prev = record["fire_sha256"]
        records.append(record)
    return records


def test_an_untouched_chain_verifies():
    assert chain_intact(_chain()) is True
    assert last_fired_for(_chain()) == "2026-09-06T02:00:00Z"
    assert last_fired_for([]) == ""


def test_a_deleted_record_breaks_the_chain():
    """The control on everything above it.

    Every count in this module is computed from the records on disk. If
    removing an inconvenient one left the rest verifying, an operator
    could delete the night the job failed and the roster would read
    clean.
    """
    records = _chain()
    assert chain_intact(records[:1] + records[2:]) is False


def test_a_rewritten_record_breaks_the_chain():
    records = _chain()
    records[1]["lateness_seconds"] = 0
    assert chain_intact(records) is False


def test_reordering_breaks_the_chain():
    records = _chain()
    assert chain_intact([records[1], records[0], records[2]]) is False


def test_appending_onto_a_broken_chain_is_refused(tmp_path):
    path = tmp_path / "fires.json"
    records = _chain()
    path.write_text(json.dumps(records[:1] + records[2:]), encoding="utf-8")
    with pytest.raises(ValueError):
        append_fire(records[0], path=path)


def test_the_schedule_store_refuses_an_unsealed_row(tmp_path):
    path = tmp_path / "schedules.json"
    save_schedules([_sched()], path=path)
    assert load_schedules(path)[0]["schedule_id"] == "sched_a"
    path.write_text(json.dumps([{"schedule_id": "sched_b"}]),
                    encoding="utf-8")
    with pytest.raises(ValueError):
        load_schedules(path)
