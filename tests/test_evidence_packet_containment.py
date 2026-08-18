"""Terminal fail-closed boundary for arbitrary Python journey checks."""
from dataclasses import replace
import socket
import sys
from pathlib import Path
from threading import Event, Thread
import pytest
import harness.oracle as oracle_module
from harness.evidence_journey import append_event, new_journey, run_journey_check
from harness.evidence_packet import pack_journey_packet, verify_journey_packet
from harness.execution_input_protection import ExecutionInputProtectionUnavailable
from harness.journey_checks import JourneyCheckService
from harness.journey_service import JourneyService
from harness.journey_store import JourneyStore, JourneyStoreError, MutationCommand
from harness.operation_grants import GrantStore
from harness.pytest_prepared import verify_prepared
from test_journey_checks import (
    JOURNEY_TWO, NOW as CHECK_NOW, OPERATION, OWNER, Runner,
    _command as check_command, _events as check_events, _service as check_service,
)

REASON = "EXECUTION_CONTAINMENT_UNAVAILABLE"
LIMIT = ("NOT_PROVES_CANDIDATE_BEHAVIOR: candidate and tests were not executed "
         "because deny-read and deny-egress containment is unavailable.")
REQUIREMENT = {
    "schema": "flywheel.python-execution-containment-requirement/v1",
    "status": "UNAVAILABLE",
    "child_process_spawned": False,
    "candidate_spawned": False,
    "candidate_executed": False,
    "tests_executed": False,
    "required_runtime": {
        "identity": "Windows AppContainer/lowbox identity",
        "filesystem": "allowlisted staging ACL",
        "network": "no network capabilities",
    },
}
def _journey():
    journey = new_journey(journey_id="containment-v1", goal="Check Python",
        intake={"summary": "untrusted Python"}, created_at="2026-08-13T12:00:00Z")
    return append_event(journey, {"stage": "decomposed",
        "occurred_at": "2026-08-13T12:01:00Z", "claims": [{
            "claim_id": "claim-root", "statement": "The candidate meets its tests",
            "depends_on": [], "verdict": "UNDECIDED",
            "reason": "registered checker has not run", "receipt_refs": []}]})
def _listener():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0)); listener.listen(2); listener.settimeout(0.2)
    return listener, listener.getsockname()[1]
def _received(listener):
    try:
        connection, _ = listener.accept()
    except TimeoutError:
        return None
    with connection:
        connection.settimeout(0.2)
        return connection.recv(1024)
def _fixture(tmp_path, attempt):
    root = tmp_path / "artifacts"; root.mkdir()
    candidate, test = root / "candidate.py", root / "test_candidate.py"
    canary = tmp_path / "outside-canary.txt"; canary.write_text("outside-secret", encoding="utf-8")
    read_listener, read_port = _listener(); process_listener, process_port = _listener()
    child = ("import socket; s=socket.create_connection(('127.0.0.1',"
             f"{process_port}),timeout=2); s.sendall(b'process-spawned'); s.close()")
    prefix = ("from pathlib import Path\nimport socket, subprocess, sys\n"
        f"data=Path({str(canary)!r}).read_bytes()\n"
        f"s=socket.create_connection(('127.0.0.1',{read_port}),timeout=2); "
        "s.sendall(data); s.close()\n"
        f"subprocess.run([sys.executable,'-c',{child!r}],check=True,timeout=2)\n")
    implementations = {
        "benign": "def add(a,b): return a+b\n",
        "failing": "def add(a,b): return a-b\n",
        "collection-error": "def add(a,b): return a+b\n",
        "oversized-output": "print('x'*3000000)\ndef add(a,b): return a+b\n",
    }
    candidate.write_text(prefix + implementations[attempt], encoding="utf-8")
    test_source = ("import deliberately_missing_dependency\n" if attempt == "collection-error"
                   else "from candidate import add\ndef test_add(): assert add(2,3)==5\n")
    test.write_text(test_source, encoding="utf-8")
    context = {"task_id": "containment-v1", "prompt": "Check candidate",
        "oracle_cmd": f'"{sys.executable}" -m pytest test_candidate.py',
        "candidate_ref": "candidate.py",
        "raw_artifact_refs": ["candidate.py", "test_candidate.py"],
        "timeout_seconds": 15}
    return root, candidate, context, read_listener, process_listener
