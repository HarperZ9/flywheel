"""I6: retention is owner-set, keep is the default, and a change is an owner
decision. Keep over a simulated year deletes nothing; an edited policy is
pending until adopted with presence; the first run after adoption only
plans; a 30-day rule then deletes exactly the older items through the
deletion engine, with a tombstone; a run over the share threshold stops at
its plan; each run writes one ledger entry and one witness event; a failing
run leaves its plan pending and visible."""
import json
import os
import time

import pytest

from delete_fixtures import OWNER, plant_trace
from harness import trace_retention as policy
from harness import trace_retention_schedule as schedule
from harness.trace_custody_ledger import CustodyLedger
from harness.trace_presence import PresenceError, confirm
from harness.trace_tombstones import TombstoneLedger
from harness.trace_witness import MemorySink
from trace_enc_fakes import StreamTestProvider, using

DAY = 86400.0


@pytest.fixture
def home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "state").mkdir(parents=True)
    (home / "owner.ref").write_text(OWNER)
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    monkeypatch.setenv("FLYWHEEL_RUN_ROOT", str(tmp_path / "run"))
    with using(StreamTestProvider()):
        yield home


def _traces(home, count: int, old: int) -> list[str]:
    """`count` gateway traces; the first `old` of them stored 40 days ago."""
    refs = [plant_trace(home, operation=f"op_{i:032x}") for i in range(count)]
    base = home / "state" / "gateway-agent-traces" / "v1" / "owners" / OWNER
    stamp = time.time() - 40 * DAY
    for i in range(old):
        for path in (base / f"op_{i:032x}").iterdir():
            os.utime(path, (stamp, stamp))
    return refs


def _live(home) -> set[str]:
    return {item["ref"] for item in policy.items(home, OWNER) if item["store"] == "S1"}


def _adopt(home, doc: dict, sink) -> None:
    policy.write_file(home, doc)
    digest = policy.digest(policy.read_file(home)[0])
    ref = confirm(home / "state", OWNER, "retention_adopt", digest, "adopt")
    policy.adopt(home, OWNER, ref, sink=sink)


def _runs(home) -> list[dict]:
    return [e for e in CustodyLedger(home, OWNER).entries() if e["kind"] == "retention_run"]


def _rule(share=None) -> dict:
    doc = {"action": "rules", "rules": [{"store": "S1", "max_age_days": 30,
                                         "reason_code": "older_than_30_days"}]}
    return {**doc, **({"max_share_per_run": share} if share is not None else {})}


def test_default_keep_over_a_simulated_year_deletes_nothing(home):
    refs = set(_traces(home, 3, old=3))
    for day in range(0, 366, 30):
        result = schedule.run(home, OWNER, now=time.time() + day * DAY, sink=MemorySink())
        assert result["state"] == "KEEP"
    assert _live(home) == refs
    assert _runs(home) == [] and not schedule.should_schedule(home, OWNER)
    assert schedule.start_if_adopted(home) is None
    assert policy.effective(home, OWNER)["action"] == "keep"


def test_an_edited_policy_is_pending_until_adopted_with_presence(home):
    _traces(home, 2, old=2)
    (home / policy.FILENAME).write_text(json.dumps(_rule()))
    state = policy.effective(home, OWNER)
    assert state["pending_change"] and state["action"] == "keep"
    assert schedule.run(home, OWNER, sink=MemorySink())["state"] == "KEEP"
    with pytest.raises(PresenceError):
        policy.adopt(home, OWNER, "prs_" + "0" * 32, sink=MemorySink())
    digest = policy.digest(policy.read_file(home)[0])
    ref = confirm(home / "state", OWNER, "retention_adopt", digest, "adopt")
    policy.adopt(home, OWNER, ref, sink=MemorySink())
    after = policy.effective(home, OWNER)
    assert not after["pending_change"] and after["action"] == "rules"
    assert schedule.should_schedule(home, OWNER)


def test_first_run_only_plans_then_the_next_deletes_exactly_the_older_items(home):
    sink = MemorySink()
    refs = _traces(home, 4, old=2)
    _adopt(home, _rule(share=0.5), sink)
    first = schedule.run(home, OWNER, sink=sink)
    assert first["state"] == "PLANNED" and first["items"] == 2
    assert _live(home) == set(refs)
    second = schedule.run(home, OWNER, sink=sink)
    assert second["state"] == "APPLIED", second
    assert _live(home) == set(refs[2:])
    tombstones = TombstoneLedger(home / "state", OWNER).entries()
    assert len(tombstones) == 1 and tombstones[0]["reason_code"] == "retention"
    assert [e["fields"]["applied"] for e in _runs(home)] == [False, True]
    assert [e["kind"] for e in sink.read()].count("retention_run") == 2
    assert not any(e["kind"] == "deletion" for e in CustodyLedger(home, OWNER).entries())


