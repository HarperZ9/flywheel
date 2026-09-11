"""Durable exact proposals for external gateway operations."""
from __future__ import annotations
from dataclasses import asdict, replace
from datetime import timedelta
from pathlib import Path
import re
import secrets
from typing import Callable
from .evidence_json import canonical_sha256, strict_load_json
from .evidence_public import TransportError, exact_request, parse_json
from .grant_route import _replace, _request_from
from .gateway_grant_errors import gateway_error_response
from .gateway_grant_index import replace_indexed_proposal as _write_indexed
from .gateway_grant_inbox import gateway_grant_inbox_post
from .gateway_operation import (AuthorizedOperation, GatewayOperationError, GRANTABLE_ACTIONS, PROPOSAL_REF_PATTERN,
    PROPOSAL_SCHEMA, REQUEST_SCHEMA, canonicalize_operation, thaw_operation)
from .gateway_envelope import parse_gateway_envelope
from .gateway_secret_boundary import validate_no_raw_secrets
from .gateway_provider_adapter import credential_slots, freeze_execution_plan
from .gateway_grant_summary import proposal_response as _proposal_response
from .gateway_agent_grant import validate_record_fields, record_binding, attach_binding, compare_binding
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
    state = Path(state_root); state.mkdir(parents=True, exist_ok=True)
    root = state / "gateway-grant-proposals"; root.mkdir(exist_ok=True)
    _secure_owner_only(root, directory=True)
    owner = root / owner_ref; owner.mkdir(exist_ok=True)
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
    if (not validate_record_fields(value, _RECORD_FIELDS)
            or value.get("schema") != PROPOSAL_SCHEMA
            or value.get("owner_ref") != owner_ref
            or value.get("state") not in {"prepared", "approved", "rejected"}
            or value.get("record_sha256") != _digest(value)):
        raise GrantError("PERMISSION_DENIED")
    proposal_ref = value.get("proposal_ref", "")
    suffix = proposal_ref[4:] if type(proposal_ref) is str else ""
    if (PROPOSAL_REF_PATTERN.fullmatch(proposal_ref) is None
            or value.get("planned_grant_ref") != f"gnt_{suffix}"):
        raise GrantError("PERMISSION_DENIED")
    operation = canonicalize_operation(value.get("action"), value.get("operation"))
    record_binding(value, operation)
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
def _validate_continuation_handoff(action: str, operation, *, owner_ref: str,
                                   journey_ref: str, state_root: Path,
                                   journey_events=None) -> None:
    if action == "agent.run" and "continuation" in operation.operation:
        from .continuation_agent_handoff import validate_continuation_agent_operation
        validate_continuation_agent_operation(
            operation, state_root, owner_ref=owner_ref,
            journey_ref=journey_ref, journey_events=journey_events)
def _prepare(action: str, body: dict, owner_ref: str, state_root: Path,
             clock: Callable[[], str], workspace_root: Path | None = None) -> dict:
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
    _validate_continuation_handoff(
        action, operation, owner_ref=owner_ref,
        journey_ref=body["journey_ref"], state_root=state_root)
    plan = freeze_execution_plan(operation, owner_ref=owner_ref, state_root=state_root, workspace_root=workspace_root)
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
        attach_binding(record, plan)
        request = _request(record, operation)
        GrantStore._validate_request(request, allow_default_expiry=False)
        grant_value = asdict(request)
        grant_value["scopes"] = list(request.scopes)
        grant_value["data_refs"] = list(request.data_refs)
        record["grant_request"] = grant_value
        record["record_sha256"] = _digest(record)
        owner_dir = _directory(state_root, owner_ref)
        with ExclusiveJourneyLock.acquire(owner_dir / ".lock"):
            _write_indexed(owner_dir, record, clock(), _replace, _path(owner_dir, proposal_ref))
    return _proposal_response(record, operation)
def _approve(body: dict, owner_ref: str, state_root: Path, clock: Callable[[], str]) -> dict:
    exact_request(body, {"proposal_ref"})
    if (type(body.get("proposal_ref")) is not str
            or PROPOSAL_REF_PATTERN.fullmatch(body["proposal_ref"]) is None):
        raise GatewayOperationError("INVALID_REQUEST")
    owner_dir = _directory(state_root, owner_ref)
    with ExclusiveJourneyLock.acquire(owner_dir / ".lock"):
        record = _read(owner_dir, body["proposal_ref"], owner_ref)
        if record["state"] == "rejected": raise GrantError("PERMISSION_DENIED")
        if _parse_time(clock()) >= _parse_time(record["expires_at"]):
            raise GrantError("APPROVAL_EXPIRED")
        issued = GrantStore(state_root, clock=clock).issue_exact(
            record["planned_grant_ref"], _request_from(record["grant_request"]),
            approved=True)
        if record["state"] != "approved":
            record["state"] = "approved"
            record["record_sha256"] = _digest(record)
            _write_indexed(owner_dir, record, clock(), _replace, _path(owner_dir, record["proposal_ref"]))
    return {"schema": "flywheel.operation-grant-approval/v1",
            "grant_ref": issued["grant_ref"], "expires_at": issued["expires_at"]}
