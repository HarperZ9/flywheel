"""Owner-scoped proposal inbox for reviewed gateway approvals."""
from __future__ import annotations
from pathlib import Path
from typing import Callable
from .evidence_json import canonical_bytes, canonical_sha256
from .evidence_public import exact_request
from .gateway_grant_index import (DECIDED_RECENT_SECONDS, query_proposal_index,
    read_limited_json, record_filename, replace_indexed_proposal)
from .gateway_operation import GatewayOperationError, canonicalize_operation, thaw_operation
from .gateway_operation_route import operation_ref_for
from .journey_lock import ExclusiveJourneyLock
from .journey_types import SHA256_PATTERN
from .operation_grants import GrantError, GrantStore, _parse_time, _secure_owner_only, _validate_owner_ref

CAPABILITIES_SCHEMA = "flywheel.gateway-grant-capabilities/v1"
CAPABILITIES_REQUEST_SCHEMA = "flywheel.gateway-grant-capabilities-request/v1"
LIST_REQUEST_SCHEMA = "flywheel.gateway-grant-list-request/v1"
LIST_SCHEMA = "flywheel.gateway-grant-list/v1"
LIST_ITEM_SCHEMA = "flywheel.gateway-grant-list-item/v1"
READ_REQUEST_SCHEMA = "flywheel.gateway-grant-read-request/v1"
READ_SCHEMA = "flywheel.gateway-grant-read/v1"
REVIEW_SCHEMA = "flywheel.gateway-grant-review/v1"
REVIEWED_APPROVAL_REQUEST_SCHEMA = "flywheel.gateway-grant-reviewed-approval-request/v1"
REJECT_REQUEST_SCHEMA = "flywheel.gateway-grant-reject-request/v1"
REJECTION_SCHEMA = "flywheel.gateway-grant-rejection/v1"
REVIEW_MAX_BYTES = 32_768
_STATES = {"pending", "recoverable", "decided_recent"}


def gateway_grant_inbox_post(route: str, body: dict, *, owner_ref: str,
                             state_root: Path, clock: Callable[[], str],
                             validate_record, proposal_response,
                             request_from_record, replace_record,
                             record_digest) -> tuple[dict, int]:
    if route == "capabilities":
        return _capabilities(body), 200
    if route == "list":
        return _list(body, owner_ref, state_root, clock, validate_record,
                     proposal_response, record_digest), 200
    if route == "read":
        return _read(body, owner_ref, state_root, clock, validate_record,
                     proposal_response, record_digest), 200
    if route == "approve-reviewed-once":
        return _approve_reviewed(body, owner_ref, state_root, clock,
                                 validate_record, request_from_record,
                                 replace_record, record_digest), 200
    if route == "reject":
        return _reject(body, owner_ref, state_root, clock, validate_record,
                       replace_record, record_digest), 200
    raise GatewayOperationError("NOT_FOUND")


def _capabilities(body: dict) -> dict:
    exact_request(body, {"schema"})
    if body.get("schema") != CAPABILITIES_REQUEST_SCHEMA:
        raise GatewayOperationError("INVALID_REQUEST")
    return {"schema": CAPABILITIES_SCHEMA, "proposal_list": True,
            "proposal_read": True, "reviewed_approval": True,
            "durable_reject": True, "review_max_bytes": REVIEW_MAX_BYTES}


def _owner_dir(state_root: Path, owner_ref: str) -> Path | None:
    _validate_owner_ref(owner_ref)
    root = Path(state_root) / "gateway-grant-proposals"
    owner = root / owner_ref
    if not owner.exists():
        return None
    _secure_owner_only(root, directory=True)
    _secure_owner_only(owner, directory=True)
    return owner


def _proposal_path(owner_dir: Path, proposal_ref: str) -> Path:
    return owner_dir / record_filename(proposal_ref)


def _load(owner_dir: Path | None, proposal_ref: str, owner_ref: str,
          validate_record) -> dict:
    if owner_dir is None:
        raise GrantError("PERMISSION_REQUIRED")
    path = _proposal_path(owner_dir, proposal_ref)
    if not path.exists():
        raise GrantError("PERMISSION_REQUIRED")
    _secure_owner_only(path, directory=False)
    try:
        return validate_record(read_limited_json(path), owner_ref)
    except Exception:
        raise GrantError("PERMISSION_DENIED") from None


