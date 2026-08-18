from dataclasses import replace
import hashlib
import json
from threading import Event, Thread

import pytest
from harness.evidence_json import canonical_bytes, canonical_sha256
from harness.evidence_journey import append_event, new_journey
from harness.journey_checks import CheckCommand, JourneyCheckService
from harness.journey_service import JourneyService
from harness.journey_store import JourneyStore, JourneyStoreError, MutationCommand
from harness.operation_grants import GrantRequest, GrantStore
NOW = "2026-08-14T12:00:00Z"
OWNER = "owner_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
JOURNEY = "jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
JOURNEY_TWO = "jrn_cccccccccccccccccccccccccccccccc"
OPERATION = "op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
def _legacy_journey():
    journey = new_journey(
        journey_id="durable-check-v1", goal="Check one claim",
        intake={"summary": "controlled fixture"}, created_at=NOW,
    )
    return append_event(journey, {
        "stage": "decomposed", "occurred_at": NOW, "claims": [{
            "claim_id": "claim-root", "statement": "The claim is checked",
            "depends_on": [], "verdict": "UNDECIDED", "reason": "not run",
            "receipt_refs": [],
        }],
    })
def _service(root, *, supported=frozenset(("lean", "measurement"))):
    store = JourneyStore(root)
    genesis = store.create(MutationCommand(
        owner_ref=OWNER, journey_ref=JOURNEY, expected_event_head=None,
        client_request_id="genesis", operation="intake",
        body={"legacy_label": None, "goal": "Persist checks", "intake": {},
              "occurred_at": NOW},
    ))
    journey = JourneyService(
        owner_ref=OWNER, store=store,
        grants=GrantStore(root, clock=lambda: NOW), clock=lambda: NOW,
    )
    return JourneyCheckService(
        journey=journey, supported_oracle_types=supported,
    ), genesis
def _arguments(journey, oracle_id, context, *, operation_ref=OPERATION,
               request_id="check-1", artifact_root_ref="artifacts"):
    return {
        "client_request_id": request_id, "operation_ref": operation_ref,
        "journey_sha256": canonical_sha256(journey), "claim_id": "claim-root",
        "oracle_id": oracle_id, "artifact_root_ref": artifact_root_ref,
        "candidate_ref": context["candidate_ref"],
        "context_sha256": canonical_sha256(context), "context_bytes_sha256": hashlib.sha256(canonical_bytes(context)).hexdigest(),
    }
def _command(root, service, head, *, oracle_id="ml", operation_ref=OPERATION,
             request_id="check-1", grant=True, artifact_root_ref="artifacts",
             journey_ref=JOURNEY):
    legacy = _legacy_journey()
    artifact_root = root / artifact_root_ref
    artifact_root.mkdir(parents=True, exist_ok=True)
    candidate = artifact_root / "candidate.json"
    candidate.write_text('{"candidate":true}', encoding="utf-8")
    context = {
        "task_id": "durable-check-v1", "prompt": "Check candidate",
        "oracle_cmd": "measurement_gate", "candidate_ref": candidate.name,
        "raw_artifact_refs": [candidate.name], "timeout_seconds": 10,
    }
    arguments = _arguments(
        legacy, oracle_id, context, operation_ref=operation_ref,
        request_id=request_id, artifact_root_ref=artifact_root_ref,
    )
    operation = {
        "owner_ref": OWNER, "journey_ref": journey_ref,
        "expected_event_head": head, "operation": "check", "body": arguments,
    }
    request = GrantRequest(
        owner_ref=OWNER, journey_ref=journey_ref, expected_event_head=head,
        operation_sha256=canonical_sha256(operation), tool="journey.check",
        arguments_sha256=canonical_sha256(arguments), scopes=("journey:check",),
        data_refs=(artifact_root_ref, candidate.name),
        expires_at="2026-08-14T12:02:00Z",
        nonce=request_id,
    )
    grant_ref = "gnt_00000000000000000000000000000000"
    if grant:
        grant_ref = service.journey.grants.issue(request, approved=True)["grant_ref"]
    return CheckCommand(
        owner_ref=OWNER, journey_ref=journey_ref, expected_event_head=head,
        client_request_id=request_id, operation_ref=operation_ref,
        grant_ref=grant_ref, grant_request=request, journey=legacy,
        claim_id="claim-root", oracle_id=oracle_id,
        candidate_ref=candidate.name, context=context,
        context_bytes_sha256=arguments["context_bytes_sha256"], artifact_root_ref=artifact_root_ref,
    )
