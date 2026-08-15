import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from harness.evidence_json import canonical_bytes
from harness.grant_route import grant_post
from harness.journey_route import journey_post

NOW = "2026-08-14T12:00:00Z"
LATE = "2026-08-14T12:03:00Z"
OWNER = "owner_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
JOURNEY = "jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _grant(action, body, state, evidence, *, clock=lambda: NOW):
    proposed, status = grant_post(
        f"/api/grants/prepare/{action}", canonical_bytes(body),
        owner_ref=OWNER, state_root=state, evidence_root=evidence, clock=clock)
    assert status == 200, proposed
    approved, status = grant_post(
        "/api/grants/approve-once",
        canonical_bytes({"proposal_ref": proposed["proposal_ref"]}),
        owner_ref=OWNER, state_root=state, evidence_root=evidence, clock=clock)
    assert status == 200, approved
    return approved["grant_ref"], proposed


def _post(action, body, state, evidence, *, clock=lambda: NOW):
    return journey_post(
        f"/api/journeys/{action}", canonical_bytes(body), owner_ref=OWNER,
        state_root=state, evidence_root=evidence, clock=clock)


def _created(state, evidence):
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "intake.json").write_text('{"summary":"bounded"}', encoding="utf-8")
    body = {"goal": "Preserve", "intake_ref": "intake.json",
            "client_request_id": "create-1"}
    grant, _ = _grant("create", body, state, evidence)
    result, status = _post("create", {**body, "grant_ref": grant}, state, evidence)
    assert status == 200, result
    return result


def _concluded(state, evidence):
    ack = _created(state, evidence)
    for index in range(4):
        body = {"journey_ref": ack["journey_ref"],
                "expected_event_head": ack["event_head_sha256"],
                "client_request_id": f"stage-{index}",
                "command": {"type": "advance_stage"}}
        grant, _ = _grant("append", body, state, evidence)
        ack, status = _post("append", {**body, "grant_ref": grant}, state, evidence)
        assert status == 200, ack
    return ack


def test_cli_default_artifacts_are_state_contained_not_process_cwd(tmp_path):
    """Default CLI custody must not read artifacts from the process cwd."""
    repo = Path(__file__).resolve().parents[1]
    cwd = tmp_path / "cwd"; home = tmp_path / "home"
    state_artifacts = home / "state" / "artifacts"
    cwd.mkdir(); state_artifacts.mkdir(parents=True)
    (cwd / "intake.json").write_text('{"summary":"cwd"}', encoding="utf-8")
    (state_artifacts / "intake.json").write_text(
        '{"summary":"state"}', encoding="utf-8")
    env = {**os.environ, "FLYWHEEL_HOME": str(home), "PYTHONPATH": str(repo)}
    run = subprocess.run([sys.executable, "-m", "harness.journey_cli",
        "grant", "prepare", "create", "--goal", "Preserve",
        "--intake-ref", "intake.json", "--client-request-id", "create-1"],
        cwd=cwd, env=env, capture_output=True, text=True, check=False)
    result = json.loads(run.stdout)
    records = list((home / "state" / "grant-proposals").rglob("*.json"))
    assert run.returncode == 0 and len(records) == 1
    assert b'"summary":"state"' in records[0].read_bytes()
    assert b'"summary":"cwd"' not in records[0].read_bytes()


def test_gateway_private_routes_use_state_artifacts_not_served_root(tmp_path, monkeypatch):
    """Default gateway custody must not treat the served repo root as artifacts."""
    from harness import gateway
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path = "/api/grants/prepare/create"
    handler.root = tmp_path / "served"; handler.root.mkdir()
    handler.flywheel_home = tmp_path / "home"; handler.owner_ref = OWNER
    handler.clock = lambda: NOW
    raw = canonical_bytes({"goal": "Preserve", "intake_ref": "intake.json",
                           "client_request_id": "create-1"})
    handler.rfile = __import__("io").BytesIO(raw)
    handler._content_length = lambda: len(raw)
    captured = []
    handler._json = lambda body, code=200: captured.append((body, code))
    (handler.root / "intake.json").write_text('{"summary":"served"}', encoding="utf-8")
    artifacts = handler.flywheel_home / "state" / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "intake.json").write_text('{"summary":"state"}', encoding="utf-8")
    handler._post()
    assert captured[0][1] == 200
    record = next((handler.flywheel_home / "state" / "grant-proposals").rglob("*.json"))
    assert b'"summary":"state"' in record.read_bytes()
    assert b'"summary":"served"' not in record.read_bytes()


