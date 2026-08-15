import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import harness.journey_export_tx as export_tx
from harness.evidence_json import canonical_sha256
from harness.grant_route import grant_post, resolve_approved_grant
from harness.journey_export import JourneyExportService
from harness.journey_packet_v2 import PACKET_PROFILE
from harness.journey_recovery import recover_store
from harness.journey_route import journey_post
from harness.journey_service import JourneyService
from harness.journey_store import JourneyStore, JourneyStoreError, MutationCommand
from harness.operation_grants import GrantRequest, GrantStore

NOW = "2026-08-14T12:00:00Z"
OWNER = "owner_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
JOURNEY = "jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _service(root):
    return JourneyService(owner_ref=OWNER, store=JourneyStore(root),
        grants=GrantStore(root, clock=lambda: NOW), clock=lambda: NOW)


def _concluded(root):
    store = JourneyStore(root)
    ack = store.create(MutationCommand(OWNER, JOURNEY, None, "create", "intake",
        {"legacy_label": None, "goal": "Recover export", "intake": {},
         "occurred_at": NOW}))
    for stage in ("decomposed", "preflight", "running", "concluded"):
        payload = {"conclusion": {"summary": "bounded"}} if stage == "concluded" else {}
        ack = store.append(MutationCommand(OWNER, JOURNEY, ack.event_head_sha256,
            stage, stage, {"occurred_at": NOW, "payload": payload}))
    return ack.event_head_sha256


def _authority(root, head, request_id="export-1", packet_ref="packets/journey"):
    body = {"client_request_id": request_id, "packet_ref": packet_ref,
        "artifact_root_ref": "artifacts",
        "source_projection_sha256": canonical_sha256(_service(root).resume(JOURNEY)),
        "packet_profile": PACKET_PROFILE}
    operation = {"owner_ref": OWNER, "journey_ref": JOURNEY,
        "expected_event_head": head, "operation": "export", "body": body}
    request = GrantRequest(OWNER, JOURNEY, head, canonical_sha256(operation),
        "journey.export", canonical_sha256(body), ("journey:export",),
        ("artifacts", packet_ref), "2026-08-14T12:02:00Z", request_id)
    grant = GrantStore(root, clock=lambda: NOW).issue(request, approved=True)
    return request, grant["grant_ref"], body


def _events(root):
    directory = root / "journeys" / "v2" / "owners" / OWNER / JOURNEY / "events"
    return [json.loads(path.read_bytes()) for path in sorted(directory.glob("*.json"))]


def _private_path(kind, state):
    value = {"owner_ref": OWNER, "client_request_sha256": "a" * 64,
             "packet_digest": "sha256:" + "b" * 64}
    if kind == "owner":
        return export_tx.owner_transaction_dir(state, OWNER)
    if kind == "staging":
        return export_tx.staging_path(state, value)
    if kind == "quarantine":
        return export_tx.quarantine_path(state, value)
    return export_tx.target_lock_path(state, "artifacts", "packets/out")


def _crash(root, point):
    head = _concluded(root)
    request, grant_ref, body = _authority(root, head)
    service = JourneyExportService(journey=_service(root),
        artifact_root_ref="artifacts", fault_injector=lambda seen:
        (_ for _ in ()).throw(OSError("crash")) if seen == point else None)
    with pytest.raises(JourneyStoreError):
        service.export(journey_ref=JOURNEY, expected_event_head=head,
            client_request_id="export-1", packet_ref="packets/journey",
            grant_ref=grant_ref, grant_request=request, body=body)
    return head, grant_ref


@pytest.mark.parametrize("point", ("after_grant_burn", "after_staging_flush",
                                    "after_publish", "after_event_commit"))
def test_store_recovery_completes_every_authorized_export_phase(tmp_path, point):
    """Recovery must close every post-burn phase without renewed authority."""
    (tmp_path / "artifacts").mkdir()
    _crash(tmp_path, point)
    report = recover_store(tmp_path, now=NOW)
    projection = _service(tmp_path).resume(JOURNEY)
    assert report["completed"] == 1
    assert projection["stage"] == "exported"
    assert (tmp_path / "artifacts" / "packets" / "journey" / "manifest.json").is_file()


