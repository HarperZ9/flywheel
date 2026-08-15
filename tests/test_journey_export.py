import json
from dataclasses import replace

import pytest

from harness.evidence_json import canonical_sha256
from harness.journey_export import JourneyExportService
from harness.journey_packet_v2 import PACKET_PROFILE, verify_journey_custody_packet
from harness.journey_service import JourneyService
from harness.journey_store import JourneyStore, JourneyStoreError, MutationCommand
from harness.operation_grants import GrantRequest, GrantStore

NOW = "2026-08-14T12:00:00Z"
OWNER = "owner_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
JOURNEY = "jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _service(root):
    return JourneyService(
        owner_ref=OWNER, store=JourneyStore(root),
        grants=GrantStore(root, clock=lambda: NOW), clock=lambda: NOW)


def _append(root, head, request_id, operation, payload=None):
    return JourneyStore(root).append(MutationCommand(
        owner_ref=OWNER, journey_ref=JOURNEY, expected_event_head=head,
        client_request_id=request_id, operation=operation,
        body={"occurred_at": NOW, "payload": payload or {}},
    ))


def _concluded(root):
    ack = JourneyStore(root).create(MutationCommand(
        owner_ref=OWNER, journey_ref=JOURNEY, expected_event_head=None,
        client_request_id="create", operation="intake",
        body={"legacy_label": None, "goal": "Export custody", "intake": {},
              "occurred_at": NOW},
    ))
    for stage in ("decomposed", "preflight", "running"):
        ack = _append(root, ack.event_head_sha256, stage, stage)
    return _append(root, ack.event_head_sha256, "concluded", "concluded",
                   {"conclusion": {"summary": "bounded"}})


def _grant(root, head, packet_ref="packets/journey"):
    service = _service(root); projection = service.resume(JOURNEY)
    body = {"client_request_id": "export-1", "packet_ref": packet_ref,
            "artifact_root_ref": "artifacts",
            "source_projection_sha256": canonical_sha256(projection),
            "packet_profile": PACKET_PROFILE}
    operation = {"owner_ref": OWNER, "journey_ref": JOURNEY,
        "expected_event_head": head, "operation": "export", "body": body}
    request = GrantRequest(
        OWNER, JOURNEY, head, canonical_sha256(operation), "journey.export",
        canonical_sha256(body), ("journey:export",), ("artifacts", packet_ref),
        "2026-08-14T12:02:00Z", "export-1")
    grant = GrantStore(root, clock=lambda: NOW).issue(request, approved=True)
    return request, grant["grant_ref"], body


def _export(root, head, packet_ref="packets/journey", *, grant_ref=None,
            request=None, body=None, fault_injector=None):
    request = request or _grant(root, head, packet_ref)[0]
    grant_ref = grant_ref or _grant(root, head, packet_ref)[1]
    body = body or _grant(root, head, packet_ref)[2]
    return JourneyExportService(
        journey=_service(root), artifact_root_ref="artifacts",
        fault_injector=fault_injector).export(
            journey_ref=JOURNEY, expected_event_head=head,
            client_request_id=body["client_request_id"], packet_ref=packet_ref,
            grant_ref=grant_ref, grant_request=request, body=body)


def _events(root):
    directory = root / "journeys" / "v2" / "owners" / OWNER / JOURNEY / "events"
    return [json.loads(path.read_bytes()) for path in sorted(directory.glob("*.json"))]


def test_export_publishes_h0_packet_then_appends_h1_event(tmp_path):
    """Putting H1 inside the packet would make the exported event circular."""
    (tmp_path / "artifacts").mkdir()
    h0 = _concluded(tmp_path).event_head_sha256
    request, grant_ref, body = _grant(tmp_path, h0)
    result = _export(tmp_path, h0, grant_ref=grant_ref, request=request, body=body)
    events = _events(tmp_path)
    packet = tmp_path / "artifacts" / "packets" / "journey"
    anchored = verify_journey_custody_packet(
        packet, expected_manifest_sha256=result["packet_digest"])
    assert result["source_event_head_sha256"] == h0
    assert result["final_event_head_sha256"] == events[-1]["event_sha256"]
    assert events[-1]["event_type"] == "exported"
    assert events[-1]["prior_event_sha256"] == h0
    assert anchored["verdict"] == result["structural_verdict"] == "MATCH"
    assert json.loads((packet / "criterion.json").read_text())[
        "source_event_head_sha256"] == h0


