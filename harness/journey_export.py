"""Exact-grant, CAS-bound, recoverable Journey-v2 custody export."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable
from uuid import uuid4

from .evidence_json import canonical_sha256
from .journey_export_tx import (artifact_root_path, consumed_grant_matches,
    grant_record_ref, load_or_create, load_transaction,
    packet_target_path, path_present, prepare_target_parent, quarantine_path,
    request_digest, staging_path, target_lock_path, transaction_path, update_phase)
from .journey_lock import ExclusiveJourneyLock, JourneyLockBusy, fsync_directory
from .journey_packet_v2 import (DOES_NOT_PROVE, PACKET_PROFILE, PACKET_SCHEMA,
    pack_journey_custody_packet, verify_journey_custody_packet)
from .journey_service import JourneyService
from .journey_store import JourneyStoreError
from .operation_grants import GrantError, GrantRequest, GrantStore

EXPORT_SCHEMA = "flywheel.evidence-journey-export/v2"
_BODY_FIELDS = {"client_request_id", "packet_ref", "artifact_root_ref",
                "source_projection_sha256", "packet_profile"}

def plan_export_grant(req: dict, service: JourneyService, state_root: Path,
                      artifact_root_ref: str):
    """Freeze the concluded H0/P0/profile/root/ref export authority."""
    root, artifact_ref = artifact_root_path(state_root, artifact_root_ref)
    _, packet_ref = packet_target_path(root, req["packet_ref"])
    projection = service.resume(req["journey_ref"])
    if projection["event_head_sha256"] != req["expected_event_head"]:
        raise JourneyStoreError("HEAD_CONFLICT")
    if projection["stage"] != "concluded":
        raise JourneyStoreError("INVALID_TRANSITION")
    body = {"client_request_id": req["client_request_id"],
        "packet_ref": packet_ref, "artifact_root_ref": artifact_ref,
        "source_projection_sha256": canonical_sha256(projection),
        "packet_profile": PACKET_PROFILE}
    return "export", body, "journey.export", ("journey:export",), (
        artifact_ref, packet_ref)
class JourneyExportService:
    """Publish an H0 packet, append its H1 event, then acknowledge."""
    def __init__(self, *, journey: JourneyService, artifact_root_ref: str,
                 fault_injector: Callable[[str], None] | None = None) -> None:
        self.journey = journey
        self.artifact_root_ref = artifact_root_ref
        self._fault_injector = fault_injector
    def export(self, *, journey_ref: str, expected_event_head: str,
               client_request_id: str, packet_ref: str, grant_ref: str,
               grant_request: GrantRequest, body: dict) -> dict:
        snapshot = self.journey._snapshot_body(body)
        if (set(snapshot) != _BODY_FIELDS
                or snapshot.get("client_request_id") != client_request_id
                or snapshot.get("packet_ref") != packet_ref
                or snapshot.get("artifact_root_ref") != self.artifact_root_ref
                or snapshot.get("packet_profile") != PACKET_PROFILE):
            raise JourneyStoreError("IDEMPOTENCY_MISMATCH")
        self.journey._validate_lifecycle_selector(
            journey_ref, expected_event_head)
        root, artifact_ref = artifact_root_path(
            self.journey.store.state_root, self.artifact_root_ref)
        target, normalized_packet = packet_target_path(root, packet_ref)
        digest = request_digest(owner_ref=self.journey.owner_ref,
            journey_ref=journey_ref, expected_event_head=expected_event_head,
            client_request_id=client_request_id, body=snapshot)
        path = transaction_path(self.journey.store.state_root,
            self.journey.owner_ref, client_request_id)
        lock_path = target_lock_path(self.journey.store.state_root,
            artifact_ref, normalized_packet)
        try:
            with (self.journey._operation_guard(journey_ref, "export-admission"),
                  ExclusiveJourneyLock.acquire(
                      lock_path, self.journey.store.lock_timeout_s)):
                return self._locked(path=path, request_sha=digest, root=root,
                    target=target, journey_ref=journey_ref,
                    expected_event_head=expected_event_head,
                    client_request_id=client_request_id, packet_ref=normalized_packet,
                    artifact_ref=artifact_ref, grant_ref=grant_ref,
                    grant_request=grant_request, body=snapshot)
        except JourneyLockBusy:
            raise JourneyStoreError("STORE_BUSY") from None
        except (JourneyStoreError, GrantError):
            raise
        except (OSError, TypeError, ValueError):
            raise JourneyStoreError("STORE_COMMIT_FAILED") from None
    def _locked(self, *, path: Path, request_sha: str, root: Path,
                target: Path, journey_ref: str, expected_event_head: str,
                client_request_id: str, packet_ref: str, artifact_ref: str,
                grant_ref: str, grant_request: GrantRequest, body: dict) -> dict:
        current = load_transaction(path)
        if current is not None:
            if current["request_sha256"] != request_sha:
                raise JourneyStoreError("IDEMPOTENCY_MISMATCH")
            return self._advance(path, current, root, target, grant_ref=grant_ref,
                                 grant_request=grant_request, replay=True)
        projection = self._source(journey_ref, expected_event_head, body)
        if path_present(target):
            raise JourneyStoreError("STORE_COMMIT_FAILED")
        self._grant_binding(grant_request, journey_ref, expected_event_head,
                            packet_ref, artifact_ref, body)
        record_ref, grant_sha = grant_record_ref(self.journey.owner_ref, grant_ref)
        template = self._template(request_sha=request_sha,
            journey_ref=journey_ref, expected_event_head=expected_event_head,
            client_request_id=client_request_id, packet_ref=packet_ref,
            artifact_ref=artifact_ref, projection=projection,
            grant_record_ref=record_ref, grant_ref_sha256=grant_sha,
            grant_request_sha256=GrantStore._request_sha(grant_request))
        transaction, _ = load_or_create(path, template)
        return self._advance(path, transaction, root, target, grant_ref=grant_ref,
                             grant_request=grant_request, replay=False)

    def _source(self, journey_ref: str, expected_head: str, body: dict) -> dict:
        projection = self.journey.resume(journey_ref)
        if projection["event_head_sha256"] != expected_head:
            raise JourneyStoreError("HEAD_CONFLICT")
        if projection["stage"] != "concluded":
            raise JourneyStoreError("INVALID_TRANSITION")
        if body["source_projection_sha256"] != canonical_sha256(projection):
            raise GrantError("PERMISSION_DENIED")
        return projection

    def _grant_binding(self, request: GrantRequest, journey_ref: str,
                       expected_head: str, packet_ref: str, artifact_ref: str,
                       body: dict) -> None:
        self.journey._require_binding(request, tool="journey.export",
            journey_ref=journey_ref, expected_event_head=expected_head,
            operation="export", body=body)
        if (request.scopes != ("journey:export",)
                or request.data_refs != (artifact_ref, packet_ref)):
            raise GrantError("PERMISSION_DENIED")

    def _template(self, **facts) -> dict:
        return {"schema": "flywheel.evidence-journey-export-transaction/v1",
            "owner_ref": self.journey.owner_ref,
            "client_request_sha256": canonical_sha256(facts["client_request_id"]),
            "request_sha256": facts["request_sha"],
            "journey_ref": facts["journey_ref"],
            "source_event_head_sha256": facts["expected_event_head"],
            "source_projection_sha256": canonical_sha256(facts["projection"]),
            "artifact_root_ref": facts["artifact_ref"],
            "packet_ref": facts["packet_ref"], "packet_profile": PACKET_PROFILE,
            "internal_request_id": "journey-export:" + canonical_sha256(
                facts["client_request_id"]),
            "grant_record_ref": facts["grant_record_ref"],
            "grant_ref_sha256": facts["grant_ref_sha256"],
            "grant_request_sha256": facts["grant_request_sha256"],
            "phase": "prepared", "packet_digest": None,
            "final_event_head_sha256": None,
            "final_projection_sha256": None, "transaction_sha256": ""}

    def _advance(self, path: Path, value: dict, root: Path, target: Path,
                 *, grant_ref: str | None = None,
                 grant_request: GrantRequest | None = None,
                 replay: bool = True) -> dict | None:
        if value["phase"] == "quarantine_pending":
            self._finish_quarantine(path, value, target)
            raise JourneyStoreError("HEAD_CONFLICT")
        if value["phase"] == "quarantined":
            raise JourneyStoreError("HEAD_CONFLICT")
        if value["phase"] == "prepared":
            value = self._authorize(path, value, grant_ref, grant_request)
            if value is None:
                return None
        if value["phase"] == "authorized":
            value = self._pack(path, value, root, target)
        if value["phase"] == "packed":
            value = self._publish(path, value, target)
        if value["phase"] == "published":
            value = self._commit_event(path, value, target)
        if value["phase"] != "committed":
            raise JourneyStoreError("STORE_COMMIT_FAILED")
        result = self._replay(value, target, replay=replay)
        self._checkpoint("before_response")
        return result

    def _authorize(self, path: Path, value: dict, grant_ref: str | None,
                   request: GrantRequest | None) -> dict | None:
        if consumed_grant_matches(self.journey.store.state_root, value):
            return update_phase(path, value, "authorized")
        if grant_ref is None or request is None:
            return None
        if (GrantStore._request_sha(request) != value["grant_request_sha256"]
                or canonical_sha256(grant_ref) != value["grant_ref_sha256"]):
            raise GrantError("PERMISSION_DENIED")
        self.journey.grants.consume(grant_ref, request, now=self.journey.clock())
        self._checkpoint("after_grant_burn")
        if not consumed_grant_matches(self.journey.store.state_root, value):
            raise JourneyStoreError("STORE_COMMIT_FAILED")
        return update_phase(path, value, "authorized")

    def _pack(self, path: Path, value: dict, root: Path, target: Path) -> dict:
        projection = self._source(value["journey_ref"],
            value["source_event_head_sha256"], {
                "source_projection_sha256": value["source_projection_sha256"]})
        stage = staging_path(self.journey.store.state_root, value)
        if path_present(stage):
            residue = quarantine_path(self.journey.store.state_root, value).with_name(
                f"{value['client_request_sha256']}-partial-{uuid4().hex}")
            os.rename(stage, residue); fsync_directory(residue.parent)
        result = pack_journey_custody_packet(
            stage, events=self.journey._events(value["journey_ref"]),
            projection=projection)
        packet_digest = result["packet_digest"]
        anchored = verify_journey_custody_packet(
            stage, expected_manifest_sha256=packet_digest)
        if anchored.get("verdict") != "MATCH" or path_present(target):
            raise JourneyStoreError("STORE_COMMIT_FAILED")
        value = update_phase(path, value, "packed", packet_digest=packet_digest)
        self._checkpoint("after_staging_flush")
        return value

    def _publish(self, path: Path, value: dict, target: Path) -> dict:
        stage = staging_path(self.journey.store.state_root, value)
        if path_present(target) and not path_present(stage):
            checked = verify_journey_custody_packet(
                target, expected_manifest_sha256=value["packet_digest"])
            if checked.get("verdict") != "MATCH":
                raise JourneyStoreError("STORE_COMMIT_FAILED")
        else:
            if path_present(target) or not stage.is_dir():
                raise JourneyStoreError("STORE_COMMIT_FAILED")
            root = target.parents[len(Path(value["packet_ref"]).parts) - 1]
            prepare_target_parent(root, target)
            os.rename(stage, target); fsync_directory(target.parent)
        value = update_phase(path, value, "published")
        self._checkpoint("after_publish")
        return value

    def _commit_event(self, path: Path, value: dict, target: Path) -> dict:
        checked = verify_journey_custody_packet(
            target, expected_manifest_sha256=value["packet_digest"])
        if checked.get("verdict") != "MATCH":
            raise JourneyStoreError("STORE_COMMIT_FAILED")
        payload = self._event_payload(value)
        try:
            ack = self.journey._append_lifecycle(
                journey_ref=value["journey_ref"],
                expected_event_head=value["source_event_head_sha256"],
                client_request_id=value["internal_request_id"],
                operation="exported", payload=payload)
        except JourneyStoreError as exc:
            if exc.code != "HEAD_CONFLICT":
                raise
            value = update_phase(path, value, "quarantine_pending")
            self._finish_quarantine(path, value, target)
            raise
        self._checkpoint("after_event_commit")
        return update_phase(path, value, "committed",
            final_event_head_sha256=ack.event_head_sha256,
            final_projection_sha256=ack.projection_sha256)

    def _finish_quarantine(self, path: Path, value: dict, target: Path) -> dict:
        held = quarantine_path(self.journey.store.state_root, value)
        if path_present(target):
            if path_present(held):
                raise JourneyStoreError("STORE_COMMIT_FAILED")
            os.rename(target, held); fsync_directory(target.parent)
            fsync_directory(held.parent); self._checkpoint("after_quarantine_move")
        elif not path_present(held):
            raise JourneyStoreError("STORE_COMMIT_FAILED")
        return update_phase(path, value, "quarantined")

    @staticmethod
    def _event_payload(value: dict) -> dict:
        return {"packet_schema": PACKET_SCHEMA,
            "packet_profile": PACKET_PROFILE, "packet_ref": value["packet_ref"],
            "packet_manifest_sha256": value["packet_digest"],
            "source_event_head_sha256": value["source_event_head_sha256"],
            "source_projection_sha256": value["source_projection_sha256"]}

    def _replay(self, value: dict, target: Path, *, replay: bool) -> dict:
        checked = verify_journey_custody_packet(
            target, expected_manifest_sha256=value["packet_digest"])
        if checked.get("verdict") != "MATCH":
            raise JourneyStoreError("STORE_COMMIT_FAILED")
        ack = self.journey._append_lifecycle(
            journey_ref=value["journey_ref"],
            expected_event_head=value["source_event_head_sha256"],
            client_request_id=value["internal_request_id"], operation="exported",
            payload=self._event_payload(value))
        if (ack.event_head_sha256 != value["final_event_head_sha256"]
                or ack.projection_sha256 != value["final_projection_sha256"]):
            raise JourneyStoreError("STORE_COMMIT_FAILED")
        return {"schema": EXPORT_SCHEMA, "profile": PACKET_PROFILE,
            "journey_ref": value["journey_ref"],
            "source_event_head_sha256": value["source_event_head_sha256"],
            "final_event_head_sha256": value["final_event_head_sha256"],
            "final_projection_sha256": value["final_projection_sha256"],
            "packet_ref": value["packet_ref"],
            "packet_digest": value["packet_digest"],
            "structural_verdict": checked["structural_verdict"],
            "authenticity_verdict": checked["authenticity_verdict"],
            "rehash_resistance_verdict": checked["rehash_resistance_verdict"],
            "idempotent_replay": replay,
            "does_not_prove": list(DOES_NOT_PROVE)}

    def _checkpoint(self, point: str) -> None:
        if self._fault_injector is not None:
            try: self._fault_injector(point)
            except Exception: raise JourneyStoreError("STORE_COMMIT_FAILED") from None
