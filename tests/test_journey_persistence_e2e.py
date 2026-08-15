import json
import shutil

import harness.journey_route as route_module
from harness.gateway_auth import DEFAULT_HOSTS, authenticate_owner
from harness.grant_route import grant_post
from harness.journey_checks import JourneyCheckService
from harness.journey_packet_v2 import verify_journey_custody_packet
from harness.journey_recovery import recover_store
from harness.journey_route import journey_post

NOW = "2026-08-14T12:00:00Z"
FIXTURE = "benchmarks/fixtures/evidence-journey/durable-restart-v2.json"
COMMON_LENS = ("journey_ref", "event_head_sha256", "fact_ids", "claim_ids",
               "checks", "verdicts", "missing_evidence", "stage", "conclusion")

def _owner(state):
    token = "t" * 43
    headers = {"Authorization": f"Bearer {token}", "Host": "localhost:8799",
               "Content-Type": "application/json"}
    owner, reason = authenticate_owner(headers, "POST", token, state / "auth",
                                        allowed_hosts=DEFAULT_HOSTS)
    assert reason == "ok"
    return owner

def _post(action, body, state, evidence, owner):
    return journey_post(f"/api/journeys/{action}", json.dumps(body).encode(),
        owner_ref=owner, state_root=state, evidence_root=evidence,
        clock=lambda: NOW)

def _grant(action, body, state, evidence, owner):
    proposal, status = grant_post(f"/api/grants/prepare/{action}",
        json.dumps(body).encode(), owner_ref=owner, state_root=state,
        evidence_root=evidence, clock=lambda: NOW)
    assert status == 200, proposal
    approved, status = grant_post("/api/grants/approve-once",
        json.dumps({"proposal_ref": proposal["proposal_ref"]}).encode(),
        owner_ref=owner, state_root=state, evidence_root=evidence,
        clock=lambda: NOW)
    assert status == 200, approved
    return approved["grant_ref"], proposal

def _observe(log, *, action, request_id, status, result, effect):
    log.append({"action": action, "client_request_id": request_id,
        "grant_prepare": True, "grant_approve": True,
        "expected_status": status,
        "expected_error": None if status == 200 else result["error"]["code"],
        "expected_effect": effect})

def _mutate(action, body, state, evidence, owner, log=None,
            fixture_action=None, effect=None):
    grant, proposal = _grant(action, body, state, evidence, owner)
    result, status = _post(action, {**body, "grant_ref": grant},
                           state, evidence, owner)
    if log is not None:
        _observe(log, action=fixture_action or action,
            request_id=body["client_request_id"], status=status,
            result=result, effect=effect)
    assert status == 200, result
    return result, proposal

def _created_with_claim(state, evidence, owner, log):
    create = {"goal": "Accept durable restart", "intake_ref": "intake.json",
              "client_request_id": "create-1"}
    ack, _ = _mutate("create", create, state, evidence, owner, log,
                     "create", "intake_event")
    retry_grant, _ = _grant("create", create, state, evidence, owner)
    retry, status = _post("create", {**create, "grant_ref": retry_grant},
                           state, evidence, owner)
    changed = {**create, "goal": "Changed retry"}
    changed_grant, _ = _grant("create", changed, state, evidence, owner)
    mismatch, mismatch_status = _post("create", {**changed,
        "grant_ref": changed_grant}, state, evidence, owner)
    assert status == 200 and retry["idempotent_replay"] is True
    assert mismatch_status == 409 and mismatch["error"]["code"] == "IDEMPOTENCY_MISMATCH"
    claim = {"journey_ref": ack["journey_ref"],
        "expected_event_head": ack["event_head_sha256"],
        "client_request_id": "claim-1", "command": {"type": "record_claim",
        "claim": {"claim_id": "claim-1", "statement": "Data is deterministic",
        "depends_on": [], "does_not_prove": "claim correctness"}}}
    return _mutate("append", claim, state, evidence, owner, log,
                   "record_claim", "record_claim_event")[0]