def _events(root, journey_ref=JOURNEY):
    directory = root / "journeys" / "v2" / "owners" / OWNER / journey_ref / "events"
    return [json.loads(path.read_bytes()) for path in sorted(directory.glob("*.json"))]
class Runner:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result or {"verdict": "PASS"}, error, 0
        self.candidate = self.artifact_root = None
    def __call__(self, journey, claim_id, oracle_id, candidate, context,
                 *, artifact_root=None):
        self.calls += 1; self.candidate, self.artifact_root = candidate, artifact_root
        if self.error is not None:
            raise self.error
        return self.result
def test_admitted_check_commits_one_started_and_one_completed_terminal(tmp_path):
    """Skipping or duplicating a lifecycle event would leave an untruthful run."""
    service, genesis = _service(tmp_path)
    command = _command(tmp_path, service, genesis.event_head_sha256)
    runner = Runner({"verdict": "PASS", "receipt_ref": "receipts/check.json"})
    started = service.request(command)
    completed = service.run(OPERATION, runner)
    replay = service.run(OPERATION, Runner({"verdict": "FAIL"}))
    events = _events(tmp_path)
    assert [event["event_type"] for event in events[1:]] == [
        "check_requested", "check_started", "check_completed",
    ]
    assert started.event_sha256 == events[2]["event_sha256"]
    assert completed.event_sha256 == replay.event_sha256 == events[3]["event_sha256"]
    assert runner.calls == 1
    assert (runner.candidate, runner.artifact_root) == (
        tmp_path / "artifacts" / "candidate.json", tmp_path / "artifacts")
def test_check_arguments_bind_server_context_byte_digest(tmp_path):
    """Exact grant arguments must bind bytes, not only parsed context meaning."""
    service, genesis = _service(tmp_path)
    command = _command(tmp_path, service, genesis.event_head_sha256)
    expected = hashlib.sha256(canonical_bytes(command.context)).hexdigest()
    assert getattr(command, "context_bytes_sha256", None) == expected
    assert service._arguments(command)["context_bytes_sha256"] == expected
@pytest.mark.parametrize("case,oracle_id,supported,grant,reason", (
    ("permission", "ml", frozenset(("measurement",)), False, "PERMISSION_REQUIRED"),
    ("oracle", "unregistered", frozenset(("measurement",)), True,
     "ORACLE_UNAVAILABLE"),
    ("capability", "ml", frozenset(), True, "UNSUPPORTED_CAPABILITY"),
))
def test_pre_admission_blocks_are_durable_after_request(
        tmp_path, case, oracle_id, supported, grant, reason):
    """Admitting denied or unsupported work would make a request look executed."""
    service, genesis = _service(tmp_path, supported=supported)
    command = _command(
        tmp_path, service, genesis.event_head_sha256, oracle_id=oracle_id,
        request_id=f"check-{case}", grant=grant,
    )
    blocked = service.request(command)
    events = _events(tmp_path)
    assert [event["event_type"] for event in events[1:]] == [
        "check_requested", "check_blocked",
    ]
    assert blocked.event_sha256 == events[2]["event_sha256"]
    assert events[2]["payload"]["reason"] == reason
def test_python_refusal_precedes_candidate_read_runner_spawn_and_receipt(
        tmp_path, monkeypatch):
    """Reading or spawning before containment refusal would cross admission."""
    service, genesis = _service(tmp_path)
    monkeypatch.setattr(service, "_resolve_artifacts", lambda *_: pytest.fail("resolved"))
    command = _command(
        tmp_path, service, genesis.event_head_sha256, oracle_id="code",
        request_id="python-refusal",
    )
    runner = Runner()

    blocked = service.request(command)
    events = _events(tmp_path)
    assert blocked.event_sha256 == events[-1]["event_sha256"]
    assert [event["event_type"] for event in events[1:]] == [
        "check_requested", "check_blocked",
    ]
    assert events[-1]["payload"]["reason"] == "EXECUTION_CONTAINMENT_UNAVAILABLE"
    assert runner.calls == 0
    assert not (tmp_path / "receipts").exists()
@pytest.mark.parametrize("result,error,terminal", (
    ({"state": "cancelled"}, None, "check_completed"),
    (None, RuntimeError(r"C:\\private\\candidate-output"), "check_failed"),
))
def test_run_commits_one_public_safe_noncompleted_terminal(
        tmp_path, result, error, terminal):
    """Runner output cannot claim cancellation; raw failures stay public-safe."""
    service, genesis = _service(tmp_path)
    operation = OPERATION.replace("a", "b")
    command = _command(
        tmp_path, service, genesis.event_head_sha256,
        operation_ref=operation, request_id=terminal,
    )
    service.request(command)
    ack = service.run(operation, Runner(result=result, error=error))
    events = _events(tmp_path)
    terminals = [event for event in events if event["event_type"].startswith("check_")
                 and event["event_type"] in {
                     "check_completed", "check_failed", "check_cancelled"}]
    assert len(terminals) == 1 and terminals[0]["event_type"] == terminal
    assert ack.event_sha256 == terminals[0]["event_sha256"]
    assert "private" not in json.dumps(terminals[0])
