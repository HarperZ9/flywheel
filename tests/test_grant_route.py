from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from harness.grant_route import grant_post, resolve_approved_grant
from harness.journey_lock import JourneyLockBusy
from harness.journey_route import journey_post

NOW = "2026-08-14T12:00:00Z"
OWNER = "owner_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
OTHER = "owner_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _post(path, body, *, owner=OWNER, state, evidence, clock=lambda: NOW):
    return grant_post(f"/api/grants/{path}", json.dumps(body).encode(),
                      owner_ref=owner, state_root=state,
                      evidence_root=evidence, clock=clock)


def _prepare_create(state, evidence):
    (evidence / "intake.json").write_text('{"summary":"bounded"}', encoding="utf-8")
    return _post("prepare/create", {
        "goal": "Preserve evidence", "intake_ref": "intake.json",
        "client_request_id": "create-1",
    }, state=state, evidence=evidence)


def test_prepare_is_not_authority_and_approval_survives_process_state(tmp_path):
    """Treating a proposal as a grant or relying on memory would widen or lose custody."""
    state, evidence = tmp_path / "state", tmp_path / "evidence"
    state.mkdir(); evidence.mkdir()
    proposal, status = _prepare_create(state, evidence)
    assert status == 200
    assert set(proposal) == {"schema", "proposal_ref", "planned_grant_ref",
                             "action", "operation_sha256", "expires_at"}
    assert proposal["planned_grant_ref"][4:] == proposal["proposal_ref"][4:]
    with pytest.raises(Exception, match="PERMISSION_REQUIRED"):
        resolve_approved_grant(proposal["planned_grant_ref"], owner_ref=OWNER,
                               state_root=state, clock=lambda: NOW)

    approved, status = _post("approve-once", {
        "proposal_ref": proposal["proposal_ref"],
    }, state=state, evidence=evidence)
    assert status == 200 and approved["grant_ref"] == proposal["planned_grant_ref"]
    resolved = resolve_approved_grant(
        approved["grant_ref"], owner_ref=OWNER, state_root=state, clock=lambda: NOW)
    assert resolved["action"] == "create"
    assert resolved["grant_request"].owner_ref == OWNER


def test_proposal_parent_creation_and_replacements_sync_the_full_chain(
        tmp_path, monkeypatch):
    """Acknowledgment must follow durable parent entries through state_root."""
    from harness import grant_route
    state, evidence = tmp_path / "state", tmp_path / "evidence"
    evidence.mkdir(); synced = []
    monkeypatch.setattr(grant_route, "fsync_directory",
                        lambda path: synced.append(Path(path)))
    proposal, status = _prepare_create(state, evidence)
    root, owner = state / "grant-proposals", state / "grant-proposals" / OWNER
    assert status == 200 and synced == [tmp_path, state, root, owner, root, state]
    synced.clear()
    approved, approved_status = _post(
        "approve-once", {"proposal_ref": proposal["proposal_ref"]},
        state=state, evidence=evidence)
    assert approved_status == 200 and approved["grant_ref"] == proposal["planned_grant_ref"]
    assert synced == [owner, root, state]


@pytest.mark.parametrize("phase", ("prepare", "approve"))
def test_proposal_and_exact_grant_lock_contention_is_retryable(
        phase, tmp_path, monkeypatch):
    """Private lock contention must return one fixed retryable response."""
    from harness import grant_route
    state, evidence = tmp_path / "state", tmp_path / "evidence"
    state.mkdir(); evidence.mkdir()
    proposal = _prepare_create(state, evidence)[0] if phase == "approve" else None
    monkeypatch.setattr(grant_route.ExclusiveJourneyLock, "acquire",
                        lambda *_a, **_k: (_ for _ in ()).throw(JourneyLockBusy()))
    if phase == "prepare":
        result, status = _prepare_create(state, evidence)
        assert not list((state / "grant-proposals").rglob("*.json"))
    else:
        result, status = _post("approve-once", {
            "proposal_ref": proposal["proposal_ref"]}, state=state, evidence=evidence)
        assert not (state / "grants").exists()
    assert status == 503 and result["error"] == {
        "code": "STORE_BUSY", "message": "grant proposal custody is busy"}
    assert str(tmp_path) not in json.dumps(result)


