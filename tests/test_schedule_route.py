"""The unattended-run surface, through the handler and over the wire.

`test_scheduler.py` covers the arithmetic and the chain. What is left is
the part a caller touches: defining a schedule, asking what it owes, and
ticking it. The last two tests go through `gateway._Handler` rather than
calling the handler directly, because the parity row for this capability
cites the route, and a handler that works while nothing dispatches to it
is the exact failure that row's witness rule was written to catch.

Split from test_scheduler.py when that file reached the length gate.
"""
import io
import json
import sys

from harness.accountable_hooks import register_hook, save_registry
from harness.schedule_route import handle_schedule_get, handle_schedule_post
from harness.scheduler import chain_intact, fires_path

ANCHOR = "2026-09-06T00:00:00Z"


def _clock(stamp):
    return lambda: stamp


def _define(run_root, *, schedule_id, catch_up="latest", every=3600):
    return handle_schedule_post(
        "/api/schedule/define",
        {"schedule_id": schedule_id, "event": "bench.completed",
         "every_seconds": every, "starts_at": ANCHOR, "catch_up": catch_up},
        run_root=run_root, clock=_clock(ANCHOR))


def test_the_route_defines_stores_and_reports_what_is_owed(tmp_path):
    body, code = _define(tmp_path, schedule_id="sched_r")
    assert code == 200 and body["schedule"]["schedule_sha256"]
    roster, code = handle_schedule_get(
        "/api/schedule", run_root=tmp_path,
        clock=_clock("2026-09-06T04:00:00Z"))
    assert code == 200 and roster["count"] == 1
    assert roster["any_chain_broken"] is False
    state = roster["schedules"][0]
    assert state["pending"]["due"] == 5
    assert state["plan"]["policy"] == "latest"
    assert len(state["plan"]["skipped"]) == 4


def test_an_incomplete_definition_is_refused(tmp_path):
    body, code = handle_schedule_post(
        "/api/schedule/define", {"schedule_id": "sched_r"},
        run_root=tmp_path, clock=_clock(ANCHOR))
    assert code == 422 and body["error"]["code"] == "INVALID_REQUEST"


def test_an_unknown_schedule_route_is_a_404(tmp_path):
    _, code = handle_schedule_get("/api/schedule/all", run_root=tmp_path,
                                  clock=_clock(ANCHOR))
    assert code == 404
    _, code = handle_schedule_post("/api/schedule/purge", {},
                                   run_root=tmp_path, clock=_clock(ANCHOR))
    assert code == 404


def test_a_tick_fires_the_hook_the_event_is_bound_to(tmp_path):
    """The timing and the work are separate registrations, and both show.

    The schedule knows an event. The hook registry knows what that event
    runs. A tick joins them and seals the join, so the receipt names the
    argv that ran without the schedule ever having held it.
    """
    save_registry([register_hook(event="bench.completed",
                                 argv=[sys.executable, "-c", "print('ran')"],
                                 blocking=False, hook_id="hook_s",
                                 created_at=ANCHOR)],
                  registry_path=tmp_path / "hooks" / "registry.json")
    _define(tmp_path, schedule_id="sched_t")
    body, code = handle_schedule_post(
        "/api/schedule/tick", {}, run_root=tmp_path,
        clock=_clock("2026-09-06T02:30:00Z"))
    assert code == 200 and body["fired"] == 1 and body["skipped"] == 2
    run = body["results"][0]["runs"][0]
    assert run["hooks_run"] == 1
    assert run["event_blocked"] is False
    assert run["lateness_seconds"] == 1800
    records = json.loads(
        fires_path(tmp_path, "sched_t").read_text(encoding="utf-8"))
    assert chain_intact(records) is True
    assert records[0]["hook_receipts"][0]["exit_code"] == 0


def test_an_event_with_no_hook_registered_fires_and_says_so(tmp_path):
    """An event nobody listens for is the ordinary state, not an error.

    The occurrence still happened and still gets a record. What the
    record carries is an empty receipt list, which is a different claim
    from a run that was never due.
    """
    _define(tmp_path, schedule_id="sched_q")
    body, _ = handle_schedule_post("/api/schedule/tick", {},
                                   run_root=tmp_path,
                                   clock=_clock("2026-09-06T02:30:00Z"))
    assert body["fired"] == 1
    assert body["results"][0]["runs"][0]["hooks_run"] == 0


