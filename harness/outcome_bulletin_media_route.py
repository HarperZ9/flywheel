"""Private gateway routes for Bulletin media review."""
from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
from typing import Callable

from .bulletin_signed_transport import BulletinSignedTransportError
from .evidence_public import TransportError, exact_request
from .gateway_operation import PROPOSAL_REF_PATTERN, REQUEST_SCHEMA as GATEWAY_SCHEMA
from .operation_grants import _parse_time
from .outcome_bulletin_media import (
    SELECTION_SCHEMA,
    build_gateway_media_grant_request,
    build_media_preview_from_run_selection,
    preview_media_bytes,
)
from .outcome_bulletin_media_selection import list_media_artifacts, list_media_runs

PREPARED_PREVIEW_SCHEMA = "flywheel.outcome-bulletin-media-preview-response/v1"
PREVIEW_BYTES_REQUEST_SCHEMA = "flywheel.bulletin-media-preview-bytes-request/v1"


def prepared_preview_body(
        body: dict, *, state_root: Path, run_root: Path, owner_ref: str,
        prepare: Callable[[dict], dict]) -> dict:
    request = build_preview_prepare_body(
        body, state_root=state_root, run_root=run_root, owner_ref=owner_ref)
    proposal = prepare(request)
    return {"schema": PREPARED_PREVIEW_SCHEMA, "proposal": proposal,
            "operation": _operation_wrapper(request)}


def build_preview_prepare_body(
        body: dict, *, state_root: Path, run_root: Path, owner_ref: str) -> dict:
    exact_request(body, {
        "schema", "journey_ref", "expected_event_head", "client_request_id",
        "credential_ref", "run_id", "destination", "post", "media"},
        optional={"timeout", "bulletin_access"})
    if body.get("schema") != SELECTION_SCHEMA:
        raise TransportError(
            "INVALID_BULLETIN_MEDIA", "Bulletin media request is invalid", 422)
    try:
        preview = build_media_preview_from_run_selection(
            body, state_root=state_root, run_root=run_root, owner_ref=owner_ref,
            allow_loopback=os.environ.get("FLYWHEEL_BULLETIN_ALLOW_LOOPBACK") == "1")
    except BulletinSignedTransportError as exc:
        raise TransportError(
            "INVALID_BULLETIN_MEDIA", "Bulletin media request is invalid", 422
        ) from exc
    return build_gateway_media_grant_request(
        preview, journey_ref=body["journey_ref"],
        expected_event_head=body["expected_event_head"],
        client_request_id=body["client_request_id"],
        timeout=body.get("timeout", 20),
        credential_ref=body["credential_ref"],
        bulletin_access=body.get("bulletin_access"))


def preview_bytes_body(
        body: dict, *, state_root: Path, owner_ref: str,
        load_record: Callable[[str], dict], clock: Callable[[], str]) -> dict:
    exact_request(body, {
        "schema", "proposal_ref", "preview_ref", "preview_sha256"})
    if body.get("schema") != PREVIEW_BYTES_REQUEST_SCHEMA:
        raise TransportError(
            "INVALID_BULLETIN_MEDIA", "Bulletin media request is invalid", 422)
    proposal_ref = body["proposal_ref"]
    if (type(proposal_ref) is not str
            or PROPOSAL_REF_PATTERN.fullmatch(proposal_ref) is None):
        raise TransportError(
            "INVALID_BULLETIN_MEDIA", "Bulletin media request is invalid", 422)
    record = load_record(proposal_ref)
    if record["state"] == "rejected" or _parse_time(clock()) >= _parse_time(
            record["expires_at"]):
        raise TransportError(
            "APPROVAL_EXPIRED", "approval proposal is no longer active", 403)
    preview = record["operation"]["args"]
    review_refs = {row["preview_ref"] for row in preview.get("preview_media", [])}
    if (preview.get("preview_sha256") != body["preview_sha256"]
            or body["preview_ref"] not in review_refs):
        raise TransportError(
            "INVALID_BULLETIN_MEDIA", "Bulletin media request is invalid", 422)
    raw, headers = preview_media_bytes(
        state_root, body["preview_ref"], owner_ref=owner_ref)
    return {
        "schema": "flywheel.bulletin-media-preview-bytes/v1",
        "preview_ref": body["preview_ref"],
        "preview_sha256": body["preview_sha256"],
        "content_type": headers["content-type"],
        "cache": "no-store",
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "body_b64": base64.b64encode(raw).decode(),
    }



def runs_body(body: dict, *, run_root: Path) -> dict:
    return list_media_runs(body, run_root=run_root)


def artifacts_body(body: dict, *, run_root: Path) -> dict:
    return list_media_artifacts(body, run_root=run_root)


def _operation_wrapper(request: dict) -> dict:
    return {"schema": GATEWAY_SCHEMA, "action": "lane.call",
            "journey_ref": request["journey_ref"],
            "expected_event_head": request["expected_event_head"],
            "client_request_id": request["client_request_id"],
            "operation": request["operation"]}
