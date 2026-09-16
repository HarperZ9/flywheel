"""Credential-bound provider delivery for sampled live-screen frames."""

from __future__ import annotations

import hashlib
import json
import time

from .gateway_agent_transport import AgentTransportError, BoundAgentTransport
from .gateway_operation import thaw_operation
from .live_screen_delivery import (
    DeliveryError,
    OpenAIResponsesImageTransport,
    deliver_latest_sampled_image,
)
from .live_screen_delivery_records import record_delivery
from .live_screen_types import ScreenShareGrant


def deliver_bound_sampled_image(manager, *, authorized, owner_ref: str,
                                now_ns: int, utc_now, opener=None,
                                clock=time.monotonic,
                                clock_ns=time.monotonic_ns) -> dict:
    op = thaw_operation(authorized.operation)
    bindings = authorized.credential_bindings
    if bindings is None:
        raise DeliveryError("PERMISSION_REQUIRED", "delivery credential binding is missing")
    try:
        api_key = bindings.value_for("OPENAI_API_KEY")
    except Exception as exc:
        raise DeliveryError("PERMISSION_REQUIRED", "delivery credential binding is missing") from exc
    timeout_s = op["timeout_s"]
    transport = BoundAgentTransport(
        base_url="https://api.openai.com/v1",
        adapter="openai",
        model=op["model"],
        deadline=clock() + timeout_s,
        max_tokens=op["max_output_tokens"],
        max_calls=1,
        clock=clock,
        opener=opener,
        native_protocol="openai_responses",
    )
    image_transport = OpenAIResponsesImageTransport(
        transport,
        base_url="https://api.openai.com/v1",
        model=op["model"],
        api_key=api_key,
        max_output_tokens=op["max_output_tokens"],
        model_route=op["destination"],
    )
    grant = ScreenShareGrant(
        owner_ref,
        op["destination"],
        op["model"],
        (op["source_id"],),
        now_ns + timeout_s * 1_000_000_000,
    )
    try:
        receipt = deliver_latest_sampled_image(
            manager,
            session_id=op["session_id"],
            source_id=op["source_id"],
            owner_ref=owner_ref,
            grant=grant,
            destination=op["destination"],
            model=op["model"],
            prompt=op["prompt"],
            transport=image_transport,
            now_ns=now_ns,
            utc_now=utc_now,
            clock_ns=clock_ns,
            max_age_ms=op.get("max_age_ms"),
            timeout=float(timeout_s),
        )
    except AgentTransportError as exc:
        raise DeliveryError(exc.code, "provider delivery failed") from exc
    refs = list(op["credential_refs"])
    receipt = {
        **receipt,
        "provider_binding": {
            "provider": "openai",
            "model_route": op["destination"],
            "model": op["model"],
            "credential_ref_count": len(refs),
            "credential_refs_sha256": hashlib.sha256(
                json.dumps(refs, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
        },
    }
    record = record_delivery(manager, owner_ref=owner_ref, receipt=receipt)
    receipt = {**receipt, "delivery_ref": record["delivery_ref"],
               "delivery_receipt_sha256": record["record_sha256"]}
    return {"schema": "flywheel.live-screen-delivery/v1", "receipt": receipt}
