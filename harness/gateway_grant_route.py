"""Durable exact proposals for external gateway operations."""
from __future__ import annotations
from dataclasses import asdict, replace
from datetime import timedelta
from pathlib import Path
import re
import secrets
from typing import Callable
from .evidence_json import canonical_sha256, strict_load_json
from .evidence_public import TransportError, error_response, exact_request, parse_json
from .grant_route import _replace, _request_from
from .gateway_operation import (AuthorizedOperation, GatewayOperationError, PROPOSAL_REF_PATTERN,
    PROPOSAL_SCHEMA, REQUEST_SCHEMA, canonicalize_operation, thaw_operation)
from .gateway_envelope import parse_gateway_envelope
from .gateway_secret_boundary import validate_no_raw_secrets
from .gateway_provider_adapter import credential_slots, freeze_execution_plan
from .journey_lock import ExclusiveJourneyLock, JourneyLockBusy
from .journey_store import JourneyStore, JourneyStoreError
from .journey_types import JOURNEY_REF_PATTERN, SHA256_PATTERN
from .operation_grants import (GrantError, GrantRequest, GrantStore, _parse_time, _secure_owner_only, _utc_text, _validate_owner_ref)
ROUTE_PREFIX = "/api/gateway-grants/"
_BASE = {"schema", "journey_ref", "expected_event_head", "client_request_id"}
_RECORD_FIELDS = {"schema", "proposal_ref", "planned_grant_ref", "owner_ref", "action",
    "journey_ref", "expected_event_head", "client_request_id", "operation",
    "execution_plan_sha256", "grant_request", "expires_at", "state",
    "record_sha256"}
def _directory(state_root: Path, owner_ref: str) -> Path:
    _validate_owner_ref(owner_ref)
    state = Path(state_root)
    state.mkdir(parents=True, exist_ok=True)
    root = state / "gateway-grant-proposals"
    root.mkdir(exist_ok=True)
    _secure_owner_only(root, directory=True)
    owner = root / owner_ref
    owner.mkdir(exist_ok=True)
    _secure_owner_only(owner, directory=True)
    return owner
def _path(owner_dir: Path, proposal_ref: str) -> Path:
    if (type(proposal_ref) is not str
            or PROPOSAL_REF_PATTERN.fullmatch(proposal_ref) is None):
        raise GrantError("PERMISSION_REQUIRED")
    return owner_dir / f"{canonical_sha256(proposal_ref)}.json"
def _digest(record: dict) -> str:
    return canonical_sha256({key: value for key, value in record.items()
                             if key != "record_sha256"})
def _validate_record(value: object, owner_ref: str) -> dict:
    if (type(value) is not dict or set(value) != _RECORD_FIELDS
            or value.get("schema") != PROPOSAL_SCHEMA
            or value.get("owner_ref") != owner_ref
            or value.get("state") not in {"prepared", "approved"}
            or value.get("record_sha256") != _digest(value)):
        raise GrantError("PERMISSION_DENIED")
    proposal_ref = value.get("proposal_ref", "")
    suffix = proposal_ref[4:] if type(proposal_ref) is str else ""
    if (PROPOSAL_REF_PATTERN.fullmatch(proposal_ref) is None
            or value.get("planned_grant_ref") != f"gnt_{suffix}"):
        raise GrantError("PERMISSION_DENIED")
    operation = canonicalize_operation(value.get("action"), value.get("operation"))
    request = _request_from(value.get("grant_request"))
    if request != _request(value, operation):
        raise GrantError("PERMISSION_DENIED")
    return value
def _read(owner_dir: Path, proposal_ref: str, owner_ref: str) -> dict:
    path = _path(owner_dir, proposal_ref)
    if not path.exists():
        raise GrantError("PERMISSION_REQUIRED")
    try:
        _secure_owner_only(path, directory=False)
        return _validate_record(strict_load_json(path.read_bytes()), owner_ref)
    except (GatewayOperationError, GrantError):
        raise GrantError("PERMISSION_DENIED") from None
    except (OSError, TypeError, ValueError):
        raise GrantError("PERMISSION_DENIED") from None