def test_identical_request_replays_before_grant_and_adds_no_events(tmp_path):
    """Burning a second grant or appending twice would make retries unsafe."""
    service, genesis = _service(tmp_path)
    command = _command(tmp_path, service, genesis.event_head_sha256)
    first = service.request(command)
    before = _events(tmp_path)
    retry = replace(command, grant_ref="gnt_ffffffffffffffffffffffffffffffff")
    replay = service.request(retry)
    assert replay.event_sha256 == first.event_sha256
    assert replay.idempotent_replay is True
    assert _events(tmp_path) == before
def test_invalid_journey_selector_is_rejected_before_lock_path_creation(tmp_path):
    """Creating an operation lock before selector admission would permit traversal."""
    service, genesis = _service(tmp_path)
    command = _command(tmp_path, service, genesis.event_head_sha256)
    escaped = tmp_path / "journeys" / "v2" / "owners" / "escape"
    with pytest.raises(ValueError, match="journey_ref"):
        service.request(replace(command, journey_ref=r"..\escape"))
    assert not escaped.exists()


def test_concurrent_identical_request_serializes_full_admission(tmp_path, monkeypatch):
    """Interleaving grant burn and start could persist both blocked and started."""
    first, genesis = _service(tmp_path)
    second = JourneyCheckService(journey=JourneyService(
        owner_ref=OWNER, store=JourneyStore(tmp_path),
        grants=GrantStore(tmp_path, clock=lambda: NOW), clock=lambda: NOW,
    ))
    command = _command(tmp_path, first, genesis.event_head_sha256)
    entered, release, second_done = Event(), Event(), Event()
    original = first._consume_or_block

    def pause(checked):
        entered.set()
        assert release.wait(2)
        return original(checked)

    monkeypatch.setattr(first, "_consume_or_block", pause)
    results, errors = [], []

    def call(service, done=None):
        try:
            results.append(service.request(command))
        except Exception as exc:
            errors.append(exc)
        finally:
            if done is not None:
                done.set()

    leader = Thread(target=call, args=(first,))
    follower = Thread(target=call, args=(second, second_done))
    leader.start()
    assert entered.wait(2)
    follower.start()
    assert not second_done.wait(0.2)
    release.set()
    leader.join(2); follower.join(2)

    assert not errors and len(results) == 2
    assert results[0].event_sha256 == results[1].event_sha256
    assert [event["event_type"] for event in _events(tmp_path)[1:]] == [
        "check_requested", "check_started",
    ]


def test_concurrent_terminal_serializes_replay_before_server_time(tmp_path, monkeypatch):
    """A terminal timestamp race must replay the one committed terminal."""
    first, genesis = _service(tmp_path)
    command = _command(tmp_path, first, genesis.event_head_sha256)
    first.request(command)
    second = JourneyCheckService(journey=JourneyService(
        owner_ref=OWNER, store=JourneyStore(tmp_path),
        grants=GrantStore(tmp_path, clock=lambda: NOW),
        clock=lambda: "2026-08-14T12:00:01Z",
    ))
    second.request(replace(command, grant_ref="gnt_ffffffffffffffffffffffffffffffff"))
    entered, release, second_done = Event(), Event(), Event()
    original = first.journey._lifecycle_replay

    def pause(*args):
        replay = original(*args)
        if args[3] == "check_completed":
            entered.set(); assert release.wait(2)
        return replay

    monkeypatch.setattr(first.journey, "_lifecycle_replay", pause)
    results, errors = [], []

    def finish(service, done=None):
        try:
            results.append(service._commit_terminal(
                OPERATION, "completed", {"verdict": "PASS"})[0])
        except Exception as exc:
            errors.append(exc)
        finally:
            if done is not None: done.set()

    leader = Thread(target=finish, args=(first,)); leader.start()
    assert entered.wait(2)
    follower = Thread(target=finish, args=(second, second_done)); follower.start()
    assert not second_done.wait(0.2)
    release.set(); leader.join(2); follower.join(2)

    assert not errors and len(results) == 2
    assert results[0].event_sha256 == results[1].event_sha256
    assert [event["event_type"] for event in _events(tmp_path)].count(
        "check_completed") == 1
