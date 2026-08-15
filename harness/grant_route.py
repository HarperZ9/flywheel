"""Private durable proposal custody for exact one-use Journey grants."""
from __future__ import annotations
from dataclasses import asdict
from datetime import timedelta
import os, re, secrets
from pathlib import Path
from typing import Callable
from uuid import uuid4
from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json
from .evidence_public import (
    TransportError, admitted_root, error_response, exact_request, json_ref,
    parse_json, public_metadata, public_result, public_text, relative_ref,
)
from .journey_checks import OPERATION_REF_PATTERN
from .journey_lock import ExclusiveJourneyLock, JourneyLockBusy, fsync_directory
from .journey_service import JourneyService
from .journey_store import JourneyStore, JourneyStoreError
from .journey_types import STAGES
from .operation_grants import (
    GrantError, GrantRequest, GrantStore, _parse_time, _secure_owner_only,
    _utc_text, _validate_owner_ref,
)

ROUTE_PREFIX = "/api/grants/"
PROPOSAL_SCHEMA = "flywheel.grant-proposal/v1"
PROPOSAL_REF_PATTERN = re.compile(r"prp_[0-9a-f]{32}\Z")
_PREPARE_FIELDS = {
    "create": frozenset(("goal", "intake_ref", "client_request_id")),
    "append": frozenset(("journey_ref", "expected_event_head",
                         "client_request_id", "command")),
    "check": frozenset(("journey_ref", "expected_event_head", "client_request_id",
                        "claim_id", "oracle_id", "candidate_ref", "context_ref")),
    "cancel": frozenset(("journey_ref", "expected_event_head",
                         "client_request_id", "operation_ref")),
    "export": frozenset(("journey_ref", "expected_event_head",
                         "client_request_id", "packet_ref")),
}
_RECORD_FIELDS = frozenset((
    "schema", "proposal_ref", "planned_grant_ref", "owner_ref", "action",
    "request", "operation", "operation_body", "grant_request", "operation_ref",
    "expires_at", "state", "proposal_sha256",
))
def _service(owner_ref: str, state_root: Path,
             clock: Callable[[], str]) -> JourneyService:
    grants = GrantStore(state_root, clock=clock)
    return JourneyService(owner_ref=owner_ref, store=JourneyStore(state_root),
                          grants=grants, clock=clock)
def _artifact_root_ref(state_root: Path, evidence_root: Path) -> tuple[Path, str]:
    state = Path(state_root).resolve(strict=True)
    evidence = admitted_root(evidence_root)
    try:
        contained = os.path.commonpath((os.path.normcase(str(state)),
            os.path.normcase(str(evidence)))) == os.path.normcase(str(state))
        relative = evidence.relative_to(state).as_posix() if evidence != state else "."
    except (OSError, RuntimeError, ValueError):
        contained, relative = False, ""
    if not contained:
        raise TransportError(
            "INVALID_TRANSITION", "check artifact custody is unavailable", 409)
    return evidence, relative
def _append_operation(req: dict, service: JourneyService) -> tuple[str, dict]:
    command = req["command"]
    if type(command) is not dict or type(command.get("type")) is not str:
        raise TransportError("INVALID_TRANSITION", "Journey command is invalid", 422)
    kind = command["type"]
    expected = {"advance_stage": {"type"}, "record_claim": {"type", "claim"},
                "record_next_action": {"type", "next_action"}}.get(kind)
    if expected is None or set(command) != expected:
        raise TransportError("INVALID_TRANSITION", "Journey command is invalid", 422)
    public_metadata(command)
    if kind == "advance_stage":
        projection = service.resume(req["journey_ref"])
        try:
            operation = STAGES[STAGES.index(projection["stage"]) + 1]
        except (KeyError, ValueError, IndexError):
            raise TransportError(
                "INVALID_TRANSITION", "Journey transition is unavailable", 409) from None
        return operation, {}
    name = "claims" if kind == "record_claim" else "next_actions"
    item = command["claim"] if kind == "record_claim" else command["next_action"]
    if type(item) is not dict:
        raise TransportError("INVALID_TRANSITION", "Journey command is invalid", 422)
    return kind, {name: [item]}