def _request(record: dict, operation) -> GrantRequest:
    return GrantRequest(
        record["owner_ref"], record["journey_ref"],
        record["expected_event_head"], canonical_sha256({
            "operation_sha256": operation.operation_sha256,
            "execution_plan_sha256": record["execution_plan_sha256"]}),
        operation.tool, operation.arguments_sha256, operation.scopes,
        operation.data_refs, record["expires_at"], record["proposal_ref"],
    )
def _current_head(store: JourneyStore, owner_ref: str, journey_ref: str) -> str:
    store._validate_selector(owner_ref, journey_ref)
    journey_dir = store._journey_dir(owner_ref, journey_ref)
    if not journey_dir.exists():
        raise JourneyStoreError("JOURNEY_NOT_FOUND")
    head = store._read_head(journey_dir)
    if head is None:
        raise JourneyStoreError("JOURNEY_NOT_FOUND")
    store._events_at_head(journey_dir, head)
    return head["event_head_sha256"]
def _proposal_response(record: dict, operation) -> dict:
    summary = {
        "schema": "flywheel.gateway-grant-summary/v1", "action": record["action"],
        "journey_ref": record["journey_ref"],
        "expected_event_head": record["expected_event_head"],
        "destination": dict(operation.destination), "tool": operation.tool,
        "operation_sha256": operation.operation_sha256,
        "arguments_sha256": operation.arguments_sha256,
        "scopes": list(operation.scopes), "data_refs": list(operation.data_refs),
        "credential_refs": list(operation.credential_refs),
        "effect": "one dispatch after approval", "expires_at": record["expires_at"],
    }
    return {
        "schema": PROPOSAL_SCHEMA, "proposal_ref": record["proposal_ref"],
        "planned_grant_ref": record["planned_grant_ref"],
        "action": record["action"], "journey_ref": record["journey_ref"],
        "expected_event_head": record["expected_event_head"],
        "client_request_id": record["client_request_id"], "tool": operation.tool,
        "destination": dict(operation.destination),
        "operation_sha256": operation.operation_sha256,
        "arguments_sha256": operation.arguments_sha256,
        "scopes": list(operation.scopes), "data_refs": list(operation.data_refs),
        "credential_refs": list(operation.credential_refs),
        "expires_at": record["expires_at"], "summary": summary,
    }
def _prepare(action: str, body: dict, owner_ref: str, state_root: Path,
             clock: Callable[[], str]) -> dict:
    exact_request(body, _BASE | {"operation"})
    if (body.get("schema") != REQUEST_SCHEMA
            or JOURNEY_REF_PATTERN.fullmatch(body.get("journey_ref", "")) is None
            or SHA256_PATTERN.fullmatch(
                body.get("expected_event_head", "")) is None
            or type(body.get("client_request_id")) is not str
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}",
                            body["client_request_id"]) is None):
        raise GatewayOperationError("INVALID_REQUEST")
    validate_no_raw_secrets(body)
    operation = canonicalize_operation(action, body["operation"])
    plan = freeze_execution_plan(operation, owner_ref=owner_ref, state_root=state_root)
    credential_slots(operation, owner_ref, state_root, plan=plan)
    store = JourneyStore(state_root)
    journey_dir = store._journey_dir(owner_ref, body["journey_ref"])
    with ExclusiveJourneyLock.acquire(journey_dir / ".lock"):
        if _current_head(store, owner_ref, body["journey_ref"]) != body[
                "expected_event_head"]:
            raise GatewayOperationError("HEAD_CONFLICT")
        suffix = secrets.token_hex(16)
        proposal_ref, grant_ref = f"prp_{suffix}", f"gnt_{suffix}"
        expires = _utc_text(_parse_time(clock()) + timedelta(seconds=120))
        record = {
            "schema": PROPOSAL_SCHEMA, "proposal_ref": proposal_ref,
            "planned_grant_ref": grant_ref, "owner_ref": owner_ref,
            "action": action, "journey_ref": body["journey_ref"],
            "expected_event_head": body["expected_event_head"],
            "client_request_id": body["client_request_id"],
            "operation": thaw_operation(operation.operation),
            "execution_plan_sha256": plan.digest,
            "expires_at": expires, "state": "prepared",
        }
        request = _request(record, operation)
        GrantStore._validate_request(request, allow_default_expiry=False)
        grant_value = asdict(request)
        grant_value["scopes"] = list(request.scopes)
        grant_value["data_refs"] = list(request.data_refs)
        record["grant_request"] = grant_value
        record["record_sha256"] = _digest(record)
        owner_dir = _directory(state_root, owner_ref)
        with ExclusiveJourneyLock.acquire(owner_dir / ".lock"):
            _replace(_path(owner_dir, proposal_ref), record)
    return _proposal_response(record, operation)