@pytest.mark.parametrize("attempt", [
    "benign", "failing", "collection-error", "oversized-output"])
def test_arbitrary_python_attempts_stop_before_any_child_execution(tmp_path, attempt):
    root, candidate, context, read_listener, process_listener = _fixture(tmp_path, attempt)
    try:
        result = run_journey_check(_journey(), "claim-root", "code", candidate, context)
        leaked, spawned = _received(read_listener), _received(process_listener)
    finally:
        read_listener.close(); process_listener.close()
    assert leaked is None, leaked
    assert spawned is None, spawned
    assert (result["verdict"], result["unverifiable_reason"]) == ("UNVERIFIABLE", REASON)
    assert result["oracle_calls_consumed"] == 0
    assert (result["claim_id"], result["claim_verdict_before"]) == (
        "claim-root", "UNDECIDED")
    assert result["execution_containment"] == REQUIREMENT
    assert result["does_not_prove"] == [LIMIT]
    assert "receipt_ref" not in result and not (root / "receipts").exists()
def test_candidate_junit_parser_and_oracle_dispatch_are_unreachable(tmp_path, monkeypatch):
    root, candidate, context, first, second = _fixture(tmp_path, "benign")
    monkeypatch.setattr(oracle_module, "_pytest_canonical", lambda *_:
        (_ for _ in ()).throw(AssertionError("candidate JUnit parser reached")))
    monkeypatch.setattr(oracle_module.PytestOracle, "verify_prepared", lambda *_:
        (_ for _ in ()).throw(AssertionError("pytest oracle dispatch reached")))
    try:
        result = run_journey_check(_journey(), "claim-root", "code", candidate, context)
    finally:
        first.close(); second.close()
    assert result["unverifiable_reason"] == REASON
    assert "receipt_ref" not in result and not (root / "receipts").exists()
def test_python_refusal_does_not_even_resolve_or_open_candidate(tmp_path):
    """Candidate path admission before refusal would already grant a host read."""
    class UnreadablePath(type(Path())):
        def resolve(self, *args, **kwargs):
            raise AssertionError("candidate resolution reached")

        def open(self, *args, **kwargs):
            raise AssertionError("candidate open reached")

    candidate = UnreadablePath(tmp_path / "never-read.py")
    context = {
        "task_id": "containment-v1", "prompt": "Check candidate",
        "oracle_cmd": f'"{sys.executable}" -m pytest test_candidate.py',
        "candidate_ref": "never-read.py", "raw_artifact_refs": ["never-read.py"],
        "timeout_seconds": 15,
    }
    result = run_journey_check(_journey(), "claim-root", "code", candidate, context)
    assert result["unverifiable_reason"] == REASON
    assert result["oracle_calls_consumed"] == 0 and "receipt_ref" not in result
def test_retired_prepared_pytest_entry_refuses_before_using_inputs():
    entries = [lambda: verify_prepared(None, [], None, []),
               lambda: oracle_module.PytestOracle().verify_prepared([], None, [])]
    for entry in entries:
        with pytest.raises(ExecutionInputProtectionUnavailable, match=REASON):
            entry()
def test_an_unadmitted_python_run_cannot_be_packed_as_fail_or_pass(tmp_path):
    root, candidate, context, first, second = _fixture(tmp_path, "failing")
    try:
        result = run_journey_check(_journey(), "claim-root", "code", candidate, context)
    finally:
        first.close(); second.close()
    assert result["unverifiable_reason"] == REASON and "receipt_ref" not in result
    journey = append_event(_journey(), {"stage": "preflight",
        "occurred_at": "2026-08-13T12:02:00Z", "claims": [{
            "claim_id": "claim-root", "statement": "The candidate meets its tests",
            "depends_on": [], "verdict": "UNVERIFIABLE", "reason": REASON,
            "receipt_refs": [], "raw_artifact_refs": []}]})
    packet = tmp_path / "packet"
    with pytest.raises(ValueError, match="requires receipts and raw evidence"):
        pack_journey_packet(packet, journey=journey, artifact_root=root)
    assert not packet.exists()
    assert verify_journey_packet(packet)["verdict"] == "UNVERIFIABLE"