def test_route_replays_exact_create_append_check_and_export_after_expiry(tmp_path):
    """An expired grant cannot authorize new work, but stored exact replay survives."""
    state, evidence = tmp_path / "state", tmp_path / "state" / "artifacts"
    evidence.mkdir(parents=True)
    create = _created(state, evidence)
    create_public = {"goal": "Preserve", "intake_ref": "intake.json",
                     "client_request_id": "create-1"}
    replay_grant, _ = _grant("create", create_public, state, evidence)
    create_replay, status = _post(
        "create", {**create_public, "grant_ref": replay_grant},
        state, evidence, clock=lambda: LATE)
    append = {"journey_ref": create["journey_ref"],
        "expected_event_head": create["event_head_sha256"],
        "client_request_id": "append-1", "command": {"type": "advance_stage"}}
    append_grant, _ = _grant("append", append, state, evidence)
    appended, _ = _post("append", {**append, "grant_ref": append_grant}, state, evidence)
    append_replay, append_status = _post(
        "append", {**append, "grant_ref": append_grant},
        state, evidence, clock=lambda: LATE)
    (evidence / "ctx.json").write_text(
        '{"candidate_ref":"candidate.py","task_id":"safe"}', encoding="utf-8")
    check = {"journey_ref": appended["journey_ref"],
        "expected_event_head": appended["event_head_sha256"],
        "client_request_id": "check-1", "claim_id": "claim-1",
        "oracle_id": "code", "candidate_ref": "candidate.py",
        "context_ref": "ctx.json"}
    check_grant, _ = _grant("check", check, state, evidence)
    checked, _ = _post("check", {**check, "grant_ref": check_grant}, state, evidence)
    check_replay, check_status = _post(
        "check", {**check, "grant_ref": check_grant},
        state, evidence, clock=lambda: LATE)
    concluded = _concluded(tmp_path / "other-state", tmp_path / "other-state" / "artifacts")
    export = {"journey_ref": concluded["journey_ref"],
        "expected_event_head": concluded["event_head_sha256"],
        "client_request_id": "export-1", "packet_ref": "packets/out"}
    other_state = tmp_path / "other-state"; other_evidence = other_state / "artifacts"
    export_grant, _ = _grant("export", export, other_state, other_evidence)
    exported, _ = _post("export", {**export, "grant_ref": export_grant},
                        other_state, other_evidence)
    export_replay, export_status = _post(
        "export", {**export, "grant_ref": export_grant},
        other_state, other_evidence, clock=lambda: LATE)
    mismatch, mismatch_status = _post("append", {**append, "client_request_id": "append-2",
        "grant_ref": append_grant}, state, evidence, clock=lambda: LATE)
    expired_state, expired_evidence = tmp_path / "expired-state", tmp_path / "expired-state" / "artifacts"
    expired = _created(expired_state, expired_evidence)
    expired_append = {"journey_ref": expired["journey_ref"],
        "expected_event_head": expired["event_head_sha256"],
        "client_request_id": "append-expired", "command": {"type": "advance_stage"}}
    expired_grant, _ = _grant("append", expired_append, expired_state, expired_evidence)
    new_work, new_status = _post("append", {**expired_append,
        "grant_ref": expired_grant}, expired_state, expired_evidence, clock=lambda: LATE)
    assert status == append_status == check_status == export_status == 200
    assert create_replay["idempotent_replay"] is True
    assert append_replay["event_head_sha256"] == appended["event_head_sha256"]
    assert check_replay["event_head_sha256"] == checked["event_head_sha256"]
    assert export_replay["packet_digest"] == exported["packet_digest"]
    assert mismatch_status == 403 and mismatch["error"]["code"] == "PERMISSION_DENIED"
    assert new_status == 403 and new_work["error"]["code"] == "APPROVAL_EXPIRED"


def test_prepare_rejects_invalid_scalars_without_any_durable_write(tmp_path):
    """Invalid action scalars must fail before proposal, grant, or state custody."""
    state, evidence = tmp_path / "state", tmp_path / "evidence"
    evidence.mkdir()
    cases = [
        ("create", {"goal": "g", "intake_ref": "intake.json",
                    "client_request_id": ""}),
        ("append", {"journey_ref": "not-a-journey",
                    "expected_event_head": "a" * 64,
                    "client_request_id": "r",
                    "command": {"type": "advance_stage"}}),
        ("append", {"journey_ref": JOURNEY, "expected_event_head": "bad",
                    "client_request_id": "r",
                    "command": {"type": "advance_stage"}}),
    ]
    for action, body in cases:
        result, status = grant_post(
            f"/api/grants/prepare/{action}", canonical_bytes(body),
            owner_ref=OWNER, state_root=state, evidence_root=evidence,
            clock=lambda: NOW)
        assert status == 422 and result["error"]["code"] == "INVALID_TRANSITION"
        assert not state.exists()


def test_check_execution_canonicalizes_refs_the_same_way_as_prepare(tmp_path):
    """Prepare and execute must hash the same canonical refs and _source_ref."""
    state, evidence = tmp_path / "state", tmp_path / "state" / "artifacts"
    evidence.mkdir(parents=True)
    ack = _created(state, evidence)
    (evidence / "dir").mkdir()
    (evidence / "dir" / "ctx.json").write_text(
        '{"candidate_ref":"dir/candidate.py","task_id":"safe"}',
        encoding="utf-8")
    body = {"journey_ref": ack["journey_ref"],
        "expected_event_head": ack["event_head_sha256"],
        "client_request_id": "check-1", "claim_id": "claim-1",
        "oracle_id": "code", "candidate_ref": r"dir\candidate.py",
        "context_ref": r"dir\ctx.json"}
    grant, _ = _grant("check", body, state, evidence)
    result, status = _post("check", {**body, "grant_ref": grant}, state, evidence)
    assert status == 200 and result["state"] == "blocked"


def test_store_busy_during_grant_consumption_is_retryable_503(tmp_path, monkeypatch):
    """Grant-consume lock contention must not become PERMISSION_DENIED."""
    from harness import operation_grants
    state, evidence = tmp_path / "state", tmp_path / "state" / "artifacts"
    evidence.mkdir(parents=True)
    (evidence / "intake.json").write_text('{"summary":"bounded"}', encoding="utf-8")
    body = {"goal": "Preserve", "intake_ref": "intake.json",
            "client_request_id": "create-1"}
    grant, _ = _grant("create", body, state, evidence)
    monkeypatch.setattr(operation_grants.ExclusiveJourneyLock, "acquire",
                        lambda *_a, **_k: (_ for _ in ()).throw(
                            operation_grants.JourneyLockBusy()))
    result, status = _post("create", {**body, "grant_ref": grant}, state, evidence)
    assert status == 503 and result["error"]["code"] == "STORE_BUSY"