def _approve(body: dict, owner_ref: str, state_root: Path,
             clock: Callable[[], str]) -> dict:
    exact_request(body, {"proposal_ref"})
    if (type(body.get("proposal_ref")) is not str
            or PROPOSAL_REF_PATTERN.fullmatch(body["proposal_ref"]) is None):
        raise GatewayOperationError("INVALID_REQUEST")
    owner_dir = _directory(state_root, owner_ref)
    with ExclusiveJourneyLock.acquire(owner_dir / ".lock"):
        record = _read(owner_dir, body["proposal_ref"], owner_ref)
        if _parse_time(clock()) >= _parse_time(record["expires_at"]):
            raise GrantError("APPROVAL_EXPIRED")
        issued = GrantStore(state_root, clock=clock).issue_exact(
            record["planned_grant_ref"], _request_from(record["grant_request"]),
            approved=True)
        if record["state"] != "approved":
            record["state"] = "approved"
            record["record_sha256"] = _digest(record)
            _replace(_path(owner_dir, record["proposal_ref"]), record)
    return {"schema": "flywheel.operation-grant-approval/v1",
            "grant_ref": issued["grant_ref"], "expires_at": issued["expires_at"]}
def _authorize(envelope, *, owner_ref: str, state_root: Path,
               clock: Callable[[], str]) -> AuthorizedOperation:
    action = envelope.action
    operation = envelope.operation
    plan = freeze_execution_plan(operation, owner_ref=owner_ref, state_root=state_root)
    credential_slots(operation, owner_ref, state_root, plan=plan)
    body = {"journey_ref": envelope.journey_ref,
            "expected_event_head": envelope.expected_event_head,
            "client_request_id": envelope.client_request_id,
            "grant_ref": envelope.grant_ref}
    owner_dir = _directory(state_root, owner_ref)
    proposal_ref = "prp_" + str(body.get("grant_ref", ""))[4:]
    store = JourneyStore(state_root)
    journey_dir = store._journey_dir(owner_ref, body.get("journey_ref"))
    with ExclusiveJourneyLock.acquire(journey_dir / ".lock"):
        if _current_head(store, owner_ref, body.get("journey_ref")) != body.get(
                "expected_event_head"):
            raise GatewayOperationError("HEAD_CONFLICT")
        with ExclusiveJourneyLock.acquire(owner_dir / ".lock"):
            record = _read(owner_dir, proposal_ref, owner_ref)
            if (record["state"] != "approved" or record["action"] != action
                    or record["journey_ref"] != body.get("journey_ref")
                    or record["expected_event_head"] != body.get(
                        "expected_event_head")
                    or record["client_request_id"] != body.get(
                        "client_request_id")
                    or record["operation"] != thaw_operation(operation.operation)
                    or record["execution_plan_sha256"] != plan.digest
                    or record["planned_grant_ref"] != body.get("grant_ref")):
                raise GatewayOperationError("PERMISSION_DENIED")
            request = _request_from(record["grant_request"])
            if request != _request(record, operation):
                raise GatewayOperationError("PERMISSION_DENIED")
            if action == "plan.run":
                from .plan_run_store import verify_plan_run
                verified = verify_plan_run(thaw_operation(operation.operation)["binding"],
                    owner_ref=owner_ref, state_root=state_root)
                plan = replace(plan, verified_plan=verified)
            GrantStore(state_root, clock=clock).consume(
                body["grant_ref"], request, now=clock())
    return AuthorizedOperation(
        operation.action, operation.tool, operation.destination,
        operation.operation,
        operation.operation_sha256, operation.arguments_sha256,
        operation.scopes, operation.data_refs, operation.credential_refs,
        owner_ref, record["journey_ref"], record["expected_event_head"],
        record["client_request_id"], record["planned_grant_ref"],
        record["expires_at"], plan,
    )