def _authorize(envelope, *, owner_ref: str, state_root: Path, clock: Callable[[], str], workspace_root: Path | None = None) -> AuthorizedOperation:
    action = envelope.action
    operation = envelope.operation
    plan = freeze_execution_plan(operation, owner_ref=owner_ref, state_root=state_root, workspace_root=workspace_root)
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
        head = store._read_head(journey_dir)
        if head is None:
            raise JourneyStoreError("JOURNEY_NOT_FOUND")
        events = store._events_at_head(journey_dir, head)
        if head["event_head_sha256"] != body.get("expected_event_head"):
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
                    or record["planned_grant_ref"] != body.get("grant_ref")):
                raise GatewayOperationError("PERMISSION_DENIED")
            compare_binding(record, plan)
            if record["execution_plan_sha256"] != plan.digest:
                raise GatewayOperationError("PERMISSION_DENIED")
            request = _request_from(record["grant_request"])
            if request != _request(record, operation):
                raise GatewayOperationError("PERMISSION_DENIED")
            _validate_continuation_handoff(
                action, operation, owner_ref=owner_ref,
                journey_ref=body["journey_ref"], state_root=state_root,
                journey_events=events)
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
        clock: Callable[[], str], workspace_root: Path | None = None) -> AuthorizedOperation:
    return authorize_gateway_envelope(parse_gateway_envelope(action, raw), owner_ref=owner_ref, state_root=state_root, clock=clock, workspace_root=workspace_root)
def authorize_gateway_envelope(envelope, *, owner_ref: str, state_root: Path,
        clock: Callable[[], str], workspace_root: Path | None = None) -> AuthorizedOperation:
    try:
        return _authorize(envelope, owner_ref=owner_ref,
                          state_root=state_root, clock=clock, workspace_root=workspace_root)
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
def gateway_grant_post(path: str, raw: bytes, *, owner_ref: str, state_root: Path, clock: Callable[[], str], run_root: Path | None = None, workspace_root: Path | None = None) -> tuple[dict, int]:
    """Prepare or approve without dispatching an external operation."""
    try:
        if not path.startswith(ROUTE_PREFIX): raise GatewayOperationError("NOT_FOUND")
        route, body = path[len(ROUTE_PREFIX):], parse_json(raw)
        if route in {"capabilities", "list", "read", "approve-reviewed-once", "reject"}:
            return gateway_grant_inbox_post(route, body, owner_ref=owner_ref, state_root=state_root, clock=clock, validate_record=_validate_record, proposal_response=_proposal_response, request_from_record=_request_from, replace_record=_replace, record_digest=_digest)
        if route == "approve-once":
            return _approve(body, owner_ref, state_root, clock), 200
        if route.startswith("bulletin-media-") and run_root is None: raise GatewayOperationError("INVALID_REQUEST")
        if route == "bulletin-media-runs":
            from .outcome_bulletin_media_route import runs_body as _rb; return _rb(body, run_root=run_root), 200
        if route == "bulletin-media-artifacts":
            from .outcome_bulletin_media_route import artifacts_body as _ab; return _ab(body, run_root=run_root), 200
        if route == "bulletin-media-preview":
            from .outcome_bulletin_media_route import prepared_preview_body as _mp; return _mp(body, state_root=state_root, run_root=run_root, owner_ref=owner_ref, prepare=lambda req: _prepare("lane.call", req, owner_ref, state_root, clock)), 200
        if route == "bulletin-media-preview-bytes":
            from .outcome_bulletin_media_route import preview_bytes_body as _pb; owner_dir = _directory(state_root, owner_ref); return _pb(body, state_root=state_root, owner_ref=owner_ref, clock=clock, load_record=lambda ref: _read(owner_dir, ref, owner_ref)), 200
        if not route.startswith("prepare/") or "/" in route[8:]: raise GatewayOperationError("NOT_FOUND")
        action = route[8:]
        if action not in GRANTABLE_ACTIONS: raise GatewayOperationError("NOT_FOUND")
        return _prepare(action, body, owner_ref, state_root, clock, workspace_root), 200
    except (TransportError, GatewayOperationError, GrantError, JourneyLockBusy, JourneyStoreError, OSError, ValueError) as exc:
        return gateway_error_response(exc)