def test_export_replay_after_restart_returns_same_result_without_new_event(tmp_path):
    """Same id and digest after restart must not burn another grant or append again."""
    (tmp_path / "artifacts").mkdir()
    h0 = _concluded(tmp_path).event_head_sha256
    request, grant_ref, body = _grant(tmp_path, h0)
    first = _export(tmp_path, h0, grant_ref=grant_ref, request=request, body=body)
    before = _events(tmp_path)
    replay = _export(tmp_path, h0, grant_ref="gnt_ffffffffffffffffffffffffffffffff",
                     request=request, body=body)
    assert replay["idempotent_replay"] is True
    assert replay["final_event_head_sha256"] == first["final_event_head_sha256"]
    assert replay["packet_digest"] == first["packet_digest"]
    assert _events(tmp_path) == before


def test_changed_digest_reuse_and_distinct_stale_head_fail_closed(tmp_path):
    """Changed retry bytes or a different request at stale H0 must not export twice."""
    (tmp_path / "artifacts").mkdir()
    h0 = _concluded(tmp_path).event_head_sha256
    request, grant_ref, body = _grant(tmp_path, h0)
    _export(tmp_path, h0, grant_ref=grant_ref, request=request, body=body)
    changed = {**body, "packet_ref": "packets/other"}
    with pytest.raises(JourneyStoreError) as mismatch:
        _export(tmp_path, h0, "packets/other", grant_ref=grant_ref,
                request=request, body=changed)
    assert mismatch.value.code == "IDEMPOTENCY_MISMATCH"
    other_request, other_grant, other_body = _grant(tmp_path, h0, "packets/stale")
    other_body = {**other_body, "client_request_id": "export-2"}
    other_request = replace(other_request, nonce="export-2")
    with pytest.raises(JourneyStoreError) as conflict:
        _export(tmp_path, h0, "packets/stale", grant_ref=other_grant,
                request=other_request, body=other_body)
    assert conflict.value.code == "HEAD_CONFLICT"


def test_existing_target_refuses_before_grant_burn(tmp_path):
    """An existing caller target, even empty, must not consume one-use approval."""
    artifact_root = tmp_path / "artifacts"; (artifact_root / "packets" / "journey").mkdir(parents=True)
    h0 = _concluded(tmp_path).event_head_sha256
    request, grant_ref, body = _grant(tmp_path, h0)
    with pytest.raises(JourneyStoreError) as failure:
        _export(tmp_path, h0, grant_ref=grant_ref, request=request, body=body)
    assert failure.value.code == "STORE_COMMIT_FAILED"
    assert GrantStore(tmp_path, clock=lambda: NOW).consume(
        grant_ref, request, now=NOW)["consumed"] is True


@pytest.mark.parametrize("point", ("after_grant_burn", "after_staging_flush",
                                   "after_publish", "after_event_commit",
                                   "before_response"))
def test_crash_recovery_converges_or_replays_without_acknowledged_loss(tmp_path, point):
    """A crash after burn must recover to one packet and one exported event."""
    (tmp_path / "artifacts").mkdir()
    h0 = _concluded(tmp_path).event_head_sha256
    request, grant_ref, body = _grant(tmp_path, h0)
    with pytest.raises(JourneyStoreError):
        _export(tmp_path, h0, grant_ref=grant_ref, request=request, body=body,
                fault_injector=lambda seen: (_ for _ in ()).throw(OSError("crash"))
                if seen == point else None)
    replay = _export(tmp_path, h0, grant_ref=grant_ref, request=request, body=body)
    assert replay["final_event_head_sha256"] == _events(tmp_path)[-1]["event_sha256"]
    assert [event["event_type"] for event in _events(tmp_path)].count("exported") == 1