def test_a_run_over_the_share_threshold_stops_at_its_plan(home):
    refs = _traces(home, 4, old=2)
    _adopt(home, _rule(), MemorySink())
    schedule.run(home, OWNER, sink=MemorySink())
    stopped = schedule.run(home, OWNER, sink=MemorySink())
    assert stopped["state"] == "STOPPED_AT_PLAN" and stopped["share"]["S1"] == 0.5
    assert _live(home) == set(refs)
    pending = schedule.status(home, OWNER)["pending_plan"]
    assert pending["plan_digest"] == stopped["plan_digest"] and pending["items"] == 2
    ref = confirm(home / "state", OWNER, "retention_apply", pending["plan_digest"], "apply")
    applied = schedule.apply_pending(home, OWNER, pending["plan_digest"], ref, sink=MemorySink())
    assert applied["state"] == "APPLIED" and _live(home) == set(refs[2:])
    assert schedule.status(home, OWNER)["pending_plan"] is None


def test_a_manual_apply_needs_the_pending_digest_and_presence(home):
    _traces(home, 4, old=2)
    _adopt(home, _rule(), MemorySink())
    digest = schedule.run(home, OWNER, sink=MemorySink())["plan_digest"]
    with pytest.raises(PresenceError):
        schedule.apply_pending(home, OWNER, digest, "prs_" + "1" * 32, sink=MemorySink())
    other = "f" * 64
    ref = confirm(home / "state", OWNER, "retention_apply", other, "apply")
    assert schedule.apply_pending(home, OWNER, other, ref,
                                  sink=MemorySink())["state"] == "PLAN_NOT_PENDING"


def test_a_failing_run_leaves_its_plan_pending_and_visible(home, monkeypatch):
    from harness import trace_delete_apply
    refs = _traces(home, 4, old=2)
    _adopt(home, _rule(share=0.5), MemorySink())
    schedule.run(home, OWNER, sink=MemorySink())

    def fail(*args, **kwargs):
        raise OSError("disk went away")
    monkeypatch.setattr(trace_delete_apply, "apply_authorized", fail)
    failed = schedule.run(home, OWNER, sink=MemorySink())
    assert failed["state"] == "FAILED" and failed["reason"] == "OSError"
    assert _live(home) == set(refs)
    shown = schedule.status(home, OWNER)
    assert shown["pending_plan"]["plan_digest"] == failed["plan_digest"]
    assert shown["last_run"]["state"] == "FAILED"
    assert _runs(home)[-1]["fields"]["applied"] is False


def test_status_and_the_prompt_hook_show_what_waits_for_the_owner(tmp_path, monkeypatch):
    from capture_channel_fixture import prompt_event, run_hook, running_gateway
    from harness.trace_inventory_scan import scan
    home, work = tmp_path / "gw", tmp_path / "work"
    home.mkdir()
    work.mkdir()
    with running_gateway(home, monkeypatch):
        (home / policy.FILENAME).write_text(json.dumps(_rule()))
        proc = run_hook(home, "prompt", prompt_event(), cwd=work)
        monkeypatch.setenv("FLYWHEEL_HOME", str(home))
        doc = scan()
    assert doc["retention"]["pending_change"] is True
    assert "flywheel traces retention show" in json.loads(proc.stdout)["systemMessage"]


def test_the_gateway_scheduler_runs_at_start_under_an_adopted_rule(home, monkeypatch):
    from harness import trace_witness
    monkeypatch.setattr(trace_witness, "default_sink", trace_witness.MemorySink)
    _traces(home, 2, old=1)
    _adopt(home, _rule(share=1.0), MemorySink())
    scheduler = schedule.start_if_adopted(home)
    assert scheduler is not None
    deadline = time.time() + 20
    while not _runs(home) and time.time() < deadline:
        scheduler.stop.wait(0.05)
    scheduler.stop.set()
    scheduler.thread.join(5)
    assert [e["fields"]["reason_code"] for e in _runs(home)] == ["first_run_plan_only"]