def test_recovery_quarantines_only_owned_target_after_competing_head(tmp_path):
    """A published packet at stale H0 is quarantined without moving a neighbor."""
    artifacts = tmp_path / "artifacts"; artifacts.mkdir()
    head, _ = _crash(tmp_path, "after_publish")
    neighbor = artifacts / "packets" / "neighbor.txt"
    neighbor.write_text("keep", encoding="utf-8")
    JourneyStore(tmp_path).append(MutationCommand(OWNER, JOURNEY, head,
        "competing", "record_next_action", {"occurred_at": NOW,
        "payload": {"next_actions": [{"action_id": "inspect",
            "kind": "inspect", "description": "Inspect competing head",
            "basis_refs": ["fact_public"]}]}}))
    report = recover_store(tmp_path, now=NOW)
    assert report["quarantined"] == 1
    assert not (artifacts / "packets" / "journey").exists()
    assert neighbor.read_text(encoding="utf-8") == "keep"


def test_recovery_finishes_crash_after_quarantine_move(tmp_path):
    """A crash between owned-target move and phase seal must remain recoverable."""
    artifacts = tmp_path / "artifacts"; artifacts.mkdir()
    head = _concluded(tmp_path)
    request, grant_ref, body = _authority(tmp_path, head)
    with pytest.raises(JourneyStoreError):
        JourneyExportService(journey=_service(tmp_path),
            artifact_root_ref="artifacts", fault_injector=lambda point:
            (_ for _ in ()).throw(OSError("crash"))
            if point == "after_publish" else None).export(
                journey_ref=JOURNEY, expected_event_head=head,
                client_request_id="export-1", packet_ref="packets/journey",
                grant_ref=grant_ref, grant_request=request, body=body)
    JourneyStore(tmp_path).append(MutationCommand(OWNER, JOURNEY, head,
        "competing-quarantine", "record_next_action", {"occurred_at": NOW,
        "payload": {"next_actions": [{"action_id": "inspect",
            "kind": "inspect", "description": "Inspect competing head",
            "basis_refs": ["fact_public"]}]}}))
    with pytest.raises(JourneyStoreError) as failure:
        JourneyExportService(journey=_service(tmp_path),
            artifact_root_ref="artifacts", fault_injector=lambda point:
            (_ for _ in ()).throw(OSError("crash"))
            if point == "after_quarantine_move" else None).export(
                journey_ref=JOURNEY, expected_event_head=head,
                client_request_id="export-1", packet_ref="packets/journey",
                grant_ref=grant_ref, grant_request=request, body=body)
    assert failure.value.code == "STORE_COMMIT_FAILED"
    report = recover_store(tmp_path, now=NOW)
    transaction = next((tmp_path / "journey-exports" / "v2" / "owners"
                        / OWNER).glob("*.json"))
    assert report["quarantined"] == 1 and report["completed"] == 0
    assert json.loads(transaction.read_bytes())["phase"] == "quarantined"
    assert not (artifacts / "packets" / "journey").exists()


@pytest.mark.parametrize("kind", ("owner", "staging", "quarantine", "lock"))
def test_private_export_roots_reject_abstract_reparse_ancestor(
        tmp_path, monkeypatch, kind):
    """A Windows-style reparse ancestor must not redirect private custody."""
    state = tmp_path / "state"; suspect = state / "journey-exports"
    suspect.mkdir(parents=True)
    original = export_tx._is_reparse
    monkeypatch.setattr(export_tx, "_is_reparse", lambda path:
                        Path(path) == suspect or original(path))
    with pytest.raises(ValueError):
        _private_path(kind, state)
    assert not (suspect / "v2").exists()


@pytest.mark.skipif(os.name == "nt", reason="deterministic POSIX symlink case")
@pytest.mark.parametrize("kind", ("owner", "staging", "quarantine", "lock"))
def test_private_export_roots_reject_real_symlink_ancestor(tmp_path, kind):
    """A real symlink must not create transaction material outside state."""
    state, outside = tmp_path / "state", tmp_path / "outside"
    state.mkdir(); outside.mkdir()
    (state / "journey-exports").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        _private_path(kind, state)
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("kind", ("owner", "staging", "quarantine", "lock"))
def test_private_export_roots_verify_state_containment(tmp_path, monkeypatch, kind):
    """Every private root must reject a computed path outside state custody."""
    state, outside = tmp_path / "state", tmp_path / "outside"
    state.mkdir(); outside.mkdir()
    monkeypatch.setattr(export_tx, "_tx_root", lambda _state: outside)
    with pytest.raises(ValueError):
        _private_path(kind, state)
    assert list(outside.iterdir()) == []