def _conclude(ack, state, evidence, owner, log):
    effects = ("stage_decomposed", "stage_preflight",
               "stage_running", "stage_concluded")
    for index in range(4):
        body = {"journey_ref": ack["journey_ref"],
            "expected_event_head": ack["event_head_sha256"],
            "client_request_id": f"stage-{index}",
            "command": {"type": "advance_stage"}}
        ack, _ = _mutate("append", body, state, evidence, owner, log,
                         "advance_stage", effects[index])
    return ack

def _blocked_python(ack, state, evidence, owner, log):
    context = {"candidate_ref": "candidate.py", "task_id": "blocked-python"}
    (evidence / "python-context.json").write_text(json.dumps(context), encoding="utf-8")
    body = {"journey_ref": ack["journey_ref"],
        "expected_event_head": ack["event_head_sha256"],
        "client_request_id": "check-python", "claim_id": "claim-1",
        "oracle_id": "code", "candidate_ref": "candidate.py",
        "context_ref": "python-context.json"}
    result, _ = _mutate("check", body, state, evidence, owner, log,
                        "blocked_python_check", "check_blocked")
    assert result["state"] == "blocked" and not (evidence / "candidate.py").exists()
    return result

class _DataRunner:
    calls = 0
    def __call__(self, _journey, _claim, _oracle, candidate, _context,
                 *, artifact_root=None):
        self.calls += 1
        assert candidate.name == "candidate.json" and artifact_root == candidate.parent
        return {"verdict": "UNDECIDED", "basis": "deterministic fixture"}

def _data_check(ack, state, evidence, owner, monkeypatch, log):
    candidate = evidence / "candidate.json"
    candidate.write_text('{"sample":1}', encoding="utf-8")
    context = {"candidate_ref": "candidate.json", "task_id": "data-check"}
    (evidence / "data-context.json").write_text(json.dumps(context), encoding="utf-8")
    body = {"journey_ref": ack["journey_ref"],
        "expected_event_head": ack["event_head_sha256"],
        "client_request_id": "check-data", "claim_id": "claim-1",
        "oracle_id": "ml", "candidate_ref": "candidate.json",
        "context_ref": "data-context.json"}
    captured = []
    original = JourneyCheckService
    def capture(**kwargs):
        captured.append(original(**kwargs)); return captured[-1]
    with monkeypatch.context() as patch:
        patch.setattr(route_module, "JourneyCheckService", capture)
        started, _ = _mutate("check", body, state, evidence, owner)
    checks, runner = captured[0], _DataRunner()
    terminal = checks.run(started["operation_ref"], runner)
    _observe(log, action="deterministic_data_check",
        request_id=body["client_request_id"], status=200, result=started,
        effect="check_completed")
    assert started["state"] == "running"
    assert runner.calls == 1 and checks.state(started["operation_ref"]) == "completed"
    return {"journey_ref": terminal.journey_ref,
        "event_head_sha256": terminal.event_head_sha256,
        "projection_sha256": terminal.projection_sha256,
        "operation_ref": started["operation_ref"]}

def _events(state, owner, journey_ref):
    root = state / "journeys" / "v2" / "owners" / owner / journey_ref / "events"
    return [json.loads(path.read_bytes()) for path in sorted(root.glob("*.json"))]

def _terminal_counts(events, exported, evidence):
    kinds = [event["event_type"] for event in events]
    terminals = sum(kinds.count(kind) for kind in (
        "check_blocked", "check_completed", "check_failed", "check_cancelled"))
    request_hashes = [event["request_sha256"] for event in events]
    packet_count = sum(path.name == "manifest.json"
                       for path in (evidence / "packets").rglob("manifest.json"))
    return {"acknowledged_loss": int(
                exported["final_event_head_sha256"] != events[-1]["event_sha256"]),
        "duplicate_logical_event": len(request_hashes) - len(set(request_hashes)),
        "silent_overwrite": int(packet_count != 1),
        "unclosed_check_request": kinds.count("check_requested") - terminals,
        "check_blocked": kinds.count("check_blocked"),
        "check_completed": kinds.count("check_completed"),
        "check_failed": kinds.count("check_failed"),
        "check_cancelled": kinds.count("check_cancelled")}

