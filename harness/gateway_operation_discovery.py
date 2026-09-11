"""Bounded owner/Journey discovery over the existing immutable operation history."""
from __future__ import annotations

import base64
import re
from urllib.parse import parse_qs

from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json
from .gateway_operation import GatewayOperationError
from .gateway_operation_recovery import LIFECYCLE, history_state, validate_history
from .journey_projection import reduce_events
from .journey_store import HEAD_SCHEMA
from .journey_types import JOURNEY_REF_PATTERN, SHA256_PATTERN, validate_event
from .operation_grants import OWNER_REF_PATTERN
from .private_artifact_fs import NOT_FOUND, PrivateArtifactError, open_artifact_root

SCHEMA = "flywheel.gateway-operation-list/v1"
MAX_EVENTS, MAX_FILE_BYTES, MAX_TOTAL_BYTES = 4096, 1048576, 16777216
_CURSOR_FIELDS = {"owner_sha256", "journey_ref", "head", "sequence", "offset"}


def _require(condition, code="STORE_COMMIT_FAILED"):
    if not condition:
        raise GatewayOperationError(code)


def _query(query, owner):
    _require(type(owner) is str and OWNER_REF_PATTERN.fullmatch(owner), "NOT_FOUND")
    _require(type(query) is str and len(query) <= 2048, "INVALID_REQUEST")
    try:
        values = parse_qs(query, keep_blank_values=True, strict_parsing=True, max_num_fields=3)
        _require("journey_ref" in values and not set(values) - {"journey_ref", "limit", "cursor"}
                 and all(len(v) == 1 for v in values.values()), "INVALID_REQUEST")
        journey = values["journey_ref"][0]
        limit = values.get("limit", ["20"])[0]
        _require(JOURNEY_REF_PATTERN.fullmatch(journey)
                 and re.fullmatch(r"[1-9][0-9]?", limit) and int(limit) <= 50, "INVALID_REQUEST")
        cursor = None
        if "cursor" in values:
            raw = values["cursor"][0]
            _require(re.fullmatch(r"[A-Za-z0-9_-]{1,1024}", raw), "INVALID_REQUEST")
            decoded = base64.b64decode(raw + "=" * (-len(raw) % 4), altchars=b"-_", validate=True)
            cursor = strict_load_json(decoded)
            _require(type(cursor) is dict and set(cursor) == _CURSOR_FIELDS
                     and decoded == canonical_bytes(cursor)
                     and _encode(cursor) == raw
                     and cursor["owner_sha256"] == canonical_sha256(owner)
                     and cursor["journey_ref"] == journey
                     and type(cursor["head"]) is str and SHA256_PATTERN.fullmatch(cursor["head"])
                     and type(cursor["sequence"]) is int and 0 <= cursor["sequence"] < MAX_EVENTS
                     and type(cursor["offset"]) is int and 1 <= cursor["offset"] < MAX_EVENTS,
                     "INVALID_REQUEST")
        return journey, int(limit), cursor
    except (ValueError, TypeError, KeyError, RecursionError):
        raise GatewayOperationError("INVALID_REQUEST") from None


def _encode(cursor):
    return base64.urlsafe_b64encode(canonical_bytes(cursor)).decode("ascii").rstrip("=")