def test_check_grant_binds_server_owned_artifact_root(tmp_path):
    """Changing the granted root reference must block rather than redirect."""
    service, genesis = check_service(tmp_path)
    command = check_command(tmp_path, service, genesis.event_head_sha256)
    redirected = tmp_path / "redirected"; redirected.mkdir()
    (redirected / command.candidate_ref).write_text("redirect", encoding="utf-8")
    blocked = service.request(replace(command, artifact_root_ref="redirected"))
    before = check_events(tmp_path)
    assert before[-1]["event_type"] == "check_blocked"
    assert before[-1]["payload"]["reason"] == "PERMISSION_DENIED"
    assert blocked.event_sha256 == before[-1]["event_sha256"]
    with pytest.raises(JourneyStoreError, match="IDEMPOTENCY_MISMATCH"):
        service.request(command)
    assert check_events(tmp_path) == before
@pytest.mark.parametrize("consumed", (False, True))
def test_request_only_retry_closes_without_duplicate_or_grant_reburn(
        tmp_path, monkeypatch, consumed):
    """A crash-only request is safely closed without re-burning its exact grant."""
    service, genesis = check_service(tmp_path)
    command = check_command(tmp_path, service, genesis.event_head_sha256)
    def crash(point):
        if point == "after_check_requested": raise RuntimeError("crash")
    service.journey._fault_injector = crash
    with pytest.raises(JourneyStoreError, match="STORE_COMMIT_FAILED"):
        service.request(command)
    assert [event["event_type"] for event in check_events(tmp_path)[1:]] == [
        "check_requested"]
    if consumed:
        service.journey.grants.consume(command.grant_ref, command.grant_request,
                                       now=CHECK_NOW)
    second = JourneyCheckService(journey=JourneyService(
        owner_ref=OWNER, store=JourneyStore(tmp_path),
        grants=GrantStore(tmp_path, clock=lambda: CHECK_NOW), clock=lambda: CHECK_NOW))
    monkeypatch.setattr(second.journey.grants, "consume", lambda *args, **kwargs:
                        pytest.fail("retry attempted another grant burn"))
    replay = second.request(command)
    events = check_events(tmp_path)
    assert [event["event_type"] for event in events[1:]] == [
        "check_requested", "check_blocked"]
    assert events[-1]["payload"]["reason"] == "CHECK_INTERRUPTED"
    assert second.request(command).event_sha256 == replay.event_sha256
    conflict = check_command(tmp_path, second, replay.event_head_sha256,
                             request_id="check-distinct")
    with pytest.raises(JourneyStoreError, match="IDEMPOTENCY_MISMATCH"):
        second.request(conflict)
    assert check_events(tmp_path) == events
def test_operation_ref_rejects_cross_journey_cross_service_reuse(tmp_path):
    """Owner-wide reuse must not reveal or append another Journey's operation."""
    first, genesis = check_service(tmp_path)
    first.request(check_command(tmp_path, first, genesis.event_head_sha256))
    store = JourneyStore(tmp_path)
    other = store.create(MutationCommand(
        owner_ref=OWNER, journey_ref=JOURNEY_TWO, expected_event_head=None,
        client_request_id="genesis-two", operation="intake",
        body={"legacy_label": None, "goal": "Other", "intake": {},
              "occurred_at": CHECK_NOW},
    ))
    second = JourneyCheckService(journey=JourneyService(
        owner_ref=OWNER, store=store,
        grants=GrantStore(tmp_path, clock=lambda: CHECK_NOW), clock=lambda: CHECK_NOW,
    ))
    reused = check_command(
        tmp_path, second, other.event_head_sha256,
        request_id="check-other", journey_ref=JOURNEY_TWO)
    with pytest.raises(JourneyStoreError, match="IDEMPOTENCY_MISMATCH"):
        second.request(reused)
    assert [event["event_type"] for event in check_events(
        tmp_path, JOURNEY_TWO)] == ["intake"]