def test_approval_is_idempotent_cross_owner_hidden_and_grant_ledger_digest_only(tmp_path):
    """A retry must keep one grant while another owner learns nothing about it."""
    state, evidence = tmp_path / "state", tmp_path / "evidence"
    state.mkdir(); evidence.mkdir()
    proposal, _ = _prepare_create(state, evidence)
    body = {"proposal_ref": proposal["proposal_ref"]}
    first, first_status = _post("approve-once", body, state=state, evidence=evidence)
    second, second_status = _post("approve-once", body, state=state, evidence=evidence)
    denied, denied_status = _post(
        "approve-once", body, owner=OTHER, state=state, evidence=evidence)
    assert (first_status, second_status) == (200, 200) and first == second
    assert denied_status == 403 and denied["error"]["code"] == "PERMISSION_REQUIRED"
    grant_bytes = b"".join(path.read_bytes() for path in (state / "grants").rglob("*.json"))
    assert b"Preserve evidence" not in grant_bytes and b"intake.json" not in grant_bytes
    assert b"request_sha256" in grant_bytes


def test_approval_retry_recovers_after_grant_issue_before_proposal_mark(tmp_path, monkeypatch):
    """A crash-shaped proposal write failure must not mint a second grant."""
    from harness import grant_route
    state, evidence = tmp_path / "state", tmp_path / "evidence"
    state.mkdir(); evidence.mkdir()
    proposal, _ = _prepare_create(state, evidence)
    body = {"proposal_ref": proposal["proposal_ref"]}
    real_replace = grant_route._replace
    monkeypatch.setattr(grant_route, "_replace",
                        lambda *_a, **_k: (_ for _ in ()).throw(OSError("crash")))
    failed, failed_status = _post(
        "approve-once", body, state=state, evidence=evidence)
    monkeypatch.setattr(grant_route, "_replace", real_replace)
    retried, retried_status = _post(
        "approve-once", body, state=state, evidence=evidence)
    records = list((state / "grants").rglob("*.json"))
    assert failed_status == 500 and failed["error"]["code"] == "STORE_COMMIT_FAILED"
    assert retried_status == 200 and retried["grant_ref"] == proposal["planned_grant_ref"]
    assert len(records) == 1


def test_proposal_digest_mismatch_fails_closed(tmp_path):
    """Private-record tampering must not be promoted into grant authority."""
    state, evidence = tmp_path / "state", tmp_path / "evidence"
    state.mkdir(); evidence.mkdir()
    proposal, _ = _prepare_create(state, evidence)
    record_path = next((state / "grant-proposals" / OWNER).glob("*.json"))
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["operation_body"]["goal"] = "changed"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    result, status = _post("approve-once", {
        "proposal_ref": proposal["proposal_ref"],
    }, state=state, evidence=evidence)
    assert status == 403 and result["error"]["code"] == "PERMISSION_DENIED"
    assert not (state / "grants").exists()