def _list(body: dict, owner_ref: str, state_root: Path, clock, validate_record,
          proposal_response, record_digest) -> dict:
    exact_request(body, {"schema", "state", "limit", "cursor"},
                  optional={"state", "limit", "cursor"})
    state = body.get("state", "pending")
    limit = body.get("limit", 25)
    cursor = body.get("cursor")
    if (body.get("schema") != LIST_REQUEST_SCHEMA or state not in _STATES
            or type(limit) is not int or type(limit) is bool
            or not 1 <= limit <= 50):
        raise GatewayOperationError("INVALID_REQUEST")
    now = _parse_time(clock())
    owner_dir = _owner_dir(state_root, owner_ref)
    page = query_proposal_index(owner_dir, state, now, cursor, limit + 1)
    rows, record_reads, drift = [], 0, False
    for indexed in page["rows"]:
        record_reads += 1
        try:
            record = _load(owner_dir, indexed["proposal_ref"], owner_ref,
                           validate_record)
            if not _matches_index(record, indexed):
                raise GrantError("PERMISSION_DENIED")
        except GrantError:
            drift = True
            continue
        item = _item(record, owner_ref, now, proposal_response, record_digest)
        if _include(state, item):
            rows.append((item, indexed["cursor"]))
        if len(rows) > limit:
            break
    next_cursor = None
    if len(rows) > limit:
        next_cursor = rows[limit - 1][1]
        rows = rows[:limit]
    elif len(page["rows"]) == limit + 1:
        next_cursor = page["rows"][-1]["cursor"]
    recovery = page.get("recovery_required")
    complete = page["index_complete"] and not drift
    status = page["list_status"] if recovery else ("index_drift" if drift else page["list_status"])
    response = {"schema": LIST_SCHEMA, "server_time": clock(), "state": state,
                "items": [item for item, _cursor in rows],
                "next_cursor": next_cursor, "index_complete": complete,
                "list_status": "complete" if complete else status,
                "coverage_scope": page.get("coverage_scope", "maintained_index"),
                "recovery_required": recovery,
                "decided_recent_window_seconds": DECIDED_RECENT_SECONDS,
                "inspected_index_rows": page["inspected_index_rows"],
                "record_reads": record_reads}
    return response


def _read(body: dict, owner_ref: str, state_root: Path, clock, validate_record,
          proposal_response, record_digest) -> dict:
    exact_request(body, {"schema", "proposal_ref"})
    if body.get("schema") != READ_REQUEST_SCHEMA:
        raise GatewayOperationError("INVALID_REQUEST")
    record = _load(_owner_dir(state_root, owner_ref), body["proposal_ref"],
                   owner_ref, validate_record)
    item = _item(record, owner_ref, _parse_time(clock()), proposal_response,
                 record_digest)
    result = {**item, "schema": READ_SCHEMA, "server_time": clock()}
    if item["review_available"]:
        result["review"] = _review(record, owner_ref, record_digest)[0]
    else:
        result["unavailable_reason"] = "OPERATION_REVIEW_TOO_LARGE"
    return result


def _matches_index(record: dict, indexed: dict) -> bool:
    return (record["proposal_ref"] == indexed["proposal_ref"]
            and record["record_sha256"] == indexed["record_sha256"]
            and record["state"] == indexed["proposal_state"]
            and record["expires_at"] == indexed["expires_at"]
            and record_filename(record["proposal_ref"]) == indexed["record_file"])


def _item(record: dict, owner_ref: str, now, proposal_response,
          record_digest) -> dict:
    operation = canonicalize_operation(record["action"], record["operation"])
    review, reason = _review(record, owner_ref, record_digest)
    derived = _derived(record, now, review is not None)
    return {"schema": LIST_ITEM_SCHEMA, "proposal_ref": record["proposal_ref"],
            "planned_grant_ref": record["planned_grant_ref"],
            "proposal_state": record["state"], "derived_state": derived,
            "record_sha256": record["record_sha256"],
            "expires_at": record["expires_at"],
            "operation_ref": operation_ref_for(owner_ref,
                record["journey_ref"], record["client_request_id"]),
            "review_available": review is not None,
            **({"review_sha256": review["review_sha256"]} if review else {}),
            **({"unavailable_reason": reason} if reason else {}),
            "summary": proposal_response(record, operation)["summary"]}


def _review(record: dict, owner_ref: str, record_digest) -> tuple[dict | None, str | None]:
    operation = canonicalize_operation(record["action"], record["operation"])
    prepared = dict(record); prepared["state"] = "prepared"
    prepared["record_sha256"] = record_digest(prepared)
    unsigned = {"schema": REVIEW_SCHEMA,
                "proposal_ref": record["proposal_ref"],
                "planned_grant_ref": record["planned_grant_ref"],
                "record_sha256": prepared["record_sha256"],
                "operation_ref": operation_ref_for(owner_ref,
                    record["journey_ref"], record["client_request_id"]),
                "action": record["action"],
                "journey_ref": record["journey_ref"],
                "expected_event_head": record["expected_event_head"],
                "client_request_id": record["client_request_id"],
                "destination": dict(operation.destination),
                "tool": operation.tool, "scopes": list(operation.scopes),
                "data_refs": list(operation.data_refs),
                "credential_refs": list(operation.credential_refs),
                "execution_plan_sha256": record["execution_plan_sha256"],
                "operation_sha256": operation.operation_sha256,
                "arguments_sha256": operation.arguments_sha256,
                "operation": thaw_operation(operation.operation),
                "expires_at": record["expires_at"]}
    review = {**unsigned, "review_sha256": canonical_sha256(unsigned)}
    return (None, "OPERATION_REVIEW_TOO_LARGE") if len(
        canonical_bytes(review)) > REVIEW_MAX_BYTES else (review, None)