def test_different_operation_race_has_no_bare_request_or_second_grant_burn(
        tmp_path, monkeypatch):
    """Journey admission serializes before another request or grant burn."""
    first, genesis = check_service(tmp_path)
    second = JourneyCheckService(journey=JourneyService(
        owner_ref=OWNER, store=JourneyStore(tmp_path),
        grants=GrantStore(tmp_path, clock=lambda: CHECK_NOW), clock=lambda: CHECK_NOW))
    leader_command = check_command(tmp_path, first, genesis.event_head_sha256)
    entered, release, second_done = Event(), Event(), Event()
    original = first._consume_or_block
    def pause(checked):
        entered.set(); assert release.wait(2)
        return original(checked)
    monkeypatch.setattr(first, "_consume_or_block", pause)
    results, errors = [], []
    def call(service, command, done=None):
        try: results.append(service.request(command))
        except Exception as exc: errors.append(exc)
        finally:
            if done is not None: done.set()
    leader = Thread(target=call, args=(first, leader_command)); leader.start()
    assert entered.wait(2)
    follower_command = check_command(
        tmp_path, second, check_events(tmp_path)[-1]["event_sha256"],
        operation_ref=OPERATION.replace("a", "d"), request_id="check-race")
    follower = Thread(
        target=call, args=(second, follower_command, second_done)); follower.start()
    early = second_done.wait(0.2); release.set(); leader.join(2); follower.join(2)
    assert not early and len(results) == 1 and len(errors) == 1
    assert str(errors[0]) == "HEAD_CONFLICT"
    assert [event["event_type"] for event in check_events(tmp_path)[1:]] == [
        "check_requested", "check_started"]
    second.journey.grants.consume(
        follower_command.grant_ref, follower_command.grant_request, now=CHECK_NOW)
def test_cross_service_run_executes_runner_and_side_effect_once(tmp_path):
    """A follower replays the terminal without invoking its runner."""
    first, genesis = check_service(tmp_path)
    command = check_command(tmp_path, first, genesis.event_head_sha256)
    first.request(command)
    second = JourneyCheckService(journey=JourneyService(
        owner_ref=OWNER, store=JourneyStore(tmp_path),
        grants=GrantStore(tmp_path, clock=lambda: CHECK_NOW), clock=lambda: CHECK_NOW))
    second.request(replace(
        command, grant_ref="gnt_ffffffffffffffffffffffffffffffff"))
    entered, release, follower_done = Event(), Event(), Event()
    side_effect = tmp_path / "runner-side-effect.txt"
    class EffectRunner(Runner):
        def __init__(self, pause=False): super().__init__(); self.pause = pause
        def __call__(self, *args, **kwargs):
            self.calls += 1
            if self.pause: entered.set(); assert release.wait(2)
            with side_effect.open("a", encoding="utf-8") as stream:
                stream.write("effect\n")
            return self.result
    leader_runner, follower_runner = EffectRunner(True), EffectRunner()
    results, errors = [], []
    def execute(service, runner, done=None):
        try: results.append(service.run(OPERATION, runner))
        except Exception as exc: errors.append(exc)
        finally:
            if done is not None: done.set()
    leader = Thread(target=execute, args=(first, leader_runner)); leader.start()
    assert entered.wait(2)
    follower = Thread(
        target=execute, args=(second, follower_runner, follower_done)); follower.start()
    early = follower_done.wait(0.2); release.set(); leader.join(2); follower.join(2)
    assert not early and not errors and len(results) == 2
    assert leader_runner.calls == 1 and follower_runner.calls == 0
    assert side_effect.read_text(encoding="utf-8") == "effect\n"
    assert results[0].event_sha256 == results[1].event_sha256
