"""A schedule stops itself when its fires keep failing, exit 0 or not.

The failure this guards against: a job on a clock runs a command that exits
0 while printing that the account hit its usage limit. Each fire reads as a
success, so the job runs all night and bills for every attempt. The hook
receipt now names the limit, and the schedule stops after two failed fires
in a row under one definition.
"""
import sys

from harness.accountable_hooks import register_hook, run_hooks, save_registry
from harness.schedule_route import handle_schedule_get, handle_schedule_post
from harness.scheduler import breaker, fires_path, load_fires

ANCHOR = "2026-09-06T00:00:00Z"
LIMIT_TEXT = "Claude AI usage limit reached|1760000000"


def _clock(stamp):
    return lambda: stamp


def _hook(tmp_path, printed, *, blocking=False):
    counter = tmp_path / "runs.txt"
    code = (f"import pathlib; p = pathlib.Path({str(counter)!r}); "
            f"p.write_text((p.read_text() if p.exists() else '') + 'x'); "
            f"print({printed!r})")
    return register_hook(event="bench.completed", argv=[sys.executable, "-c", code],
                         blocking=blocking, hook_id="hook_limit", created_at=ANCHOR)


def _runs(tmp_path):
    counter = tmp_path / "runs.txt"
    return len(counter.read_text()) if counter.exists() else 0


def _define(tmp_path, created_at=ANCHOR):
    return handle_schedule_post(
        "/api/schedule/define",
        {"schedule_id": "sched_limit", "event": "bench.completed",
         "every_seconds": 3600, "starts_at": ANCHOR, "catch_up": "all"},
        run_root=tmp_path, clock=_clock(created_at))


def test_exit_zero_with_a_limit_message_is_a_failed_hook(tmp_path):
    receipts = run_hooks("bench.completed", [_hook(tmp_path, LIMIT_TEXT, blocking=True)],
                         runner=lambda argv: {"exit_code": 0, "output": LIMIT_TEXT},
                         context={})
    assert receipts[0]["exit_code"] == 0
    assert receipts[0]["false_success"] is True
    assert receipts[0]["limit_signal"] == "rate_limit"
    assert receipts[0]["blocked"] is True


def test_ordinary_output_leaves_the_receipt_unchanged(tmp_path):
    receipts = run_hooks("bench.completed", [_hook(tmp_path, "ok")],
                         runner=lambda argv: {"exit_code": 0, "output": "ok"},
                         context={})
    assert "false_success" not in receipts[0] and "limit_signal" not in receipts[0]
    assert receipts[0]["blocked"] is False


def test_a_backlog_stops_after_two_failed_fires_instead_of_replaying(tmp_path):
    save_registry([_hook(tmp_path, LIMIT_TEXT)],
                  registry_path=tmp_path / "hooks" / "registry.json")
    _define(tmp_path)
    body, code = handle_schedule_post("/api/schedule/tick", {}, run_root=tmp_path,
                                      clock=_clock("2026-09-06T04:30:00Z"))
    result = body["results"][0]
    assert code == 200 and result["fired"] == 2 and _runs(tmp_path) == 2
    assert result["breaker"]["tripped"] is True
    assert result["breaker"]["limit_signals"] == ["rate_limit"]
    assert "Redefine the schedule" in result["refused"]
    later, _ = handle_schedule_post("/api/schedule/tick", {}, run_root=tmp_path,
                                    clock=_clock("2026-09-06T06:30:00Z"))
    assert later["fired"] == 0 and _runs(tmp_path) == 2
    roster, _ = handle_schedule_get("/api/schedule", run_root=tmp_path,
                                    clock=_clock("2026-09-06T06:30:00Z"))
    assert roster["schedules"][0]["breaker"]["tripped"] is True


def test_redefining_the_schedule_re_arms_it(tmp_path):
    save_registry([_hook(tmp_path, LIMIT_TEXT)],
                  registry_path=tmp_path / "hooks" / "registry.json")
    _define(tmp_path)
    handle_schedule_post("/api/schedule/tick", {}, run_root=tmp_path,
                         clock=_clock("2026-09-06T01:30:00Z"))
    _define(tmp_path, created_at="2026-09-06T02:00:00Z")
    body, _ = handle_schedule_post("/api/schedule/tick", {}, run_root=tmp_path,
                                   clock=_clock("2026-09-06T03:30:00Z"))
    assert body["results"][0]["fired"] >= 1


def test_a_passing_fire_resets_the_count(tmp_path):
    save_registry([_hook(tmp_path, "ok")],
                  registry_path=tmp_path / "hooks" / "registry.json")
    _define(tmp_path)
    body, _ = handle_schedule_post("/api/schedule/tick", {}, run_root=tmp_path,
                                   clock=_clock("2026-09-06T04:30:00Z"))
    assert body["results"][0]["fired"] == 5 and "refused" not in body["results"][0]
    schedule = body["results"][0]
    records = load_fires(fires_path(tmp_path, schedule["schedule_id"]))
    assert breaker({"schedule_sha256": records[-1]["schedule_sha256"]},
                   records)["consecutive_failed_fires"] == 0
