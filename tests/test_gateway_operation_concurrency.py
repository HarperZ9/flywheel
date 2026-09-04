"""Route tests about contention: one journey lock, more than one request.

These are the tests the route's lock timeout exists for, so they are the ones
that set it explicitly rather than inheriting a production default a loaded
runner can outlast.
"""
from dataclasses import replace
import json
import threading
import time

from harness.gateway_operation_process import WorkerOutcome
from harness.gateway_operation_route import route_gateway_operation

from gateway_route_fixtures import OWNER, Factory, Process, _setup

def test_exact_start_replay_precedes_authorization_and_second_worker(tmp_path):
    calls = []
    service, raw = _setup(tmp_path, authorize_calls=calls)
    process = Process(WorkerOutcome("completed", {"ok": True}))
    factory = Factory(process)
    first = route_gateway_operation(
        "POST", "/api/agent", owner_ref=OWNER, raw=raw,
        content_type="application/json", service=service,
        process_factory=factory)
    b"".join(first.stream or ())
    replay = route_gateway_operation(
        "POST", "/api/agent", owner_ref=OWNER, raw=raw,
        content_type="application/json", service=service,
        process_factory=factory)
    b"".join(replay.stream or ())
    changed = json.loads(raw)
    changed["expected_event_head"] = "e" * 64
    mismatch = route_gateway_operation(
        "POST", "/api/agent", owner_ref=OWNER,
        raw=json.dumps(changed).encode(), content_type="application/json",
        service=service, process_factory=factory)
    assert calls == ["agent.run"] and factory.calls == 1
    assert mismatch.status == 409
    assert mismatch.body["error"]["code"] == "IDEMPOTENCY_MISMATCH"
def test_guarded_route_thread_start_failure_commits_one_terminal(monkeypatch, tmp_path):
    authorizations = []
    service, raw = _setup(tmp_path, authorize_calls=authorizations, lock_timeout_s=.05)
    service.credential_resolver = lambda authorized, _root: replace(
        authorized, credential_bindings={"TOKEN": "synthetic-route-launch"})
    factory = Factory(Process(WorkerOutcome("completed", {"ignored": True})))
    monkeypatch.setattr(threading.Thread, "start", lambda _thread: (_ for _ in ()).throw(OSError("thread unavailable")))
    request = lambda: route_gateway_operation(
        "POST", "/api/agent", owner_ref=OWNER, raw=raw, content_type="application/json", service=service,
        process_factory=factory)
    first = request()
    assert first.status == 200
    first_wire = b"".join(first.stream or ())
    ref = next(iter(service.operation_refs(OWNER)))
    terminal, result = service.snapshot(OWNER, ref), service.result(OWNER, ref)
    replay_wire = b"".join(request().stream or ())
    history = service._history(service._journey(OWNER), ref)
    terminals = [event for event in history if event["event_type"] in {
        "operation_completed", "operation_failed", "operation_cancelled"}]
    assert terminal.state == "failed"
    assert result["result"] == {"reason": "OWNERSHIP_UNAVAILABLE"}
    assert first_wire == replay_wire and b"STORE_BUSY" not in first_wire
    assert authorizations == ["agent.run"] and factory.calls == 0
    assert service._handles == service._secrets == {}
    assert len(terminals) == 1 and terminals[0]["event_type"] == "operation_failed"
def test_concurrent_exact_start_replays_before_second_authorization(tmp_path):
    calls = []
    # The second request waits on the journey lock while the first one sits in
    # a deliberately slow authorizer. On a loaded runner that wait can outlast
    # the production default, and a request that gives up reports STORE_BUSY,
    # which reads as a broken store rather than a contended one. The wait is
    # what this test is about, so it gets a timeout no scheduler will beat.
    service, raw = _setup(tmp_path, authorize_calls=calls, lock_timeout_s=30.0)
    authorize = service.authorizer
    def slow_authorize(*args, **kwargs):
        time.sleep(.1)
        return authorize(*args, **kwargs)
    service.authorizer = slow_authorize
    factory = Factory(Process(WorkerOutcome("completed", {"ok": True})))
    gate, statuses = threading.Barrier(3), []
    def request():
        gate.wait()
        response = route_gateway_operation(
            "POST", "/api/agent", owner_ref=OWNER, raw=raw,
            content_type="application/json", service=service,
            process_factory=factory)
        b"".join(response.stream or ())
        statuses.append(response.status)
    threads = [threading.Thread(target=request) for _ in range(2)]
    for thread in threads: thread.start()
    gate.wait()
    for thread in threads:
        # Generous, because a slow machine is not a failure. join() returns
        # whether or not the thread finished, so the liveness assertion is what
        # turns a genuine deadlock into a named failure instead of the
        # confusing [200] != [200, 200] a silent timeout produces.
        thread.join(60)
        assert not thread.is_alive(), "a request thread never finished"
    assert statuses == [200, 200]
    assert calls == ["agent.run"] and factory.calls == 1