def _read_chain(root, owner, journey):
    """Pin every component; follow named predecessors instead of scanning stores."""
    relative = f"journeys/v2/owners/{owner}/{journey}"
    total = 0
    with open_artifact_root(root, writable=False) as cap:
        def read(path, maximum=MAX_FILE_BYTES):
            nonlocal total
            raw = cap.read_bytes(path, max_bytes=maximum)
            total += len(raw)
            _require(total <= MAX_TOTAL_BYTES)
            return strict_load_json(raw)

        try:
            head = read(f"{relative}/head.json", 4096)
        except PrivateArtifactError as exc:
            if exc.code == NOT_FOUND:
                raise GatewayOperationError("NOT_FOUND") from None
            raise
        _require(type(head) is dict and set(head) == {
            "schema", "journey_ref", "sequence", "event_head_sha256", "projection_sha256"}
            and head["schema"] == HEAD_SCHEMA and head["journey_ref"] == journey
            and type(head["sequence"]) is int and 0 <= head["sequence"] < MAX_EVENTS
            and type(head["event_head_sha256"]) is str
            and SHA256_PATTERN.fullmatch(head["event_head_sha256"])
            and type(head["projection_sha256"]) is str
            and SHA256_PATTERN.fullmatch(head["projection_sha256"]))
        digest, events = head["event_head_sha256"], []
        for sequence in range(head["sequence"], -1, -1):
            _require(type(digest) is str and SHA256_PATTERN.fullmatch(digest))
            event = validate_event(read(f"{relative}/events/{sequence:020d}-{digest}.json"))
            _require(event["event_sha256"] == digest and event["sequence"] == sequence
                     and event["journey_ref"] == journey and event["actor_id"] == owner)
            events.append(event)
            digest = event["prior_event_sha256"]
        _require(digest is None)
        events.reverse()
        projection = reduce_events(events)
        _require(canonical_sha256(projection) == head["projection_sha256"])
        # The immutable chain and committed head are the read snapshot. A concurrent
        # append may already have replaced projection.json; do not mix that version.
        return head, events


def list_operations(service, owner_ref: str, query: str) -> dict:
    journey, limit, cursor = _query(query, owner_ref)
    try:
        _, events = _read_chain(service.state_root, owner_ref, journey)
        if cursor is not None:
            sequence = cursor["sequence"]
            _require(sequence < len(events) and events[sequence]["event_sha256"] == cursor["head"],
                     "INVALID_REQUEST")
            events = events[:sequence + 1]
        anchor = events[-1]["event_sha256"]
        histories = {}
        for event in events:
            if event["event_type"] in LIFECYCLE:
                ref = event["payload"].get("operation_ref")
                _require(type(ref) is str)
                histories.setdefault(ref, []).append(event)
        for ref, history in histories.items():
            validate_history(history, ref)
            from .gateway_operation_route import operation_ref_for
            _require(ref == operation_ref_for(owner_ref, journey, history[0]["payload"]["client_request_id"]))
        ordered = sorted(histories, key=lambda ref: histories[ref][0]["sequence"], reverse=True)
        offset = cursor["offset"] if cursor else 0
        _require(offset < len(ordered) or offset == 0, "INVALID_REQUEST")
        from .gateway_operations import OperationSnapshot
        rows, request_hashes = [], {}
        for ref in ordered[offset:offset + limit]:
            request_hashes[ref] = canonical_sha256(histories[ref][0]["payload"]["client_request_id"])
            state, terminal = history_state(histories[ref])
            rows.append(OperationSnapshot(ref, journey, anchor, state, False,
                terminal["event_sha256"] if terminal else None,
                terminal["payload"]["result_sha256"] if terminal else None).as_json())
        next_offset = offset + len(rows)
        next_cursor = _encode({"owner_sha256": canonical_sha256(owner_ref), "journey_ref": journey,
            "head": anchor, "sequence": len(events) - 1, "offset": next_offset}) if next_offset < len(ordered) else None
        return {"schema": SCHEMA, "journey_ref": journey, "event_head_sha256": anchor,
                "operations": rows, "next_cursor": next_cursor,
                "request_sha256_by_operation": request_hashes}
    except PrivateArtifactError as exc:
        code = "NOT_FOUND" if exc.code == NOT_FOUND and not service.state_root.exists() else "STORE_COMMIT_FAILED"
        raise GatewayOperationError(code) from None
    except (ValueError, TypeError, KeyError, OSError, RecursionError):
        raise GatewayOperationError("STORE_COMMIT_FAILED") from None
