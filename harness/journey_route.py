"""Authenticated-owner transport for durable Evidence Journey v2 custody."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
from pathlib import Path
from typing import Callable

from .evidence_json import canonical_sha256
from .evidence_public import (
    TransportError, error_response, exact_request, json_ref_bytes, parse_json,
    public_metadata, public_result, relative_ref,
)
from .grant_route import _artifact_root_ref, resolve_approved_grant
from .journey_checks import CheckCommand, JourneyCheckService
from .journey_export import JourneyExportService
from .journey_projection import project_lens
from .journey_service import JourneyService
from .journey_store import JourneyStore, JourneyStoreError
from .operation_grants import GrantError, GrantStore
from .operation_supervisor import OperationSupervisor

ROUTE_PREFIX = "/api/journeys/"
ACK_SCHEMA = "flywheel.evidence-journey-mutation-ack/v2"
LIST_SCHEMA = "flywheel.evidence-journey-list/v2"
_FIELDS = {
    "create": frozenset(("goal", "intake_ref", "client_request_id", "grant_ref")),
    "list": frozenset(), "resume": frozenset(("journey_ref", "lens")),
    "append": frozenset(("journey_ref", "expected_event_head",
                         "client_request_id", "grant_ref", "command")),
    "check": frozenset(("journey_ref", "expected_event_head", "client_request_id",
                        "grant_ref", "claim_id", "oracle_id", "candidate_ref",
                        "context_ref")),
    "cancel": frozenset(("journey_ref", "expected_event_head",
                         "client_request_id", "grant_ref", "operation_ref")),
    "export": frozenset(("journey_ref", "expected_event_head",
                         "client_request_id", "grant_ref", "packet_ref")),
}


def _service(owner_ref: str, state_root: Path,
             clock: Callable[[], str]) -> JourneyService:
    return JourneyService(
        owner_ref=owner_ref, store=JourneyStore(state_root),
        grants=GrantStore(state_root, clock=clock), clock=clock)


def _ack(value, **extra) -> dict:
    return {"schema": ACK_SCHEMA, **asdict(value), **extra}


def _resume(req: dict, service: JourneyService) -> dict:
    lens = req["lens"]
    if type(lens) is not str or lens.lower() not in {"rescue", "diagnose", "verify"}:
        raise TransportError(
            "INVALID_TRANSITION", "Journey lens is unavailable", 422)
    return project_lens(service.resume(req["journey_ref"]), lens)


def _approved(action: str, req: dict, owner_ref: str, state_root: Path,
              clock: Callable[[], str]) -> dict:
    approved = resolve_approved_grant(
        req["grant_ref"], owner_ref=owner_ref, state_root=state_root, clock=clock)
    public_request = {key: value for key, value in req.items() if key != "grant_ref"}
    if approved["action"] != action or approved["request"] != public_request:
        raise GrantError("PERMISSION_DENIED")
    return approved


def _create(req: dict, service: JourneyService, approved: dict) -> dict:
    ack = service.create(
        client_request_id=req["client_request_id"],
        body=approved["operation_body"], grant_ref=req["grant_ref"],
        grant_request=approved["grant_request"])
    return _ack(ack)


def _append(req: dict, service: JourneyService, approved: dict) -> dict:
    ack = service.append(
        journey_ref=req["journey_ref"],
        expected_event_head=req["expected_event_head"],
        client_request_id=req["client_request_id"],
        operation=approved["operation"], body=approved["operation_body"],
        grant_ref=req["grant_ref"], grant_request=approved["grant_request"])
    return _ack(ack)


def _check_context(req: dict, approved: dict, state_root: Path,
                   evidence_root: Path) -> tuple[dict, dict, str]:
    evidence, artifact_ref = _artifact_root_ref(state_root, evidence_root)
    context_ref, candidate_ref = relative_ref(req["context_ref"]).as_posix(), relative_ref(req["candidate_ref"]).as_posix()
    context, context_bytes = json_ref_bytes(evidence, context_ref)
    if context.get("candidate_ref") != candidate_ref:
        raise GrantError("PERMISSION_DENIED")
    context = {**context, "_source_ref": context_ref}
    public_metadata(context)
    body = approved["operation_body"]
    if (body.get("context_sha256") != canonical_sha256(context)
            or body.get("context_bytes_sha256") != hashlib.sha256(context_bytes).hexdigest()
            or body.get("artifact_root_ref") != artifact_ref
            or body.get("candidate_ref") != candidate_ref):
        raise GrantError("PERMISSION_DENIED")
    return context, body, artifact_ref


def _check(req: dict, service: JourneyService, approved: dict,
           state_root: Path, evidence_root: Path) -> dict:
    context, body, artifact_ref = _check_context(
        req, approved, state_root, evidence_root)
    journey = service.resume(req["journey_ref"])
    checks = JourneyCheckService(journey=service)
    if (body.get("journey_sha256") != canonical_sha256(journey)
            and not checks._history(approved["operation_ref"], req["journey_ref"])):
        raise GrantError("PERMISSION_DENIED")
    command = CheckCommand(
        owner_ref=service.owner_ref, journey_ref=req["journey_ref"],
        expected_event_head=req["expected_event_head"],
        client_request_id=req["client_request_id"],
        operation_ref=approved["operation_ref"], grant_ref=req["grant_ref"],
        grant_request=approved["grant_request"], journey=journey,
        claim_id=req["claim_id"], oracle_id=req["oracle_id"],
        candidate_ref=body["candidate_ref"], context=context,
        context_bytes_sha256=body["context_bytes_sha256"],
        artifact_root_ref=artifact_ref, journey_sha256=body["journey_sha256"])
    ack = checks.request(command)
    return _ack(ack, operation_ref=approved["operation_ref"],
                state=checks.state(approved["operation_ref"]))


def _cancel(req: dict, service: JourneyService, approved: dict) -> dict:
    checks = JourneyCheckService(journey=service)
    supervisor = OperationSupervisor(
        check_service=checks, grant_request=lambda _ref: approved["grant_request"])
    result = supervisor.request_cancel(
        owner_ref=service.owner_ref, journey_ref=req["journey_ref"],
        expected_event_head=req["expected_event_head"],
        client_request_id=req["client_request_id"],
        operation_ref=req["operation_ref"], grant_ref=req["grant_ref"],
        timeout_s=approved["operation_body"]["timeout_s"])
    if result.get("code") == "CANCEL_UNAVAILABLE":
        raise TransportError(
            "CANCEL_UNAVAILABLE", "operation cancellation is unavailable", 409)
    return result


def _export(req: dict, service: JourneyService, approved: dict,
            state_root: Path, evidence_root: Path) -> dict:
    _, artifact_ref = _artifact_root_ref(state_root, evidence_root)
    return JourneyExportService(
        journey=service, artifact_root_ref=artifact_ref).export(
        journey_ref=req["journey_ref"],
        expected_event_head=req["expected_event_head"],
        client_request_id=req["client_request_id"], packet_ref=req["packet_ref"],
        grant_ref=req["grant_ref"], grant_request=approved["grant_request"],
        body=approved["operation_body"])


def _mapped_error(exc: Exception) -> tuple[dict, int]:
    if isinstance(exc, TransportError):
        return error_response(exc)
    if isinstance(exc, GrantError):
        status = 503 if exc.code == "STORE_BUSY" else 403
        return error_response(TransportError(
            exc.code, "operation approval is unavailable", status))
    if isinstance(exc, JourneyStoreError):
        statuses = {"JOURNEY_NOT_FOUND": 404, "HEAD_CONFLICT": 409,
            "IDEMPOTENCY_MISMATCH": 409, "INVALID_TRANSITION": 409,
            "STORE_BUSY": 503, "STORE_COMMIT_FAILED": 500,
            "VERSION_MISMATCH": 409}
        return error_response(TransportError(
            exc.code, "Journey state is unavailable", statuses.get(exc.code, 500)))
    if isinstance(exc, ValueError) and "journey_ref" in str(exc):
        return error_response(TransportError(
            "INVALID_JOURNEY_REF", "Journey reference is invalid", 422))
    return error_response(TransportError(
        "STORE_COMMIT_FAILED", "Journey operation failed", 500))


def journey_post(path: str, raw: bytes, *, owner_ref: str, state_root: Path,
                 evidence_root: Path,
                 clock: Callable[[], str]) -> tuple[dict, int]:
    """Execute one owner-scoped durable action without external dispatch."""
    try:
        if type(path) is not str or not path.startswith(ROUTE_PREFIX):
            raise TransportError("NOT_FOUND", "Journey route not found", 404)
        action = path[len(ROUTE_PREFIX):]
        if action not in _FIELDS or "/" in action:
            raise TransportError("NOT_FOUND", "Journey route not found", 404)
        req = exact_request(parse_json(raw), _FIELDS[action])
        service = _service(owner_ref, state_root, clock)
        if action == "list":
            result = {"schema": LIST_SCHEMA, "journeys": service.list()}
        elif action == "resume":
            result = _resume(req, service)
        else:
            approved = _approved(action, req, owner_ref, state_root, clock)
            if action == "create": result = _create(req, service, approved)
            elif action == "append": result = _append(req, service, approved)
            elif action == "check":
                result = _check(req, service, approved, state_root, evidence_root)
            elif action == "cancel": result = _cancel(req, service, approved)
            else: result = _export(
                req, service, approved, state_root, evidence_root)
        return public_result(action, result), 200
    except (TransportError, GrantError, JourneyStoreError, Exception) as exc:
        return _mapped_error(exc)