def _derived(record: dict, now, review_available: bool) -> str:
    if _parse_time(record["expires_at"]) <= now:
        return "expired"
    if record["state"] == "rejected":
        return "rejected"
    if record["state"] == "approved":
        return "approved_waiting_dispatch"
    return "pending" if review_available else "review_unavailable"


def _include(state: str, item: dict) -> bool:
    if state == "pending":
        return item["proposal_state"] == "prepared" and item["derived_state"] in {
            "pending", "review_unavailable"}
    if state == "recoverable":
        return item["derived_state"] in {
            "pending", "review_unavailable", "approved_waiting_dispatch"}
    return item["proposal_state"] in {"approved", "rejected"}


def _approve_reviewed(body: dict, owner_ref: str, state_root: Path, clock,
                      validate_record, request_from_record, replace_record,
                      record_digest) -> dict:
    exact_request(body, {"schema", "proposal_ref", "review_sha256"})
    if (body.get("schema") != REVIEWED_APPROVAL_REQUEST_SCHEMA
            or SHA256_PATTERN.fullmatch(body.get("review_sha256", "")) is None):
        raise GatewayOperationError("INVALID_REQUEST")
    owner_dir = _owner_dir(state_root, owner_ref)
    if owner_dir is None:
        raise GrantError("PERMISSION_REQUIRED")
    with ExclusiveJourneyLock.acquire(owner_dir / ".lock"):
        record = _load(owner_dir, body["proposal_ref"], owner_ref,
                       validate_record)
        if record["state"] == "rejected":
            raise GrantError("PERMISSION_DENIED")
        if _parse_time(clock()) >= _parse_time(record["expires_at"]):
            raise GrantError("APPROVAL_EXPIRED")
        review, _reason = _review(record, owner_ref, record_digest)
        if review is None or review["review_sha256"] != body["review_sha256"]:
            raise GrantError("PERMISSION_DENIED")
        issued = GrantStore(state_root, clock=clock).issue_exact(
            record["planned_grant_ref"], request_from_record(
                record["grant_request"]), approved=True)
        if record["state"] == "prepared":
            record["state"] = "approved"
            record["record_sha256"] = record_digest(record)
            replace_indexed_proposal(owner_dir, record, clock(),
                replace_record, _proposal_path(owner_dir, record["proposal_ref"]))
    return {"schema": "flywheel.operation-grant-approval/v1",
            "grant_ref": issued["grant_ref"], "expires_at": issued["expires_at"]}


def _reject(body: dict, owner_ref: str, state_root: Path, clock,
            validate_record, replace_record, record_digest) -> dict:
    exact_request(body, {"schema", "proposal_ref", "expected_record_sha256"})
    if (body.get("schema") != REJECT_REQUEST_SCHEMA or SHA256_PATTERN.fullmatch(
            body.get("expected_record_sha256", "")) is None):
        raise GatewayOperationError("INVALID_REQUEST")
    owner_dir = _owner_dir(state_root, owner_ref)
    if owner_dir is None:
        raise GrantError("PERMISSION_REQUIRED")
    with ExclusiveJourneyLock.acquire(owner_dir / ".lock"):
        record = _load(owner_dir, body["proposal_ref"], owner_ref,
                       validate_record)
        if record["state"] != "prepared":
            raise GatewayOperationError("INVALID_TRANSITION")
        if _parse_time(clock()) >= _parse_time(record["expires_at"]):
            raise GrantError("APPROVAL_EXPIRED")
        if record["record_sha256"] != body["expected_record_sha256"]:
            raise GatewayOperationError("INVALID_TRANSITION")
        record["state"] = "rejected"
        record["record_sha256"] = record_digest(record)
        replace_indexed_proposal(owner_dir, record, clock(),
            replace_record, _proposal_path(owner_dir, record["proposal_ref"]))
    return {"schema": REJECTION_SCHEMA, "proposal_ref": record["proposal_ref"],
            "proposal_state": "rejected",
            "record_sha256": record["record_sha256"]}
