"""Bounded in-manager records for credential-bound live-screen deliveries."""

from __future__ import annotations

import json
import re

from .evidence_json import canonical_sha256

_REF = re.compile(r"dlv_[0-9a-f]{32}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")


def record_delivery(manager, *, owner_ref: str, receipt: dict) -> dict:
    frame = receipt.get("frame")
    provider = receipt.get("provider_binding")
    if not isinstance(frame, dict) or not isinstance(provider, dict):
        raise ValueError
    record = {
        "schema": "flywheel.live-screen-delivery-record/v1",
        "owner_ref": owner_ref,
        "frame": _frame_identity(frame),
        "model_route": receipt.get("model_route"),
        "model": receipt.get("model"),
        "delivery_mode": receipt.get("delivery_mode"),
        "transport_request_sha256": receipt.get("transport_request_sha256"),
        "provider_response_id": receipt.get("provider_response_id"),
        "provider_binding": json.loads(json.dumps(provider, sort_keys=True)),
        "delivered_at_utc": receipt.get("delivered_at_utc"),
        "frame_age_ms": receipt.get("frame_age_ms"),
        "stale": bool(receipt.get("stale")),
    }
    record["record_sha256"] = canonical_sha256(record)
    record["delivery_ref"] = "dlv_" + record["record_sha256"][:32]
    records = _records(manager)
    records[record["delivery_ref"]] = record
    while len(records) > 512:
        records.pop(next(iter(records)))
    return record


def validate_delivery_part(manager, *, owner_ref: str, part: dict) -> str:
    ref = part.get("delivery_ref")
    digest = part.get("delivery_receipt_sha256")
    if not (isinstance(ref, str) and _REF.fullmatch(ref)
            and isinstance(digest, str) and _SHA.fullmatch(digest)):
        return "delivery_receipt_missing"
    record = _records(manager).get(ref)
    if not record or record.get("owner_ref") != owner_ref or record.get("record_sha256") != digest:
        return "delivery_receipt_unverified"
    if record.get("stale") is True:
        return "delivery_receipt_stale"
    if (_frame_identity(part.get("frame")) != record.get("frame")
            or part.get("model_route") != record.get("model_route")
            or part.get("model") != record.get("model")
            or record.get("delivery_mode") != "sampled_image"):
        return "delivery_receipt_mismatch"
    return "validated"


def requires_delivery_record(part: dict) -> bool:
    return part.get("kind") == "screen_frame" or any(
        key in part for key in ("delivery_ref", "delivery_receipt_sha256"))


def _records(manager) -> dict:
    records = getattr(manager, "_delivery_records", None)
    if records is None:
        records = {}
        setattr(manager, "_delivery_records", records)
    return records


def _frame_identity(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    fields = ("session_id", "source_id", "source_sequence",
              "aggregate_sequence", "frame_sha256")
    out = {key: value.get(key) for key in fields}
    if not all(key in value for key in fields):
        return None
    return out