def _check_operation(req: dict, service: JourneyService, state_root: Path,
                     evidence_root: Path, operation_ref: str) -> tuple[dict, tuple[str, ...]]:
    evidence, artifact_ref = _artifact_root_ref(state_root, evidence_root)
    journey = service.resume(req["journey_ref"])
    context_ref = relative_ref(req["context_ref"]).as_posix()
    candidate_ref = relative_ref(req["candidate_ref"]).as_posix()
    context = json_ref(evidence, context_ref)
    if context.get("candidate_ref") != candidate_ref:
        raise TransportError(
            "INVALID_TRANSITION", "check references do not match", 422)
    context = {**context, "_source_ref": context_ref}
    public_metadata(context)
    body = {
        "client_request_id": req["client_request_id"],
        "operation_ref": operation_ref,
        "journey_sha256": canonical_sha256(journey),
        "claim_id": public_text(req, "claim_id"),
        "oracle_id": public_text(req, "oracle_id"),
        "artifact_root_ref": artifact_ref, "candidate_ref": candidate_ref,
        "context_sha256": canonical_sha256(context),
    }
    return body, (artifact_ref, candidate_ref)
def _operation(action: str, req: dict, owner_ref: str, state_root: Path,
               evidence_root: Path, clock: Callable[[], str], operation_ref: str | None):
    service = _service(owner_ref, state_root, clock)
    if action == "create":
        intake = json_ref(admitted_root(evidence_root), req["intake_ref"])
        body = {"legacy_label": None, "goal": public_text(req, "goal"),
                "intake": intake, "occurred_at": clock()}
        return "intake", body, "journey.create", ("journey:create",), (req["intake_ref"],)
    if action == "append":
        operation, payload = _append_operation(req, service)
        body = {"occurred_at": clock(), "payload": payload}
        return operation, body, "journey.append", ("journey:append",), ()
    if action == "check":
        body, refs = _check_operation(
            req, service, state_root, evidence_root, operation_ref)
        return "check", body, "journey.check", ("journey:check",), refs
    if action == "cancel":
        if (type(req["operation_ref"]) is not str
                or OPERATION_REF_PATTERN.fullmatch(req["operation_ref"]) is None):
            raise TransportError("INVALID_TRANSITION", "operation is unavailable", 422)
        body = {"client_request_id": req["client_request_id"],
                "operation_ref": req["operation_ref"], "timeout_s": 5.0}
        return "cancel", body, "journey.cancel", ("journey:cancel",), ()
    relative_ref(req["packet_ref"])
    body = {"client_request_id": req["client_request_id"],
            "packet_ref": req["packet_ref"]}
    return "export", body, "journey.export", ("journey:export",), (req["packet_ref"],)
def _proposal_dir(state_root: Path, owner_ref: str) -> Path:
    _validate_owner_ref(owner_ref)
    state = Path(state_root)
    state.mkdir(parents=True, exist_ok=True)
    root = state / "grant-proposals"; root.mkdir(exist_ok=True)
    _secure_owner_only(root, directory=True)
    owner = root / owner_ref; owner.mkdir(exist_ok=True)
    _secure_owner_only(owner, directory=True)
    return owner
def _proposal_path(owner_dir: Path, proposal_ref: str) -> Path:
    if type(proposal_ref) is not str or PROPOSAL_REF_PATTERN.fullmatch(proposal_ref) is None:
        raise GrantError("PERMISSION_REQUIRED")
    return owner_dir / f"{canonical_sha256(proposal_ref)}.json"
def _digest(record: dict) -> str:
    return canonical_sha256({key: value for key, value in record.items()
                             if key != "proposal_sha256"})
def _request_from(value: dict) -> GrantRequest:
    try:
        exact = dict(value); exact["scopes"] = tuple(exact["scopes"])
        exact["data_refs"] = tuple(exact["data_refs"])
        request = GrantRequest(**exact)
        GrantStore._validate_request(request, allow_default_expiry=False)
        return request
    except (KeyError, TypeError, ValueError):
        raise GrantError("PERMISSION_DENIED") from None
