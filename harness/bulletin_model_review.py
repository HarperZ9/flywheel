"""Bounded trusted review exchange, with labels sealed before actor-claim reveal."""
from __future__ import annotations

import math
from datetime import datetime, timezone
import time
from uuid import uuid4

from .bulletin_model_exchange import ExchangeError
from .evidence_json import canonical_bytes, strict_load_json
from .private_artifact_fs import PrivateArtifactError, NOT_FOUND
from .bulletin_model_review_evidence import (PROCEDURE, PROCEDURE_SHA256, validate_metadata,
    validate_item, accounting_receipt)


def wait_record(store, name, *, timeout=120, max_bytes=65536, clock=time.monotonic, sleep=time.sleep):
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 120:
        raise ValueError("invalid_review_wait")
    end = clock() + timeout
    while clock() < end:
        try:
            raw = store.read(name, max_bytes=max_bytes)
        except ExchangeError as exc:
            cause = exc
            while cause is not None and not (isinstance(cause, PrivateArtifactError) and cause.code == NOT_FOUND):
                cause = cause.__cause__
            if cause is None:
                raise
            sleep(min(0.05, max(0, end - clock())))
            continue
        return strict_load_json(raw, max_bytes=max_bytes, max_depth=20), raw
    raise TimeoutError("trusted_review_deadline")


def native_reviewer(store):
    def review(record):
        store.put("review-request.json", canonical_bytes(record), max_bytes=65536)
        decision, _ = wait_record(store, "decision-input.json", max_bytes=8192)
        return decision
    return review


def review_prefix(rows, *, blind_store, control_store, continuation=True):
    if len(rows) != (4 if continuation else 8) or any(row.get("review") is None for row in rows):
        raise ValueError("prefix_observations_required")
    bindings, packets, packet_hashes = {}, {}, {}
    for row in rows:
        opaque = "item-" + uuid4().hex
        bindings[opaque] = row
        review = row["review"]
        packet = {"item_id": opaque, "contract": review["contract"], "observation": review["observation"]}
        packets[opaque] = packet
        packet_hashes[opaque] = blind_store.put(opaque + ".json", canonical_bytes(packet), max_bytes=1048576)
    control_store.put("blind-bindings.json", canonical_bytes({k: v["slot_id"] for k, v in bindings.items()}), max_bytes=8192)
    blind_store.put("instructions.json", canonical_bytes({
        "schema": "flywheel.bulletin-blind-review/v2", "item_ids": sorted(bindings),
        "procedure": PROCEDURE, "procedure_sha256": PROCEDURE_SHA256, "packet_sha256": packet_hashes,
        "schema_reference": "docs/bulletin-model-evaluation.md#blinded-reconstruction-records"}), max_bytes=16384)
    labels, raw = wait_record(blind_store, "labels-input.json")
    received_at = datetime.now(timezone.utc).isoformat()
    try:
        validate_metadata(labels)
        if len(labels["items"]) != len(rows):
            raise ValueError()
    except (ValueError, TypeError, KeyError):
        raise ValueError("blind_labels_invalid") from None
    seen, agrees = set(), True
    for label in labels["items"]:
        try:
            if type(label) is not dict or label.get("item_id") not in bindings or label["item_id"] in seen:
                raise ValueError()
            validate_item(label, packets[label["item_id"]], packet_hashes[label["item_id"]], metadata=labels)
            if label["verdict"] not in ("PASS", "FAIL", "UNVERIFIABLE"):
                raise ValueError()
        except (ValueError, TypeError, KeyError):
            raise ValueError("blind_labels_invalid") from None
        seen.add(label["item_id"])
        row = bindings[label["item_id"]]
        agrees &= label["verdict"] == row["review"]["result"]["verdict"]
        agrees &= label["evidence_complete"] == (not row["review"]["result"]["acquisition_gaps"])
    label_sha = control_store.put("blind-labels-frozen.json", raw, max_bytes=65536)
    task_accounting = accounting_receipt(labels, received_at=received_at, frozen_at=datetime.now(timezone.utc).isoformat())
    # Only after immutable labels exist may the claim/checker phase be exposed.
    claims_sha = blind_store.put("claims-revealed.json", canonical_bytes({"labels_sha256": label_sha, "items": [
        {"item_id": opaque, "claim": row["result"]["claim"]}
        for opaque, row in bindings.items()]}), max_bytes=262144)
    claims, claim_raw = wait_record(blind_store, "claim-labels-input.json")
    claim_received_at = datetime.now(timezone.utc).isoformat()
    try:
        validate_metadata(claims, claims=True, first=labels)
        if claims["claims_sha256"] != claims_sha or len(claims["items"]) != len(rows):
            raise ValueError()
    except (ValueError, TypeError, KeyError):
        raise ValueError("claim_labels_invalid") from None
    seen = set()
    for item in claims["items"]:
        try:
            if type(item) is not dict or item.get("item_id") not in bindings or item["item_id"] in seen:
                raise ValueError()
            validate_item(item, packets[item["item_id"]], packet_hashes[item["item_id"]], claims=True,
                claim=bindings[item["item_id"]]["result"]["claim"], metadata=claims)
            if item["claim_support"] not in ("supported", "unsupported", "no_completion_claim", "unverifiable"):
                raise ValueError()
        except (ValueError, TypeError, KeyError):
            raise ValueError("claim_labels_invalid") from None
        seen.add(item["item_id"])
        row = bindings[item["item_id"]]
        claim = row["result"].get("claim")
        expected = "no_completion_claim"
        if type(claim) is dict and claim.get("completion") == "success":
            expected = {"PASS": "supported", "FAIL": "unsupported", "UNVERIFIABLE": "unverifiable"}[
                row["review"]["result"]["verdict"]]
        agrees &= item["claim_support"] == expected
    claim_sha = control_store.put("claim-labels-frozen.json", claim_raw, max_bytes=65536)
    review_accounting = {"task_pass": task_accounting, "claim_pass": accounting_receipt(claims,
        received_at=claim_received_at, frozen_at=datetime.now(timezone.utc).isoformat()),
        "outside_actor_generation_budget": True, "statistical_independence_proven": False}
    review_sha = control_store.put("blind-review-receipt.json", canonical_bytes({
        "task_labels_sha256": label_sha, "claim_labels_sha256": claim_sha,
        "reviewer_id": labels["reviewer_id"], "reviewer_type": "model_assisted",
        "procedure_sha256": PROCEDURE_SHA256, "packet_sha256": packet_hashes,
        "review_accounting": review_accounting}), max_bytes=32768)
    blind_store.put("checker-revealed.json", canonical_bytes({"labels_sha256": label_sha,
        "claim_labels_sha256": claim_sha, "items": [
            {"item_id": opaque, "checker": row["review"]["result"]} for opaque, row in bindings.items()]}), max_bytes=262144)
    if not continuation:
        return {"status": "reviewed", "independent_review_agrees": bool(agrees),
            "reviewer_id": labels["reviewer_id"], "reviewer_type": "model_assisted",
            "blind_review_sha256": review_sha, "human_validation": False, "review_accounting": review_accounting}
    gate, _ = wait_record(control_store, "continuation-input.json")
    if type(gate) is not dict:
        raise ValueError("continuation_input_invalid")
    gate = dict(gate)
    gate.update(independent_review_agrees=bool(agrees), reviewer_id=labels["reviewer_id"],
        reviewer_type="model_assisted", blind_review_sha256=review_sha,
        observation_complete=all(not row["review"]["result"]["acquisition_gaps"] for row in rows),
        interpretable_claims=sum(type(row["result"].get("claim")) is dict for row in rows))
    return gate
