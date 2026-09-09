"""Writing Workspace service over Journey v2 and exact grants."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from .evidence_json import canonical_bytes, strict_load_json
from .evidence_public import TransportError
from .grant_route import grant_post, read_proposal_record
from .journey_route import journey_post
from .journey_service import JourneyService
from .journey_store import JourneyStore
from .operation_grants import GrantStore, load_or_create_owner_ref
from .writing_artifacts import WritingArtifactError, WritingArtifactStore
from .writing_projection import WritingProjectionError, project_from_events, validate_writing_append
from .writing_preview import build_proposal_preview
from .writing_reader_flow import build_diagnostic, scope_replacement_plan
from .writing_state_authority import review_source_refs_from_diagnostic
from .writing_state_rules import WritingStateError, validate_transition
from .writing_types import MAX_BRIEF_JSON_BYTES, MAX_MANUSCRIPT_TEXT_BYTES, MAX_SOURCE_PACKET_BYTES, SCHEMAS, WRITING_DOES_NOT_PROVE, admit_text, sha256_bytes, validate_artifact, validate_target
class WritingError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)
class WritingService:
    def __init__(self, home: Path, *, clock=None) -> None:
        self.home = Path(home)
        self.clock = clock or (
            lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
        self.state_root = self.home / "state"
        self.owner_ref = load_or_create_owner_ref(self.home)
        self.artifacts = WritingArtifactStore(self.state_root)
    def status(self) -> dict:
        projects = []
        service = self._journeys()
        for item in service.list():
            state = self.project_state(item["journey_ref"])
            if state["intake"].get("schema") == "flywheel.writing-intake/v1":
                projects.append(self._public_project(state))
        return {"schema": "flywheel.writing-status/v1", "projects": projects}
    def doctor(self) -> dict:
        return {"schema": "flywheel.writing-doctor/v1", "journey_store": "present",
                "artifact_store": "present", "semantic_quality": "unmeasured"}
    def prepare_init(self, brief_path: Path, source_packet_path: Path, *, client_request_id: str) -> dict:
        brief = validate_artifact(_load_json_file(
            brief_path, max_bytes=MAX_BRIEF_JSON_BYTES), "brief")
        source = validate_artifact(_load_json_file(
            source_packet_path, max_bytes=MAX_SOURCE_PACKET_BYTES), "source_packet")
        project_ref = brief["project_ref"]
        if source["project_ref"] != project_ref:
            raise WritingError("PROJECT_MISMATCH")
        brief_rec = self.artifacts.write_json(self.owner_ref, project_ref, "brief", "brief", brief)
        source_rec = self.artifacts.write_json(self.owner_ref, project_ref, "source_packet", "source_packet", source)
        intake = {"schema": "flywheel.writing-intake/v1", "project_ref": project_ref,
                  "brief_ref": brief_rec["artifact_ref"], "brief_sha256": brief_rec["artifact_sha256"],
                  "source_packet_ref": source_rec["artifact_ref"], "source_packet_sha256": source_rec["artifact_sha256"]}
        intake_rec = self.artifacts.write_manifest(self.owner_ref, project_ref, "intake", "intake", intake)
        request = {"goal": "Writing workspace project", "intake_ref": intake_rec["artifact_ref"], "client_request_id": client_request_id}
        proposal = self._prepare("create", request)
        return {**proposal, "approval_required": True, "project_ref": project_ref, "intake_ref": intake_rec["artifact_ref"]}
    def prepare_section(self, journey_ref: str, expected_event_head: str, section: dict, *, client_request_id: str) -> dict:
        artifact = validate_artifact(section, "section")
        state = self.project_state(journey_ref)
        if artifact["section_ref"] not in state["sections"] and len(state["sections"]) >= 8:
            raise WritingError("SECTION_LIMIT")
        return self._prepare_artifact(journey_ref, expected_event_head, client_request_id, "section", artifact["section_ref"], artifact)
    def prepare_revision(self, journey_ref: str, expected_event_head: str, project_ref: str, section_ref: str, body: str | bytes, *, client_request_id: str) -> dict:
        state = self.project_state(journey_ref); section = state["sections"].get(section_ref)
        if section is None: raise WritingError("SECTION_NOT_FOUND")
        text, raw, admission = admit_text(body); digest = sha256_bytes(raw); base_ref = section.get("current_revision_ref")
        revision_ref = f"rev_{sha256_bytes((section_ref + (base_ref or '') + digest + client_request_id).encode())[:32]}"
        body_rec = self.artifacts.write_text(self.owner_ref, project_ref, "body", revision_ref, body)
        artifact = {"schema": SCHEMAS["revision"], "project_ref": project_ref,
            "section_ref": section_ref, "revision_ref": revision_ref,
            "base_revision_ref": base_ref, "body_ref": body_rec["artifact_ref"],
            "body_sha256": digest, "word_count": len(text.split()),
            "author_supplied": True, "scope_refs": [],
            "text_admission": admission, "does_not_prove": [WRITING_DOES_NOT_PROVE]}
        proposal = self._prepare_artifact(journey_ref, expected_event_head, client_request_id, "revision", revision_ref, artifact)
        return {**proposal, "revision_ref": revision_ref, "body_sha256": digest}
    def prepare_diagnose(self, journey_ref: str, expected_event_head: str,
                         project_ref: str, revision_ref: str, *,
                         client_request_id: str) -> dict:
        state = self.project_state(journey_ref); revision = state["revisions"][revision_ref]
        artifact = build_diagnostic(project_ref=project_ref,
            section_ref=revision["section_ref"], revision_ref=revision_ref,
            body_sha256=revision["body_sha256"], body=self._revision_body(state, revision_ref),
            source_ids=self._source_ids(state))
        return self._prepare_artifact(journey_ref, expected_event_head, client_request_id, "diagnostic", artifact["diagnostic_ref"], artifact)
    def prepare_card(self, journey_ref: str, expected_event_head: str, card: dict,
                     *, client_request_id: str) -> dict:
        artifact = validate_artifact(card, "card"); state = self.project_state(journey_ref)
        validate_target(artifact["target"], body=self._revision_body(state, artifact["target"]["base_revision_ref"]))
        try:
            validate_transition(state, "card", artifact, self.artifacts, self.owner_ref)
        except WritingStateError as exc:
            raise WritingError(exc.code) from exc
        return self._prepare_artifact(journey_ref, expected_event_head, client_request_id, "card", artifact["card_ref"], artifact)
    def prepare_candidate(self, journey_ref: str, expected_event_head: str,
                          project_ref: str, card_ref: str, body: str | bytes,
                          *, client_request_id: str) -> dict:
        state = self.project_state(journey_ref); card = state["cards"][card_ref]
        base_ref = card["target"]["base_revision_ref"]; base = self._revision_body(state, base_ref)
        text, raw, admission = admit_text(body); digest = sha256_bytes(raw)
        receipt = scope_replacement_plan(base, text, card["target"])
        candidate_ref = f"cand_{sha256_bytes((card_ref + digest).encode())[:32]}"
        body_rec = self.artifacts.write_text(self.owner_ref, project_ref, "body", candidate_ref, body)
        artifact = {"schema": SCHEMAS["candidate"], "project_ref": project_ref,
            "candidate_ref": candidate_ref, "card_ref": card_ref,
            "base_revision_ref": base_ref,
            "candidate_revision_ref": f"rev_{sha256_bytes((candidate_ref + digest).encode())[:32]}",
            "candidate_body_ref": body_rec["artifact_ref"],
            "candidate_body_sha256": digest,
            "diff_summary": "candidate replaces the scoped target span",
            "out_of_scope_changes": receipt["failure_reasons"],
            "created_by": "writing_service", "scope_receipt": receipt,
            "text_admission": admission, "does_not_prove": [WRITING_DOES_NOT_PROVE]}
        proposal = self._prepare_artifact(journey_ref, expected_event_head, client_request_id, "candidate", candidate_ref, artifact)
        return {**proposal, "candidate_ref": candidate_ref, "scope_verdict": receipt["verdict"]}
    def prepare_decision(self, journey_ref: str, expected_event_head: str,
                         project_ref: str, *, decision: str,
                         candidate_ref: str | None = None,
                         section_ref: str | None = None,
                         to_revision_ref: str | None = None,
                         reason: str | None = None,
                         client_request_id: str) -> dict:
        state = self.project_state(journey_ref); scope_verdict = "NOT_APPLICABLE"
        if decision in {"accept", "reject", "supersede"}:
            candidate = state["candidates"][candidate_ref]; card = state["cards"][candidate["card_ref"]]
            section_ref = card["target"]["section_ref"]; to_revision_ref = candidate["candidate_revision_ref"]
            from_revision_ref = card["target"]["base_revision_ref"]; scope_verdict = candidate["scope_receipt"]["verdict"]
            candidate_artifact_ref = candidate["artifact_ref"]; candidate_artifact_sha = candidate["artifact_sha256"]
        elif decision == "rollback":
            section = state["sections"][section_ref]; from_revision_ref = section["current_revision_ref"]
            if to_revision_ref not in state["accepted_revision_refs_by_section"].get(section_ref, []): raise WritingError("ROLLBACK_TARGET_INVALID")
            candidate_artifact_ref = None; candidate_artifact_sha = None
        else: raise WritingError("DECISION_INVALID")
        decision_ref = f"dec_{sha256_bytes((client_request_id + decision).encode())[:32]}"
        artifact = {"schema": SCHEMAS["decision"], "project_ref": project_ref,
            "decision_ref": decision_ref, "decision": decision,
            "section_ref": section_ref, "candidate_ref": candidate_ref,
            "candidate_artifact_ref": candidate_artifact_ref,
            "candidate_artifact_sha256": candidate_artifact_sha,
            "from_revision_ref": from_revision_ref, "to_revision_ref": to_revision_ref,
            "reason": reason or f"author {decision} decision",
            "scope_verdict": scope_verdict, "decided_at": self.clock(),
            "does_not_prove": [WRITING_DOES_NOT_PROVE]}
        return self._prepare_artifact(journey_ref, expected_event_head, client_request_id, "decision", decision_ref, artifact)
    def prepare_review(self, journey_ref: str, expected_event_head: str,
                       project_ref: str, *, client_request_id: str) -> dict:
        state = self.project_state(journey_ref); review_ref = f"wrev_{sha256_bytes(client_request_id.encode())[:32]}"
        revs = self._current_revision_refs(state); latest = self._latest_ref(state["diagnostics"], "diag_unmeasured")
        diag = state["diagnostics"].get(latest); flow = latest if type(diag) is dict and diag["revision_ref"] in revs else "diag_unmeasured"
        measured = flow != "diag_unmeasured"; source_refs = review_source_refs_from_diagnostic(diag) if measured else []
        unmeasured = {"status": "unmeasured", "basis": "none", "measurement_status": "unmeasured"}
        artifact = {"schema": SCHEMAS["review"], "project_ref": project_ref,
            "review_ref": review_ref, "revision_refs": revs, "reader_flow_ref": flow,
            "source_coverage": {"status": "checked" if measured else "unmeasured",
            "basis": "deterministic" if measured else "none",
            "measurement_status": "checked" if measured else "unmeasured",
            "source_packet_ref": self._source_packet_public_ref(state), "diagnostic_ref": flow,
            "source_refs": source_refs},
            "style_lint": {**unmeasured, "source_refs": []},
            "scope_preservation": {"status": "checked" if measured else "unmeasured",
            "basis": "deterministic" if measured else "none",
            "measurement_status": "checked" if measured else "unmeasured",
            "decision_refs": [row["decision_ref"] for row in state["decisions"]]},
            "quality_measurement": {**unmeasured, "source_refs": []},
            "blocking_items": [], "does_not_prove": [WRITING_DOES_NOT_PROVE]}
        return self._prepare_artifact(journey_ref, expected_event_head, client_request_id, "review", review_ref, artifact)
    def prepare_export(self, journey_ref: str, expected_event_head: str,
                       project_ref: str, *, out_ref: str,
                       client_request_id: str) -> dict:
        if self.artifacts.exists(self.owner_ref, project_ref, "export", out_ref, ".json") or self.artifacts.exists(self.owner_ref, project_ref, "manuscript", out_ref, ".txt"):
            raise WritingError("EXPORT_TARGET_EXISTS")
        state = self.project_state(journey_ref)
        text = "\n".join(state["sections"][name]["current_body"] or "" for name in state["section_order"])
        manuscript = self.artifacts.write_text(self.owner_ref, project_ref,
            "manuscript", out_ref, text, max_bytes=MAX_MANUSCRIPT_TEXT_BYTES)
        export_ref = f"wexp_{sha256_bytes(out_ref.encode())[:32]}"
        artifact = {"schema": SCHEMAS["export"], "project_ref": project_ref,
            "export_ref": export_ref, "manuscript_ref": manuscript["artifact_ref"],
            "manuscript_sha256": manuscript["artifact_sha256"],
            "included_sections": self._included_sections(state),
            "decision_refs": [row["decision_ref"] for row in state["decisions"]],
            "review_ref": self._latest_ref({row["review_ref"]: row for row in state["reviews"]}, "wrev_unmeasured"),
            "source_packet_ref": self._source_packet_public_ref(state),
            "journey_ref": journey_ref, "event_head_sha256": expected_event_head,
            "does_not_prove": [WRITING_DOES_NOT_PROVE]}
        return self._prepare_artifact(journey_ref, expected_event_head, client_request_id, "export", export_ref, artifact)
    def approve_proposal(self, proposal_ref: str) -> dict:
        result, status = grant_post(
            "/api/grants/approve-once", canonical_bytes({"proposal_ref": proposal_ref}),
            owner_ref=self.owner_ref, state_root=self.state_root,
            evidence_root=self.artifacts.root, clock=self.clock)
        return _ok(result, status)
    def commit_proposal(self, proposal_ref: str, grant_ref: str) -> dict:
        record = read_proposal_record(
            proposal_ref, owner_ref=self.owner_ref, state_root=self.state_root)
        self._revalidate_record(record)
        request = {**record["request"], "grant_ref": grant_ref}
        route = record["action"]
        result, status = journey_post(
            f"/api/journeys/{route}", canonical_bytes(request),
            owner_ref=self.owner_ref, state_root=self.state_root,
            evidence_root=self.artifacts.root, clock=self.clock)
        ack = _ok(result, status)
        return {**ack, **_proposal_context(record)}
    def proposal_get(self, proposal_ref: str) -> dict:
        try:
            record = read_proposal_record(
                proposal_ref, owner_ref=self.owner_ref, state_root=self.state_root)
            return build_proposal_preview(
                record, artifacts=self.artifacts, owner_ref=self.owner_ref,
                project_state=self.project_state)
        except (WritingArtifactError, WritingProjectionError) as exc:
            raise WritingError(exc.code) from exc
    def project_state(self, journey_ref: str) -> dict:
        try:
            return project_from_events(self._journeys()._events(journey_ref), self.artifacts)
        except (WritingArtifactError, WritingProjectionError) as exc:
            raise WritingError(exc.code) from exc
    def read_text(self, artifact_ref: str, digest: str | None = None) -> str:
        return self.artifacts.read_text(artifact_ref, digest,
            expected_owner_ref=self.owner_ref, max_bytes=MAX_MANUSCRIPT_TEXT_BYTES)
    def _prepare_artifact(self, journey_ref: str, expected_head: str,
                          request_id: str, kind: str, name: str, artifact: dict) -> dict:
        rec = self.artifacts.write_json(self.owner_ref, artifact["project_ref"], kind, name, artifact)
        command = {"type": "record_writing_artifact", "kind": kind,
                   "artifact_ref": rec["artifact_ref"],
                   "artifact_sha256": rec["artifact_sha256"],
                   "opaque_ref": name}
        request = {"journey_ref": journey_ref, "expected_event_head": expected_head,
                   "client_request_id": request_id, "command": command}
        proposal = self._prepare("append", request)
        return {**proposal, "approval_required": True, "artifact_ref": rec["artifact_ref"],
                "artifact_sha256": rec["artifact_sha256"]}
    def _prepare(self, action: str, request: dict) -> dict:
        result, status = grant_post(
            f"/api/grants/prepare/{action}", canonical_bytes(request),
            owner_ref=self.owner_ref, state_root=self.state_root,
            evidence_root=self.artifacts.root, clock=self.clock)
        return _ok(result, status)
    def _journeys(self) -> JourneyService:
        return JourneyService(owner_ref=self.owner_ref, store=JourneyStore(self.state_root),
                              grants=GrantStore(self.state_root, clock=self.clock),
                              clock=self.clock)
    def _revision_body(self, state: dict, revision_ref: str) -> str:
        revision = state["revisions"][revision_ref]
        return self.artifacts.read_text(
            revision["body_ref"], revision["body_sha256"],
            expected_owner_ref=self.owner_ref, expected_project_ref=state["project_ref"])
    def _public_project(self, state: dict) -> dict:
        return {"project_ref": state["project_ref"], "journey_ref": state["journey_ref"],
                "event_head_sha256": state["event_head_sha256"],
                "section_refs": list(state["section_order"])}
    def _revalidate_record(self, record: dict) -> None:
        if record["action"] != "append":
            return
        try:
            validate_writing_append(
                self._journeys(), self.artifacts, record["request"],
                record["operation"], record["operation_body"])
        except (WritingArtifactError, WritingProjectionError, TransportError) as exc:
            raise WritingError(exc.code) from exc
    def _source_packet(self, state: dict) -> dict:
        intake = state["intake"]
        return self.artifacts.read_json(intake["source_packet_ref"],
            intake["source_packet_sha256"], expected_kind="source_packet",
            max_bytes=MAX_SOURCE_PACKET_BYTES,
            expected_owner_ref=self.owner_ref, expected_project_ref=state["project_ref"])
    def _source_packet_public_ref(self, state: dict) -> str:
        packet = self._source_packet(state)
        return packet.get("source_packet_ref") or state["intake"]["source_packet_ref"]
    def _source_ids(self, state: dict) -> list[str]:
        return [src.get("source_id", src.get("source_ref")) for src in self._source_packet(state)["sources"]]
    @staticmethod
    def _latest_ref(rows: dict, missing: str) -> str:
        return next(reversed(rows), missing)
    @staticmethod
    def _current_revision_refs(state: dict) -> list[str]:
        return [state["sections"][name]["current_revision_ref"]
                for name in state["section_order"]
                if state["sections"][name].get("current_revision_ref")]
    @staticmethod
    def _included_sections(state: dict) -> list[dict]:
        return [{"section_ref": name,
            "revision_ref": state["sections"][name]["current_revision_ref"],
            "body_sha256": state["sections"][name]["current_body_sha256"],
            "order_index": state["sections"][name]["order_index"]}
            for name in state["section_order"]
            if state["sections"][name].get("current_revision_ref")]
def _load_json_file(path: Path, *, max_bytes: int = 262_144) -> dict:
    path = Path(path)
    if not path.is_file() or path.stat().st_size > max_bytes: raise WritingError("INPUT_UNAVAILABLE")
    return strict_load_json(path.read_bytes(), max_bytes=max_bytes, max_depth=32)
def _ok(result: dict, status: int) -> dict:
    if status == 200: return result
    raise WritingError(result.get("error", {}).get("code", "WRITING_FAILED"))
def _proposal_context(record: dict) -> dict:
    return {"project_ref": record["operation_body"]["intake"]["project_ref"]} if record["action"] == "create" else {}
