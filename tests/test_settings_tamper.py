"""I17: an adopted settings file counts only when it matches the latest
adoption in the verified custody ledger. A retention policy or capture
settings file written straight to disk, with no presence and no ledger
entry, changes nothing: the defaults run and status says SETTINGS_TAMPERED.
A forged run state cannot skip the first run's plan-only preview."""
import json
import time

import pytest

from delete_fixtures import OWNER, plant_trace
from harness import trace_capture_settings as capture
from harness import trace_retention as policy
from harness import trace_retention_schedule as schedule
from harness.evidence_json import canonical_bytes
from harness.trace_presence import confirm
from harness.trace_witness import MemorySink
from trace_enc_fakes import StreamTestProvider, using

DAY = 86400.0
DELETE_ALL = {"action": "rules", "max_share_per_run": 1,
              "rules": [{"store": "S1", "max_age_days": 0, "reason_code": "everything"}]}


@pytest.fixture
def home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "state").mkdir(parents=True)
    (home / "owner.ref").write_text(OWNER)
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    monkeypatch.setenv("FLYWHEEL_RUN_ROOT", str(tmp_path / "run"))
    with using(StreamTestProvider()):
        yield home


def _forge_retention(home, doc: dict) -> None:
    merged = policy.validate(doc)
    path = policy._adopted_path(home, OWNER)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes({"schema": policy.SCHEMA, **merged}))
    runs = schedule._state_path(home, OWNER)
    runs.write_bytes(canonical_bytes({"planned_for": policy.digest(merged)}))


def _live(home) -> set[str]:
    return {i["ref"] for i in policy.items(home, OWNER) if i["store"] == "S1"}


def test_a_forged_retention_policy_deletes_nothing_and_is_reported(home):
    refs = {plant_trace(home, operation=f"op_{i:032x}") for i in range(3)}
    _forge_retention(home, DELETE_ALL)
    assert not schedule.should_schedule(home, OWNER)
    result = schedule.run(home, OWNER, now=time.time() + DAY, sink=MemorySink())
    assert result["state"] == "KEEP"
    assert _live(home) == refs
    shown = policy.effective(home, OWNER)
    assert shown["tampered"] is True and shown["action"] == "keep"


def test_a_forged_run_state_does_not_skip_the_plan_only_first_run(home):
    """runs.json names the policy as already planned; the ledger holds no
    plan-only run for it, so the first run still only plans."""
    refs = {plant_trace(home, operation=f"op_{i:032x}") for i in range(3)}
    policy.write_file(home, DELETE_ALL)
    digest = policy.digest(policy.read_file(home)[0])
    policy.adopt(home, OWNER, confirm(home / "state", OWNER, "retention_adopt", digest, "a"),
                 sink=MemorySink())
    schedule._state_path(home, OWNER).write_bytes(canonical_bytes({"planned_for": digest}))
    first = schedule.run(home, OWNER, now=time.time() + DAY, sink=MemorySink())
    assert first["state"] == "PLANNED" and _live(home) == refs
    second = schedule.run(home, OWNER, now=time.time() + DAY, sink=MemorySink())
    assert second["state"] == "APPLIED" and _live(home) == set()


def test_a_first_run_with_nothing_due_does_not_count_as_the_preview(home):
    """The first run that finds something still only plans, even after an
    earlier run found nothing."""
    policy.write_file(home, {"action": "rules", "rules": [
        {"store": "S1", "max_age_days": 30, "reason_code": "older_than_30_days"}],
        "max_share_per_run": 1})
    digest = policy.digest(policy.read_file(home)[0])
    policy.adopt(home, OWNER, confirm(home / "state", OWNER, "retention_adopt", digest, "a"),
                 sink=MemorySink())
    ref = plant_trace(home)
    assert schedule.run(home, OWNER, sink=MemorySink())["state"] == "NOTHING_DUE"
    later = schedule.run(home, OWNER, now=time.time() + 40 * DAY, sink=MemorySink())
    assert later["state"] == "PLANNED" and ref in _live(home)


def test_forged_capture_settings_keep_everything_off(home):
    path = capture._adopted_path(home, OWNER)
    path.parent.mkdir(parents=True, exist_ok=True)
    forged = {**capture.DEFAULTS, "content": "on", "freeze_urls": "on"}
    path.write_bytes(canonical_bytes({"schema": capture.SCHEMA, **forged}))
    shown = capture.effective(home, OWNER)
    assert shown["content"] == "off" and shown["freeze_urls"] == "off"
    assert shown["tampered"] is True and shown["pending_change"] is True


def test_settings_adopted_with_presence_are_in_effect(home):
    capture.write_file(home, {"content": "on"})
    digest = capture.digest(capture.read_file(home)[0])
    capture.adopt(home, OWNER, confirm(home / "state", OWNER, "capture_settings", digest, "a"),
                  sink=MemorySink())
    shown = capture.effective(home, OWNER)
    assert shown["content"] == "on" and shown["tampered"] is False
    stored = json.loads(capture._adopted_path(home, OWNER).read_bytes())
    assert stored["content"] == "on"