def _validate_record(value: dict, owner_ref: str) -> dict:
    if (type(value) is not dict or set(value) != _RECORD_FIELDS
            or value.get("schema") != PROPOSAL_SCHEMA
            or value.get("owner_ref") != owner_ref
            or value.get("state") not in {"prepared", "approved"}
            or value.get("action") not in _PREPARE_FIELDS
            or value.get("proposal_sha256") != _digest(value)):
        raise GrantError("PERMISSION_DENIED")
    suffix = value["proposal_ref"][4:] if type(value.get("proposal_ref")) is str else ""
    if (PROPOSAL_REF_PATTERN.fullmatch(value.get("proposal_ref", "")) is None
            or value.get("planned_grant_ref") != f"gnt_{suffix}"
            or set(value.get("request", {})) != _PREPARE_FIELDS[value["action"]]):
        raise GrantError("PERMISSION_DENIED")
    public_metadata(value["request"]); public_metadata(value["operation_body"])
    _request_from(value["grant_request"])
    return value
def _read(owner_dir: Path, proposal_ref: str, owner_ref: str) -> dict:
    path = _proposal_path(owner_dir, proposal_ref)
    if not path.exists():
        raise GrantError("PERMISSION_REQUIRED")
    try:
        _secure_owner_only(path, directory=False)
        return _validate_record(strict_load_json(path.read_bytes()), owner_ref)
    except GrantError:
        raise
    except (OSError, TypeError, ValueError):
        raise GrantError("PERMISSION_DENIED") from None
def _replace(path: Path, value: dict) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            _secure_owner_only(temporary, directory=False)
            stream.write(canonical_bytes(value)); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path); _secure_owner_only(path, directory=False)
        with path.open("r+b") as stream: os.fsync(stream.fileno())
        fsync_directory(path.parent)
    finally:
        try: temporary.unlink()
        except FileNotFoundError: pass
def _prepare(action: str, req: dict, owner_ref: str, state_root: Path,
             evidence_root: Path, clock: Callable[[], str]) -> dict:
    public_metadata(req)
    suffix = secrets.token_hex(16)
    proposal_ref, grant_ref = f"prp_{suffix}", f"gnt_{suffix}"
    operation_ref = f"op_{secrets.token_hex(16)}" if action == "check" else None
    operation, body, tool, scopes, refs = _operation(
        action, req, owner_ref, state_root, evidence_root, clock, operation_ref)
    expiry = _utc_text(_parse_time(clock()) + timedelta(seconds=120))
    selector = None if action == "create" else req["journey_ref"]
    head = None if action == "create" else req["expected_event_head"]
    operation_value = {"owner_ref": owner_ref, "journey_ref": selector,
        "expected_event_head": head, "operation": operation, "body": body}
    grant = GrantRequest(owner_ref, selector, head, canonical_sha256(operation_value),
        tool, canonical_sha256(body), scopes, refs, expiry, proposal_ref)
    grant_value = asdict(grant); grant_value["scopes"], grant_value["data_refs"] = list(scopes), list(refs)
    record = {"schema": PROPOSAL_SCHEMA, "proposal_ref": proposal_ref,
        "planned_grant_ref": grant_ref, "owner_ref": owner_ref, "action": action,
        "request": req, "operation": operation, "operation_body": body,
        "grant_request": grant_value, "operation_ref": operation_ref,
        "expires_at": expiry, "state": "prepared"}
    record["proposal_sha256"] = _digest(record)
    owner_dir = _proposal_dir(state_root, owner_ref)
    with ExclusiveJourneyLock.acquire(owner_dir / ".lock"):
        _secure_owner_only(owner_dir / ".lock", directory=False)
        _replace(_proposal_path(owner_dir, proposal_ref), record)
    return {"schema": PROPOSAL_SCHEMA, "proposal_ref": proposal_ref,
        "planned_grant_ref": grant_ref, "action": action,
        "operation_sha256": grant.operation_sha256, "expires_at": expiry,
        **({"operation_ref": operation_ref} if operation_ref else {})}
