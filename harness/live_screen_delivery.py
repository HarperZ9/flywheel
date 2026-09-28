"""Delivery seam for sampled live-screen frames.

This module deliberately bypasses the accepted text chat route because that
route drops non-text content parts.  It uses the existing bounded provider
transport shape for OpenAI Responses image input.
"""

from __future__ import annotations

import base64
import hashlib
import json

from .live_screen_feed import LiveScreenError


class DeliveryError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _fail(code: str, message: str) -> None:
    raise DeliveryError(code, message)


class OpenAIResponsesImageTransport:
    """Send one sampled frame through a BoundAgentTransport-compatible callable."""

    def __init__(self, transport, *, base_url: str, model: str, api_key: str,
                 max_output_tokens: int, detail: str = "auto",
                 max_body_bytes: int = 1 << 20,
                 model_route: str = "openai_responses:vision"):
        self.transport = transport
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.model_route = model_route
        self.api_key = api_key
        self.max_output_tokens = max_output_tokens
        self.detail = detail
        self.max_body_bytes = max_body_bytes

    def send_sampled_image(self, *, frame, prompt: str, timeout: float = 30.0) -> dict:
        if frame.media_type not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
            _fail("UNSUPPORTED_IMAGE_MEDIA_TYPE", "sampled screen frames must be supported images")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 10_000:
            _fail("INVALID_PROMPT", "sampled image delivery requires a bounded prompt")
        image_url = ("data:" + frame.media_type + ";base64," +
                     base64.b64encode(frame.payload).decode("ascii"))
        payload = {
            "model": self.model,
            "input": [{"role": "user", "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image", "image_url": image_url, "detail": self.detail},
            ]}],
            "max_output_tokens": self.max_output_tokens,
            "store": False,
            "parallel_tool_calls": False,
            "tools": [],
            "stream": False,
            "temperature": 0,
        }
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        if len(body) > self.max_body_bytes:
            _fail("SAMPLED_IMAGE_BODY_TOO_LARGE", "sampled image payload exceeds transport limit")
        status, obj = self.transport(
            "POST", self.base_url + "/responses",
            {"content-type": "application/json", "authorization": "Bearer " + self.api_key},
            body, timeout)
        if type(status) is not int or not 200 <= status < 300:
            _fail("PROVIDER_DELIVERY_FAILED", "provider did not accept sampled image")
        return {"provider_status": status, "provider_response_id": obj.get("id"),
                "transport_request_sha256": hashlib.sha256(body).hexdigest()}


def deliver_latest_sampled_image(manager, *, session_id: str, source_id: str, owner_ref: str,
                                 grant, destination: str, model: str, prompt: str,
                                 transport: OpenAIResponsesImageTransport, now_ns: int,
                                 utc_now, clock_ns=None, max_age_ms: int | None = None,
                                 timeout: float = 30.0) -> dict:
    if getattr(transport, "model", None) != model:
        _fail("TRANSPORT_MODEL_MISMATCH", "transport model differs from session binding")
    if getattr(transport, "model_route", None) != destination:
        _fail("TRANSPORT_ROUTE_MISMATCH", "transport route differs from session binding")
    try:
        frame = manager.frame_for_delivery(
            session_id, source_id, owner_ref=owner_ref, grant=grant,
            destination=destination, model=model, now_ns=now_ns)
    except LiveScreenError as exc:
        _fail(exc.code, str(exc))
    frame_ref = frame.identity()
    sent = transport.send_sampled_image(frame=frame, prompt=prompt, timeout=timeout)
    finish_ns = clock_ns() if clock_ns is not None else now_ns
    try:
        current = manager.frame_for_delivery(
            session_id, source_id, owner_ref=owner_ref, grant=grant,
            destination=destination, model=model, now_ns=finish_ns)
    except LiveScreenError as exc:
        _fail(exc.code, str(exc))
    if current.identity() != frame_ref:
        _fail("FRAME_REFERENCE_STALE", "captured frame changed before delivery completed")
    age_ms = frame.age_ms(finish_ns)
    stale = max_age_ms is not None and age_ms > max_age_ms
    return {
        "event": "screen.delivery",
        **frame_ref,
        "frame": frame_ref,
        "model_route": destination,
        "model": model,
        "delivery_mode": "sampled_image",
        "delivered_at_utc": utc_now(),
        "frame_age_ms": age_ms,
        "stale": stale,
        **sent,
    }


def deliver_native_video(*_args, **_kwargs):
    _fail("NATIVE_VIDEO_UNAVAILABLE", "native video delivery has no registered transport")


def verify_body_action_frame_reference(action: dict, delivery_receipt: dict) -> dict:
    expected = delivery_receipt.get("frame")
    if not isinstance(action, dict) or not isinstance(expected, dict):
        return {"ok": False, "code": "MALFORMED_FRAME_REFERENCE"}
    actual = action.get("live_screen_frame")
    if not isinstance(actual, dict):
        return {"ok": False, "code": "MISSING_FRAME_REFERENCE"}
    if actual != expected:
        return {"ok": False, "code": "FRAME_REFERENCE_MISMATCH"}
    return {"ok": True, "code": "FRAME_REFERENCE_MATCH"}
