"""Private HTTP route adapter for the Writing Workspace."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlsplit

from .evidence_json import canonical_bytes
from .evidence_public import (
    TransportError, error_response, exact_request, parse_json, public_result)
from .writing_artifacts import WritingArtifactError
from .writing_service import WritingError, WritingService
from .writing_types import WritingTypeError, sha256_bytes

ROUTE_PREFIX = "/api/writing/"


def writing_get(path: str, *, owner_ref: str, state_root: Path,
                clock) -> tuple[dict, int]:
    try:
        route, query = _split(path)
        service = _service(state_root, clock)
        if route == "status":
            return _ok(_public_status(service))
        if route == "doctor":
            return _ok(service.doctor())
        if route == "project":
            journey = _single(query, "journey_ref")
            return _ok(_public_project_state(service, journey))
        raise TransportError("NOT_FOUND", "writing route not found", 404)
    except (TransportError, WritingError, Exception) as exc:
        return _mapped_error(exc)


def writing_post(path: str, raw: bytes, *, owner_ref: str, state_root: Path,
                 clock) -> tuple[dict, int]:
    try:
        route, _query = _split(path)
        request = parse_json(raw)
        service = _service(state_root, clock)
        if route == "init/prepare":
            result = _prepare_init(service, exact_request(
                request, {"brief", "source_packet", "client_request_id"}))
        elif route == "section/prepare":
            req = exact_request(request, {
                "journey_ref", "expected_event_head", "client_request_id",
                "section"})
            result = service.prepare_section(
                req["journey_ref"], req["expected_event_head"], req["section"],
                client_request_id=req["client_request_id"])
        elif route == "revision/prepare":
            req = exact_request(request, {
                "journey_ref", "expected_event_head", "project_ref",
                "section_ref", "body", "client_request_id"})
            result = service.prepare_revision(
                req["journey_ref"], req["expected_event_head"],
                req["project_ref"], req["section_ref"], req["body"],
                client_request_id=req["client_request_id"])
        elif route == "diagnose/prepare":
            req = exact_request(request, {
                "journey_ref", "expected_event_head", "project_ref",
                "revision_ref", "client_request_id"})
            result = service.prepare_diagnose(
                req["journey_ref"], req["expected_event_head"],
                req["project_ref"], req["revision_ref"],
                client_request_id=req["client_request_id"])
        elif route == "card/prepare":
            req = exact_request(request, {
                "journey_ref", "expected_event_head", "client_request_id",
                "card"})
            result = service.prepare_card(
                req["journey_ref"], req["expected_event_head"], req["card"],
                client_request_id=req["client_request_id"])
        elif route == "candidate/prepare":
            req = exact_request(request, {
                "journey_ref", "expected_event_head", "project_ref",
                "card_ref", "body", "client_request_id"})
            result = service.prepare_candidate(
                req["journey_ref"], req["expected_event_head"],
                req["project_ref"], req["card_ref"], req["body"],
                client_request_id=req["client_request_id"])
        elif route == "decision/prepare":
            result = _prepare_decision(service, request)
        elif route == "review/prepare":
            req = exact_request(request, {
                "journey_ref", "expected_event_head", "project_ref",
                "client_request_id"})
            result = service.prepare_review(
                req["journey_ref"], req["expected_event_head"],
                req["project_ref"], client_request_id=req["client_request_id"])
        elif route == "export/prepare":
            req = exact_request(request, {
                "journey_ref", "expected_event_head", "project_ref",
                "out_ref", "client_request_id"})
            result = service.prepare_export(
                req["journey_ref"], req["expected_event_head"],
                req["project_ref"], out_ref=req["out_ref"],
                client_request_id=req["client_request_id"])
        elif route == "proposal/get":
            req = exact_request(request, {"proposal_ref"})
            return _ok(_public_preview(service, req["proposal_ref"]))
        elif route == "proposal/approve":
            req = exact_request(request, {"proposal_ref"})
            return _ok(service.approve_proposal(req["proposal_ref"]))
        elif route == "proposal/commit":
            req = exact_request(request, {"proposal_ref", "grant_ref"})
            return _ok(service.commit_proposal(
                req["proposal_ref"], req["grant_ref"]))
        elif route == "project/get":
            req = exact_request(request, {"journey_ref"})
            return _ok(_public_project_state(service, req["journey_ref"]))
        else:
            raise TransportError("NOT_FOUND", "writing route not found", 404)
        return _ok(_with_artifact_id(service, result))
    except (TransportError, WritingError, Exception) as exc:
        return _mapped_error(exc)


def _service(state_root: Path, clock) -> WritingService:
    return WritingService(Path(state_root).parent, clock=clock)


def _prepare_init(service: WritingService, req: dict) -> dict:
    with TemporaryDirectory(prefix="flywheel-writing-") as tmp:
        root = Path(tmp)
        brief = root / "brief.json"; source = root / "source_packet.json"
        brief.write_bytes(canonical_bytes(req["brief"]))
        source.write_bytes(canonical_bytes(req["source_packet"]))
        return service.prepare_init(
            brief, source, client_request_id=req["client_request_id"])


def _prepare_decision(service: WritingService, req: dict) -> dict:
    req = exact_request(req, {"journey_ref", "expected_event_head",
        "project_ref", "decision", "client_request_id", "candidate_ref",
        "section_ref", "to_revision_ref", "reason"}, optional={
        "candidate_ref", "section_ref", "to_revision_ref", "reason"})
    return service.prepare_decision(
        req["journey_ref"], req["expected_event_head"], req["project_ref"],
        decision=req["decision"], candidate_ref=req.get("candidate_ref"),
        section_ref=req.get("section_ref"), to_revision_ref=req.get("to_revision_ref"),
        reason=req.get("reason"), client_request_id=req["client_request_id"])


def _public_status(service: WritingService) -> dict:
    return service.status()


def _public_project_state(service: WritingService, journey_ref: str) -> dict:
    state = service.project_state(journey_ref)
    packet = service._source_packet(state)
    return {"schema": "flywheel.writing-project-view/v1",
        "project_ref": state["project_ref"], "journey_ref": state["journey_ref"],
        "event_head_sha256": state["event_head_sha256"],
        "source_packet": {"source_packet_ref": packet["source_packet_ref"],
        "sources": packet["sources"],
        "does_not_prove": packet["does_not_prove"]},
        "sections": [_public_section(state, ref) for ref in state["section_order"]],
        "diagnostics": list(state["diagnostics"].values()),
        "cards": list(state["cards"].values()),
        "candidates": list(state["candidates"].values()),
        "decisions": state["decisions"], "reviews": state["reviews"],
        "exports": state["exports"],
        "does_not_prove": ["semantic quality, factual truth, and source truth remain unmeasured unless shown by recorded checks"]}


def _public_section(state: dict, ref: str) -> dict:
    section = state["sections"][ref]
    return {"section_ref": ref, "heading": section["heading"],
        "purpose": section["purpose"], "order_index": section["order_index"],
        "current_revision_ref": section.get("current_revision_ref"),
        "current_body_sha256": section.get("current_body_sha256"),
        "current_body": section.get("current_body")}


def _public_preview(service: WritingService, proposal_ref: str) -> dict:
    preview = service.proposal_get(proposal_ref)
    approval = preview.get("approval_preview")
    if type(approval) is dict and approval.get("kind") == "candidate":
        state = service.project_state(preview["request"]["journey_ref"])
        target = approval["target"]
        revision = state["revisions"][target["base_revision_ref"]]
        before = service.read_text(revision["body_ref"],
                                   target["base_body_sha256"])
        after = approval["candidate_body"]
        approval["exact_diff"] = {"before": before, "after": after,
            "before_sha256": target["base_body_sha256"],
            "after_sha256": sha256_bytes(after.encode("utf-8")),
            "coordinate_type": target["coordinate_type"],
            "start": target["start"], "end": target["end"]}
    return preview


def _with_artifact_id(service: WritingService, result: dict) -> dict:
    if "artifact_ref" not in result or "artifact_sha256" not in result:
        return result
    preview = service.proposal_get(result["proposal_ref"])
    artifact = preview.get("writing_artifact", {})
    return {**result, "artifact_kind": artifact.get("kind"),
            "artifact_id": artifact.get("artifact_id")}


def _split(path: str) -> tuple[str, dict[str, list[str]]]:
    parts = urlsplit(path)
    if not parts.path.startswith(ROUTE_PREFIX):
        raise TransportError("NOT_FOUND", "writing route not found", 404)
    return parts.path.removeprefix(ROUTE_PREFIX), parse_qs(parts.query)


def _single(query: dict[str, list[str]], name: str) -> str:
    values = query.get(name)
    if values is None or len(values) != 1 or not values[0]:
        raise TransportError("MISSING_FIELD", "request is missing required fields")
    return values[0]


def _ok(value: dict) -> tuple[dict, int]:
    return public_result("writing", value), 200


def _mapped_error(exc: Exception) -> tuple[dict, int]:
    if isinstance(exc, TransportError):
        return error_response(exc)
    if isinstance(exc, WritingError):
        return error_response(TransportError(
            exc.code, "writing workflow is unavailable", _status(exc.code)))
    if isinstance(exc, WritingArtifactError):
        return error_response(TransportError(
            exc.code, "writing artifact is unavailable", _status(exc.code)))
    if isinstance(exc, WritingTypeError):
        return error_response(TransportError(
            str(exc), "writing request is invalid", 422))
    return error_response(TransportError(
        "WRITING_FAILED", "writing workflow is unavailable", 500))


def _status(code: str) -> int:
    if code in {"HEAD_CONFLICT", "EXPORT_TARGET_EXISTS", "ARTIFACT_EXISTS",
                "SCOPE_VIOLATION"}:
        return 409
    if code.endswith("_NOT_FOUND") or code in {"JOURNEY_NOT_FOUND",
                                               "ARTIFACT_MISSING"}:
        return 404
    return 422