def _approve(req: dict, owner_ref: str, state_root: Path,
             clock: Callable[[], str]) -> dict:
    owner_dir = _proposal_dir(state_root, owner_ref)
    with ExclusiveJourneyLock.acquire(owner_dir / ".lock"):
        _secure_owner_only(owner_dir / ".lock", directory=False)
        record = _read(owner_dir, req["proposal_ref"], owner_ref)
        if _parse_time(clock()) >= _parse_time(record["expires_at"]):
            raise GrantError("APPROVAL_EXPIRED")
        request = _request_from(record["grant_request"])
        issued = GrantStore(state_root, clock=clock).issue_exact(
            record["planned_grant_ref"], request, approved=True)
        if record["state"] != "approved":
            record["state"] = "approved"; record["proposal_sha256"] = _digest(record)
            _replace(_proposal_path(owner_dir, record["proposal_ref"]), record)
    return {"schema": "flywheel.operation-grant-approval/v1",
            "grant_ref": issued["grant_ref"], "expires_at": issued["expires_at"]}
def resolve_approved_grant(grant_ref: str, *, owner_ref: str, state_root: Path,
                           clock: Callable[[], str]) -> dict:
    suffix = grant_ref[4:] if type(grant_ref) is str and grant_ref.startswith("gnt_") else ""
    owner_dir = _proposal_dir(state_root, owner_ref)
    record = _read(owner_dir, f"prp_{suffix}", owner_ref)
    if (record["planned_grant_ref"] != grant_ref or record["state"] != "approved"):
        raise GrantError("PERMISSION_REQUIRED")
    if _parse_time(clock()) >= _parse_time(record["expires_at"]):
        raise GrantError("APPROVAL_EXPIRED")
    return {"action": record["action"], "request": record["request"],
        "operation": record["operation"], "operation_body": record["operation_body"],
        "operation_ref": record["operation_ref"],
        "grant_request": _request_from(record["grant_request"])}
def _mapped_error(exc: Exception) -> tuple[dict, int]:
    if isinstance(exc, TransportError): return error_response(exc)
    if isinstance(exc, GrantError):
        status = 403
        return error_response(TransportError(exc.code, "operation approval is unavailable", status))
    if isinstance(exc, JourneyStoreError):
        status = 404 if exc.code == "JOURNEY_NOT_FOUND" else 503 if exc.code == "STORE_BUSY" else 409
        return error_response(TransportError(exc.code, "Journey state is unavailable", status))
    return error_response(TransportError(
        "STORE_COMMIT_FAILED", "grant proposal custody failed", 500))
def grant_post(path: str, raw: bytes, *, owner_ref: str, state_root: Path,
               evidence_root: Path, clock: Callable[[], str]) -> tuple[dict, int]:
    """Prepare or approve one durable exact grant without dispatching work."""
    try:
        if type(path) is not str or not path.startswith(ROUTE_PREFIX):
            raise TransportError("NOT_FOUND", "grant route not found", 404)
        action_path, request = path[len(ROUTE_PREFIX):], parse_json(raw)
        if action_path == "approve-once":
            result = _approve(exact_request(request, {"proposal_ref"}),
                              owner_ref, state_root, clock)
        elif action_path.startswith("prepare/"):
            action = action_path.removeprefix("prepare/")
            if action not in _PREPARE_FIELDS or "/" in action:
                raise TransportError("NOT_FOUND", "grant route not found", 404)
            result = _prepare(action, exact_request(request, _PREPARE_FIELDS[action]),
                              owner_ref, state_root, evidence_root, clock)
        else:
            raise TransportError("NOT_FOUND", "grant route not found", 404)
        return public_result("grant", result), 200
    except (TransportError, GrantError, JourneyStoreError, Exception) as exc:
        return _mapped_error(exc)
