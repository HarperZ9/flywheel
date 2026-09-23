"""A schedule stops on real limit errors, says what matched, and re-arms cleanly.

A monitoring or sync job can print healthy status text that names a limit
("0 requests were rate limited"). That is a mention, not a failure, and it
must not stop a working schedule. When a schedule does stop, the owner sees
the matched words and re-arms it with one call that keeps its definition.
"""
import json
import sys

import pytest

from harness.accountable_hooks import load_registry, register_hook, run_hooks, save_registry
from harness.schedule_route import handle_schedule_get, handle_schedule_post
from harness.scheduler import chain_intact, fires_path, load_fires
from tests.test_schedule_breaker import ANCHOR, LIMIT_TEXT, _clock, _define, _hook, _runs


def _tick(tmp_path, at):
    body, _ = handle_schedule_post("/api/schedule/tick", {}, run_root=tmp_path, clock=_clock(at))
    return body["results"][0]


def _roster(tmp_path, at):
    body, _ = handle_schedule_get("/api/schedule", run_root=tmp_path, clock=_clock(at))
    return body


@pytest.mark.parametrize("printed", [
    "checked 1,204 requests in the last hour; 0 were rate limited",
    "synced 120 rows; 0 requests were rate limited",
    "GET /v1/items -> status 429, retried after 2s; done: 50 items",
    "urllib3 Retrying after 429 Too Many Requests\nbackup complete",
    "checked api.example.com: status: 503 (maintenance window), alert sent",
    "skipping optional upload: not logged in to the mirror",
])
def test_healthy_status_text_that_names_a_limit_does_not_stop_a_schedule(tmp_path, printed):
    save_registry([_hook(tmp_path, printed, blocking=True)],
                  registry_path=tmp_path / "hooks" / "registry.json")
    _define(tmp_path)
    result = _tick(tmp_path, "2026-09-06T01:30:00Z")
    assert result["fired"] == 2 and "refused" not in result
    state = _roster(tmp_path, "2026-09-06T01:30:00Z")["schedules"][0]
    assert state["breaker"]["tripped"] is False
    receipt = load_fires(fires_path(tmp_path, "sched_limit"))[-1]["hook_receipts"][0]
    assert "false_success" not in receipt and receipt["blocked"] is False
    assert receipt["limit_match"]


def test_the_receipt_and_the_refusal_carry_the_matched_words(tmp_path):
    save_registry([_hook(tmp_path, LIMIT_TEXT)],
                  registry_path=tmp_path / "hooks" / "registry.json")
    _define(tmp_path)
    result = _tick(tmp_path, "2026-09-06T04:30:00Z")
    assert result["fired"] == 2
    receipt = load_fires(fires_path(tmp_path, "sched_limit"))[-1]["hook_receipts"][0]
    assert receipt["limit_match"] == "usage limit reached"
    assert result["breaker"]["limit_matches"] == ["usage limit reached"]
    assert '(matched "usage limit reached")' in result["refused"]
    assert "Re-arm the schedule" in result["refused"]


def test_a_hook_registered_without_output_scanning_is_judged_by_exit_code(tmp_path):
    reg = register_hook(event="bench.completed", argv=[sys.executable, "-c", "pass"],
                        blocking=True, hook_id="hook_monitor", created_at=ANCHOR,
                        scan_output=False)
    assert reg["scan_output"] is False
    receipts = run_hooks("bench.completed", [reg], context={},
                         runner=lambda argv: {"exit_code": 0, "output": LIMIT_TEXT})
    assert "false_success" not in receipts[0] and receipts[0]["blocked"] is False
    save_registry([reg], registry_path=tmp_path / "registry.json")
    assert load_registry(tmp_path / "registry.json") == [reg]
    for forged in ({**reg, "scan_output": True}, {**reg, "scan_output": "no"}):
        (tmp_path / "forged.json").write_text(json.dumps([forged]), encoding="utf-8")
        with pytest.raises(ValueError):
            load_registry(tmp_path / "forged.json")
    plain = register_hook(event="bench.completed", argv=[sys.executable, "-c", "pass"],
                          blocking=True, hook_id="hook_plain", created_at=ANCHOR)
    assert "scan_output" not in plain


def test_a_stopped_schedule_holds_what_it_owes_instead_of_planning_it(tmp_path):
    save_registry([_hook(tmp_path, LIMIT_TEXT)],
                  registry_path=tmp_path / "hooks" / "registry.json")
    _define(tmp_path)
    _tick(tmp_path, "2026-09-06T01:30:00Z")
    roster = _roster(tmp_path, "2026-09-06T04:30:00Z")
    state = roster["schedules"][0]
    assert roster["any_breaker_tripped"] is True
    assert state["plan"]["fire"] == []
    assert state["plan"]["held"] == ["2026-09-06T02:00:00Z", "2026-09-06T03:00:00Z",
                                     "2026-09-06T04:00:00Z"]
    # A held schedule reports nothing as due: the owed runs are counted as held.
    assert state["pending"]["due"] == 0 and state["pending"]["held"] == 3


def test_rearm_reseals_the_stored_definition_and_keeps_the_history(tmp_path):
    save_registry([_hook(tmp_path, LIMIT_TEXT)],
                  registry_path=tmp_path / "hooks" / "registry.json")
    defined, _ = _define(tmp_path)
    _tick(tmp_path, "2026-09-06T01:30:00Z")
    assert _tick(tmp_path, "2026-09-06T02:30:00Z")["fired"] == 0
    body, code = handle_schedule_post("/api/schedule/rearm", {"schedule_id": "sched_limit"},
                                      run_root=tmp_path, clock=_clock("2026-09-06T02:40:00Z"))
    assert code == 200 and body["rearmed"] is True
    old, new = defined["schedule"], body["schedule"]
    assert {k: new[k] for k in ("event", "every_seconds", "starts_at", "catch_up")} == \
        {k: old[k] for k in ("event", "every_seconds", "starts_at", "catch_up")}
    assert new["schedule_sha256"] != old["schedule_sha256"]
    assert _roster(tmp_path, "2026-09-06T02:40:00Z")["schedules"][0]["breaker"]["tripped"] is False
    assert _tick(tmp_path, "2026-09-06T02:45:00Z")["fired"] == 1 and _runs(tmp_path) == 3
    assert chain_intact(load_fires(fires_path(tmp_path, "sched_limit")))
    missing, code = handle_schedule_post("/api/schedule/rearm", {"schedule_id": "sched_nope"},
                                         run_root=tmp_path, clock=_clock(ANCHOR))
    assert code == 422