def test_public_export_rejects_broken_reparse_target_before_grant_burn(
        tmp_path, monkeypatch):
    """A broken target reparse point must not consume approved authority."""
    state, evidence = tmp_path / "state", tmp_path / "state" / "artifacts"
    evidence.mkdir(parents=True); head = _concluded(state)
    public = {"journey_ref": JOURNEY, "expected_event_head": head,
        "client_request_id": "export-broken", "packet_ref": "packets/broken"}
    proposed, status = grant_post("/api/grants/prepare/export",
        json.dumps(public).encode(), owner_ref=OWNER, state_root=state,
        evidence_root=evidence, clock=lambda: NOW)
    assert status == 200
    approved, status = grant_post("/api/grants/approve-once", json.dumps({
        "proposal_ref": proposed["proposal_ref"]}).encode(), owner_ref=OWNER,
        state_root=state, evidence_root=evidence, clock=lambda: NOW)
    assert status == 200
    resolved = resolve_approved_grant(approved["grant_ref"], owner_ref=OWNER,
        state_root=state, clock=lambda: NOW)
    target = evidence / "packets" / "broken"; target.mkdir(parents=True)
    real_exists, real_reparse = Path.exists, export_tx._is_reparse
    monkeypatch.setattr(Path, "exists", lambda path:
                        False if path == target else real_exists(path))
    monkeypatch.setattr(export_tx, "_is_reparse", lambda path:
                        path == target or real_reparse(path))
    result, status = journey_post("/api/journeys/export", json.dumps({
        **public, "grant_ref": approved["grant_ref"]}).encode(), owner_ref=OWNER,
        state_root=state, evidence_root=evidence, clock=lambda: NOW)
    assert status == 500 and result["error"]["code"] == "STORE_COMMIT_FAILED"
    consumed = GrantStore(state, clock=lambda: NOW).consume(
        approved["grant_ref"], resolved["grant_request"], now=NOW)
    assert consumed["consumed"] is True


def test_transaction_is_digest_closed_and_omits_raw_grant_ref(tmp_path):
    """Private recovery custody must bind the grant without persisting authority."""
    (tmp_path / "artifacts").mkdir()
    _, grant_ref = _crash(tmp_path, "after_grant_burn")
    paths = list((tmp_path / "journey-exports" / "v2" / "owners" / OWNER).glob("*.json"))
    assert len(paths) == 1
    raw = paths[0].read_bytes(); value = json.loads(raw)
    claimed = value.pop("transaction_sha256")
    assert claimed == canonical_sha256(value)
    assert grant_ref.encode() not in raw and value["phase"] == "prepared"


@pytest.mark.parametrize("packet_refs", [
    ("packets/same", "packets/same"),
    ("packets/one", "packets/two"),
])
def test_two_export_races_have_one_cas_winner_and_no_overwrite(tmp_path, packet_refs):
    """Concurrent same-head exports must publish one exact packet and event."""
    (tmp_path / "artifacts").mkdir(); head = _concluded(tmp_path)
    authorities = [_authority(tmp_path, head, f"export-{index}", packet_ref)
                   for index, packet_ref in enumerate(packet_refs)]
    def run(index):
        request, grant_ref, body = authorities[index]
        try:
            result = JourneyExportService(journey=_service(tmp_path),
                artifact_root_ref="artifacts").export(
                journey_ref=JOURNEY, expected_event_head=head,
                client_request_id=body["client_request_id"],
                packet_ref=body["packet_ref"], grant_ref=grant_ref,
                grant_request=request, body=body)
            return result["structural_verdict"]
        except JourneyStoreError as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(run, range(2)))
    assert sorted(outcomes) == ["HEAD_CONFLICT", "MATCH"]
    assert [event["event_type"] for event in _events(tmp_path)].count("exported") == 1
    assert sum((tmp_path / "artifacts" / ref).is_dir()
               for ref in set(packet_refs)) == 1


@pytest.mark.parametrize("point", ("before_event_fsync", "before_head_replace",
                                    "before_directory_fsync"))
def test_recovery_closes_export_event_commit_windows(tmp_path, point):
    """An event/head crash window must converge to one authoritative H1."""
    (tmp_path / "artifacts").mkdir(); head = _concluded(tmp_path)
    request, grant_ref, body = _authority(tmp_path, head)
    store = JourneyStore(tmp_path, fault_injector=lambda seen:
        (_ for _ in ()).throw(OSError("crash")) if seen == point else None)
    service = JourneyService(owner_ref=OWNER, store=store,
        grants=GrantStore(tmp_path, clock=lambda: NOW), clock=lambda: NOW)
    with pytest.raises(JourneyStoreError):
        JourneyExportService(journey=service, artifact_root_ref="artifacts").export(
            journey_ref=JOURNEY, expected_event_head=head,
            client_request_id="export-1", packet_ref="packets/journey",
            grant_ref=grant_ref, grant_request=request, body=body)
    recover_store(tmp_path, now=NOW)
    events = _events(tmp_path)
    assert events[-1]["event_type"] == "exported"
    assert [event["event_type"] for event in events].count("exported") == 1