def test_a_second_tick_inside_the_same_interval_fires_nothing(tmp_path):
    """Idempotence is the property an unattended caller depends on.

    Whatever wakes the process may wake it twice. The cursor is the
    instant the last record stands for, so a second tick before the next
    occurrence finds nothing owed and writes nothing.
    """
    _define(tmp_path, schedule_id="sched_i")
    first, _ = handle_schedule_post("/api/schedule/tick", {},
                                    run_root=tmp_path,
                                    clock=_clock("2026-09-06T02:30:00Z"))
    second, _ = handle_schedule_post("/api/schedule/tick", {},
                                     run_root=tmp_path,
                                     clock=_clock("2026-09-06T02:59:00Z"))
    assert first["fired"] == 1
    assert second["fired"] == 0 and second["evaluated"] == 1


def test_a_tick_onto_a_broken_chain_refuses_rather_than_burying_it(tmp_path):
    from harness.scheduler import fire_record, load_schedules, schedules_path
    _define(tmp_path, schedule_id="sched_b")
    schedule = load_schedules(schedules_path(tmp_path))[0]
    honest = fire_record(schedule, scheduled_for=ANCHOR,
                         fired_at="2026-09-06T00:00:05Z", prev_sha256="",
                         hook_receipts=[], skipped=[])
    path = fires_path(tmp_path, "sched_b")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([dict(honest, lateness_seconds=99)]),
                    encoding="utf-8")
    body, code = handle_schedule_post("/api/schedule/tick", {},
                                      run_root=tmp_path,
                                      clock=_clock("2026-09-06T04:00:00Z"))
    assert code == 200 and body["fired"] == 0
    assert "broken" in body["results"][0]["refused"]
    roster, _ = handle_schedule_get("/api/schedule", run_root=tmp_path,
                                    clock=_clock("2026-09-06T04:00:00Z"))
    assert roster["any_chain_broken"] is True


class _FakeHeaders:
    def __init__(self, n):
        self._n = n

    def get(self, k, d=None):
        return self._n if k == "Content-Length" else d


def _handler(path, run_root, monkeypatch, stamp):
    import harness.gateway as gateway
    monkeypatch.setattr(gateway._Handler, "run_root", str(run_root))
    monkeypatch.setattr(gateway._Handler, "clock", lambda *a: stamp)
    h = gateway._Handler.__new__(gateway._Handler)
    h.path = path
    return h


def _wire_get(path, run_root, monkeypatch, stamp):
    h = _handler(path, run_root, monkeypatch, stamp)
    h.headers = _FakeHeaders("0")
    sent = {}
    h._json = lambda b, code=200: sent.update(body=b, code=code)
    h._get()
    return sent


def _wire_post(path, payload, run_root, monkeypatch, stamp):
    raw = json.dumps(payload).encode()
    h = _handler(path, run_root, monkeypatch, stamp)
    h.headers = _FakeHeaders(str(len(raw)))
    h.rfile = io.BytesIO(raw)
    sent = {}
    h._json = lambda b, code=200: sent.update(body=b, code=code)
    h._post()
    return sent


def test_the_gateway_dispatches_both_schedule_paths(tmp_path, monkeypatch):
    """The route witness on the parity row, exercised.

    `_route_witnessed` reads the gateway source for a dispatch against
    the path. That check can be satisfied by a line that never runs, so
    the row is only as good as a test that goes through the handler.
    """
    sent = _wire_post("/api/schedule/define",
                      {"schedule_id": "sched_w", "event": "bench.completed",
                       "every_seconds": 3600, "starts_at": ANCHOR,
                       "catch_up": "drop"},
                      tmp_path, monkeypatch, ANCHOR)
    assert sent["code"] == 200
    assert sent["body"]["schema"] == "flywheel.schedule-ack/v1"
    listed = _wire_get("/api/schedule", tmp_path, monkeypatch,
                       "2026-09-06T03:00:00Z")
    assert listed["code"] == 200
    assert listed["body"]["schema"] == "flywheel.schedule-roster/v1"
    assert listed["body"]["schedules"][0]["pending"]["due"] == 4
    ticked = _wire_post("/api/schedule/tick", {}, tmp_path, monkeypatch,
                        "2026-09-06T03:00:00Z")
    # catch_up "drop" runs none of the backlog and names all of it.
    assert ticked["body"]["fired"] == 0
    assert ticked["body"]["skipped"] == 4