def test_expired_proposal_and_unknown_fields_are_fixed_non_echo_errors(tmp_path):
    """Late or widened approval must fail without returning caller-controlled data."""
    state, evidence = tmp_path / "state", tmp_path / "evidence"
    state.mkdir(); evidence.mkdir()
    proposal, _ = _prepare_create(state, evidence)
    late = (datetime.fromisoformat(NOW.replace("Z", "+00:00"))
            + timedelta(minutes=3)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    expired, status = _post("approve-once", {"proposal_ref": proposal["proposal_ref"]},
                            state=state, evidence=evidence, clock=lambda: late)
    widened, widened_status = _post("prepare/create", {
        "goal": "C:/private/secret", "intake_ref": "intake.json",
        "client_request_id": "create-2", "occurred_at": "caller-owned",
    }, state=state, evidence=evidence)
    assert status == 403 and expired["error"]["code"] == "APPROVAL_EXPIRED"
    assert widened_status == 400 and widened["error"]["code"] == "UNKNOWN_FIELD"
    assert "private" not in json.dumps(widened)


def test_check_prepare_binds_context_without_reading_candidate(tmp_path, monkeypatch):
    """Post-approval context byte rewriting must deny before grant or Journey use."""
    state, evidence = tmp_path / "state", tmp_path / "state" / "artifacts"
    evidence.mkdir(parents=True)
    create, _ = _prepare_create(state, evidence)
    approved, _ = _post("approve-once", {"proposal_ref": create["proposal_ref"]},
                         state=state, evidence=evidence)
    created, status = journey_post("/api/journeys/create", json.dumps({
        "goal": "Preserve evidence", "intake_ref": "intake.json",
        "client_request_id": "create-1", "grant_ref": approved["grant_ref"],
    }).encode(), owner_ref=OWNER, state_root=state,
        evidence_root=evidence, clock=lambda: NOW)
    assert status == 200
    original = b'{"candidate_ref":"candidate.py","task_id":"bounded"}'
    context_path = evidence / "context.json"; context_path.write_bytes(original)
    real_read = Path.read_bytes
    def guarded(path):
        if path.name == "candidate.py": pytest.fail("candidate was read")
        return real_read(path)
    monkeypatch.setattr(Path, "read_bytes", guarded)
    request = {
        "journey_ref": created["journey_ref"],
        "expected_event_head": created["event_head_sha256"], "client_request_id": "check-1",
        "claim_id": "claim-1", "oracle_id": "code",
        "candidate_ref": "candidate.py", "context_ref": "context.json",
    }
    proposal, status = _post("prepare/check", request, state=state, evidence=evidence)
    approved, _ = _post("approve-once", {"proposal_ref": proposal["proposal_ref"]},
                         state=state, evidence=evidence)
    context_path.write_bytes(b'{ "task_id": "bounded", "candidate_ref": "candidate.py" }')
    denied, denied_status = journey_post("/api/journeys/check", json.dumps({
        **request, "grant_ref": approved["grant_ref"]}).encode(), owner_ref=OWNER,
        state_root=state, evidence_root=evidence, clock=lambda: NOW)
    context_path.write_bytes(original)
    retried, retry_status = journey_post("/api/journeys/check", json.dumps({
        **request, "grant_ref": approved["grant_ref"]}).encode(), owner_ref=OWNER,
        state_root=state, evidence_root=evidence, clock=lambda: NOW)
    assert status == 200 and proposal["operation_ref"].startswith("op_")
    assert denied_status == 403 and denied["error"]["code"] == "PERMISSION_DENIED"
    assert retry_status == 200 and retried["state"] == "blocked"
    assert not (evidence / "candidate.py").exists()


def test_check_prepare_rejects_unrepresentable_root_before_context_or_candidate_read(
        tmp_path, monkeypatch):
    """An external evidence root cannot become a service-owned artifact selector."""
    state, evidence = tmp_path / "state", tmp_path / "outside"
    state.mkdir(); evidence.mkdir()
    def no_read(_path): pytest.fail("artifact bytes were read")
    monkeypatch.setattr(Path, "read_bytes", no_read)
    result, status = _post("prepare/check", {
        "journey_ref": "jrn_0123456789abcdef0123456789abcdef",
        "expected_event_head": "a" * 64, "client_request_id": "check-1",
        "claim_id": "claim-1", "oracle_id": "code", "candidate_ref": "candidate.py",
        "context_ref": "context.json",
    }, state=state, evidence=evidence)
    assert status == 409 and result["error"]["code"] == "INVALID_TRANSITION"


def test_export_prepare_binds_concluded_h0_projection_profile_and_target_refs(tmp_path):
    """Export grants must bind H0, P0, profile, artifact root, and packet ref."""
    from harness.evidence_json import canonical_sha256
    from harness.journey_store import JourneyStore, MutationCommand
    state, evidence = tmp_path / "state", tmp_path / "state" / "artifacts"
    evidence.mkdir(parents=True)
    store = JourneyStore(state)
    ack = store.create(MutationCommand(OWNER,
        "jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", None, "create-export",
        "intake", {"legacy_label": None, "goal": "Preserve evidence",
                   "intake": {}, "occurred_at": NOW}))
    for stage in ("decomposed", "preflight", "running", "concluded"):
        payload = {"conclusion": {"summary": "bounded"}} if stage == "concluded" else {}
        ack = store.append(MutationCommand(OWNER, ack.journey_ref,
            ack.event_head_sha256, f"stage-{stage}", stage,
            {"occurred_at": NOW, "payload": payload}))
    body = {"journey_ref": ack.journey_ref,
            "expected_event_head": ack.event_head_sha256,
            "client_request_id": "export-1", "packet_ref": "packets/out"}
    proposal, status = _post("prepare/export", body, state=state, evidence=evidence)
    approved, _ = _post("approve-once", {"proposal_ref": proposal["proposal_ref"]},
                         state=state, evidence=evidence)
    resolved = resolve_approved_grant(
        approved["grant_ref"], owner_ref=OWNER,
        state_root=state, clock=lambda: NOW)
    assert status == 200 and resolved["grant_request"].scopes == ("journey:export",)
    assert resolved["grant_request"].data_refs == ("artifacts", "packets/out")
    assert resolved["operation_body"]["packet_profile"] == (
        "flywheel.evidence-journey-custody/v2")
    assert resolved["operation_body"]["source_projection_sha256"] == canonical_sha256(
        store.load(OWNER, ack.journey_ref))