def test_phase_1_acceptance_flow_and_fixture_are_public_safe(tmp_path, monkeypatch):
    """Authenticated custody survives conflict, restart, export, and clean recheck."""
    state, evidence = tmp_path / "state", tmp_path / "state" / "artifacts"
    evidence.mkdir(parents=True); owner = _owner(state)
    fixture = json.loads(open(FIXTURE, encoding="utf-8").read())
    observed = []
    (evidence / "intake.json").write_text(json.dumps(fixture["intake"]), encoding="utf-8")
    assert set(fixture) == {"schema", "goal", "intake", "commands",
                            "expected_events", "expected_terminal_counts"}
    concluded = _conclude(_created_with_claim(state, evidence, owner, observed),
                          state, evidence, owner, observed)
    blocked = _blocked_python(concluded, state, evidence, owner, observed)
    checked = _data_check(blocked, state, evidence, owner, monkeypatch, observed)
    stale = {"journey_ref": checked["journey_ref"], "expected_event_head": "0" * 64,
        "client_request_id": "stale", "command": {"type": "advance_stage"}}
    grant, _ = _grant("append", stale, state, evidence, owner)
    conflict, status = _post("append", {**stale, "grant_ref": grant}, state, evidence, owner)
    cancel = {"journey_ref": checked["journey_ref"],
        "expected_event_head": checked["event_head_sha256"],
        "client_request_id": "cancel-1", "operation_ref": checked["operation_ref"]}
    cancel_grant, _ = _grant("cancel", cancel, state, evidence, owner)
    cancelled, cancel_status = _post("cancel", {**cancel, "grant_ref": cancel_grant},
                                     state, evidence, owner)
    _observe(observed, action="cancel_terminal_operation",
        request_id=cancel["client_request_id"], status=cancel_status,
        result=cancelled, effect="no_new_event")
    assert status == 409 and conflict["error"]["code"] == "HEAD_CONFLICT"
    assert cancel_status == 409 and cancelled["error"]["code"] == "CANCEL_UNAVAILABLE"
    views = [_post("resume", {"journey_ref": checked["journey_ref"], "lens": lens},
        state, evidence, owner)[0] for lens in ("Rescue", "Diagnose", "Verify")]
    assert all(tuple(view[key] for key in COMMON_LENS) ==
               tuple(views[0][key] for key in COMMON_LENS) for view in views)
    listed, list_status = _post("list", {}, state, evidence, owner)
    assert list_status == 200 and listed["journeys"][0]["event_head_sha256"] == checked["event_head_sha256"]
    export = {"journey_ref": checked["journey_ref"],
        "expected_event_head": checked["event_head_sha256"],
        "client_request_id": "export-1", "packet_ref": "packets/journey"}
    exported, _ = _mutate("export", export, state, evidence, owner, observed,
                          "export", "exported_event_and_packet")
    clean = tmp_path / "clean" / "packet"; clean.parent.mkdir()
    shutil.copytree(evidence / "packets" / "journey", clean)
    recheck = verify_journey_custody_packet(
        clean, expected_manifest_sha256=exported["packet_digest"])
    recovery = recover_store(state, now=NOW)
    assert recheck["verdict"] == "MATCH" and exported["source_event_head_sha256"] == checked["event_head_sha256"]
    events = _events(state, owner, checked["journey_ref"])
    assert observed == fixture["commands"]
    assert [event["event_type"] for event in events] == fixture["expected_events"]
    assert _terminal_counts(events, exported, evidence) == fixture[
        "expected_terminal_counts"]
    assert {key: recovery[key] for key in ("completed", "quarantined", "starts_closed")} == {"completed": 0, "quarantined": 0, "starts_closed": False}
    public = json.dumps([fixture, listed, views, exported, recheck])
    assert str(tmp_path) not in public and "credential" not in public.lower()