def authorize_gateway_operation(
        action: str, raw: bytes, *, owner_ref: str, state_root: Path,
        clock: Callable[[], str]) -> AuthorizedOperation:
    return authorize_gateway_envelope(parse_gateway_envelope(action, raw), owner_ref=owner_ref, state_root=state_root, clock=clock)
def authorize_gateway_envelope(envelope, *, owner_ref: str, state_root: Path,
        clock: Callable[[], str]) -> AuthorizedOperation:
    try:
        return _authorize(envelope, owner_ref=owner_ref,
                          state_root=state_root, clock=clock)
    except GatewayOperationError:
        raise
    except GrantError as exc:
        raise GatewayOperationError(exc.code) from None
    except JourneyLockBusy:
        raise GatewayOperationError("STORE_BUSY") from None
    except JourneyStoreError as exc:
        code = "PERMISSION_REQUIRED" if exc.code == "JOURNEY_NOT_FOUND" else exc.code
        raise GatewayOperationError(code) from None
    except (TransportError, OSError, TypeError, ValueError):
        raise GatewayOperationError("INVALID_REQUEST") from None
def gateway_error_response(exc: Exception) -> tuple[dict, int]:
    code = getattr(exc, "code", "STORE_COMMIT_FAILED")
    if isinstance(exc, TransportError):
        code = "INVALID_REQUEST"
    elif isinstance(exc, JourneyLockBusy):
        code = "STORE_BUSY"
    elif isinstance(exc, JourneyStoreError) and code == "JOURNEY_NOT_FOUND":
        code = "PERMISSION_REQUIRED"
    errors = {
        "INVALID_REQUEST": (422, "gateway operation is invalid"),
        "AUTH_REQUIRED": (401, "gateway authentication is required"),
        "PERMISSION_REQUIRED": (403, "gateway operation approval is required"),
        "PERMISSION_DENIED": (403, "gateway operation approval is invalid"),
        "APPROVAL_EXPIRED": (403, "gateway operation approval expired"),
        "NOT_FOUND": (404, "gateway operation was not found"),
        "HEAD_CONFLICT": (409, "Journey head changed"),
        "PLAN_BINDING_DRIFT": (409, "plan run does not match its forged contract"),
        "IDEMPOTENCY_MISMATCH": (409, "operation request conflicts with its prior use"),
        "INVALID_TRANSITION": (409, "operation state does not allow this action"),
        "CANCEL_UNAVAILABLE": (409, "operation cancellation is unavailable"),
        "STORE_BUSY": (503, "operation store is busy"),
        "STORE_COMMIT_FAILED": (500, "operation state could not be committed"),
        "EXTERNAL_ACTION_FAILED": (502, "authorized external action failed")}
    code = code if code in errors else "STORE_COMMIT_FAILED"
    status, message = errors[code]
    return error_response(TransportError(code, message, status))
def gateway_grant_post(
        path: str, raw: bytes, *, owner_ref: str, state_root: Path,
        clock: Callable[[], str]) -> tuple[dict, int]:
    """Prepare or approve without dispatching an external operation."""
    try:
        if not path.startswith(ROUTE_PREFIX):
            raise GatewayOperationError("NOT_FOUND")
        route, body = path[len(ROUTE_PREFIX):], parse_json(raw)
        if route == "approve-once":
            return _approve(body, owner_ref, state_root, clock), 200
        if not route.startswith("prepare/") or "/" in route[8:]:
            raise GatewayOperationError("NOT_FOUND")
        action = route[8:]
        if action not in {"chat.complete", "agent.run", "workflow.run",
                "plugin.probe", "plugin.call", "plugin.register",
                "plugin.toggle", "plugin.remove", "marketplace.install",
                "marketplace.add", "marketplace.remove", "operation.cancel",
                "plan.run"}:
            raise GatewayOperationError("NOT_FOUND")
        return _prepare(action, body, owner_ref, state_root, clock), 200
    except (TransportError, GatewayOperationError, GrantError,
            JourneyLockBusy, JourneyStoreError, OSError, ValueError) as exc:
        return gateway_error_response(exc)
