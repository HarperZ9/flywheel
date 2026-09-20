"""Contracts for the native Studio programmatic body.

The body route is a narrow bridge: sensed state and frame refs come in as
measured data, model output proposes typed instrument controls, and authority
remains outside the model behind Accountable Surface.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from harness.studio_body_capture import (
    CaptureContractError,
    capture_evidence as normalize_capture_evidence,
    capture_request as normalize_capture_request,
)
from harness.live_screen_types import LiveScreenError, check_id

CONTRACT_VERSION = "flywheel.studio.body/v1"
SOUND_ACTION_KIND = "flywheel.studio.sound.compose/v1"
SOUND_CONTENT_SCHEMA = "flywheel.studio.body.sound.compose-request/v1"
SOUND_TARGET_PREFIX = "flywheel://studio/sound/"
STUDIO_BODY_SERVICE = "flywheel-studio-body"
STUDIO_BODY_ORIGIN = "flywheel://studio"
STUDIO_BODY_SOUND_PATH_SHAPE = r"/sound/[^/]+/[^/]+"

_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")
_RAW_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class BodyContractError(ValueError):
    """A body payload failed closed before reaching an instrument."""


@dataclass(frozen=True)
class SoundComposeStep:
    client_action_id: str
    idempotency_key: str
    model_route_ref: str
    observation_ref: str
    target: str
    session_ref: str
    instrument_ref: str
    seed: int
    duration_s: float
    root_hz: float
    capture_session_ref: str | None = None
    latest_frame_ref: str | None = None
    latest_delivered_frame_age_ms: int | None = None
    model_delivery: dict[str, Any] | None = None

    def accountable_content(self) -> dict[str, Any]:
        return {
            "schema": SOUND_CONTENT_SCHEMA,
            "client_action_id": self.client_action_id,
            "idempotency_key": self.idempotency_key,
            "model_route_ref": self.model_route_ref,
            "observation_ref": self.observation_ref,
            "capture_session_ref": self.capture_session_ref,
            "latest_frame_ref": self.latest_frame_ref,
            "latest_delivered_frame_age_ms": self.latest_delivered_frame_age_ms,
            "target": self.target,
            "session_ref": self.session_ref,
            "instrument_ref": self.instrument_ref,
            "args": {
                "seed": self.seed,
                "duration_s": self.duration_s,
                "root_hz": self.root_hz,
            },
            "model_delivery": copy.deepcopy(self.model_delivery or {"parts": []}),
        }

    def accountable_content_json(self) -> str:
        return canonical_json(self.accountable_content())


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def canonical_bytes(value: Any) -> bytes:
    return canonical_json(value).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def parse_body_step(body: Any) -> SoundComposeStep:
    if not isinstance(body, dict):
        raise BodyContractError("body must be an object")
    if body.get("schema") != CONTRACT_VERSION:
        raise BodyContractError(f"schema must be {CONTRACT_VERSION}")
    action = _dict(body.get("action"), "action")
    if action.get("kind") != SOUND_ACTION_KIND:
        raise BodyContractError(f"action.kind must be {SOUND_ACTION_KIND}")
    target = _nonempty(action.get("target"), "action.target")
    session_ref, instrument_ref = parse_sound_target(target)
    args = _dict(action.get("args"), "action.args")
    _no_extra(args, {"seed", "duration_s", "root_hz"}, "action.args")
    age = body.get("latest_delivered_frame_age_ms")
    return SoundComposeStep(
        client_action_id=_nonempty(body.get("client_action_id"), "client_action_id"),
        idempotency_key=_nonempty(body.get("idempotency_key"), "idempotency_key"),
        model_route_ref=_nonempty(body.get("model_route_ref"), "model_route_ref"),
        observation_ref=_nonempty(body.get("observation_ref"), "observation_ref"),
        capture_session_ref=_optional_capture_ref(body.get("capture_session_ref"), "capture_session_ref"),
        latest_frame_ref=_optional_capture_ref(body.get("latest_frame_ref"), "latest_frame_ref"),
        latest_delivered_frame_age_ms=_optional_age(age),
        target=target,
        session_ref=session_ref,
        instrument_ref=instrument_ref,
        seed=_seed(args.get("seed")),
        duration_s=_bounded_float(args.get("duration_s"), "duration_s", 6.0, 90.0),
        root_hz=_bounded_float(args.get("root_hz"), "root_hz", 55.0, 880.0),
        model_delivery=_model_delivery(body.get("model_delivery")),
    )


def parse_sound_content(content: str | dict[str, Any]) -> SoundComposeStep:
    try:
        body = json.loads(content) if isinstance(content, str) else content
    except json.JSONDecodeError as exc:
        raise BodyContractError("content must be JSON") from exc
    if not isinstance(body, dict) or body.get("schema") != SOUND_CONTENT_SCHEMA:
        raise BodyContractError(f"content schema must be {SOUND_CONTENT_SCHEMA}")
    return parse_body_step({
        "schema": CONTRACT_VERSION,
        "client_action_id": body.get("client_action_id"),
        "idempotency_key": body.get("idempotency_key"),
        "model_route_ref": body.get("model_route_ref"),
        "observation_ref": body.get("observation_ref"),
        "capture_session_ref": body.get("capture_session_ref"),
        "latest_frame_ref": body.get("latest_frame_ref"),
        "latest_delivered_frame_age_ms": body.get("latest_delivered_frame_age_ms"),
        "model_delivery": body.get("model_delivery"),
        "action": {"kind": SOUND_ACTION_KIND, "target": body.get("target"),
                   "args": body.get("args")},
    })


def parse_sound_target(target: str) -> tuple[str, str]:
    if not target.startswith(SOUND_TARGET_PREFIX):
        raise BodyContractError(f"target must start with {SOUND_TARGET_PREFIX}")
    parts = target[len(SOUND_TARGET_PREFIX):].split("/")
    if len(parts) != 2:
        raise BodyContractError("target must name session and instrument")
    session_ref, instrument_ref = parts
    _ref(session_ref, "session_ref")
    _ref(instrument_ref, "instrument_ref")
    return session_ref, instrument_ref


def build_body_snapshot(
    session_ref: str,
    instrument_ref: str,
    *,
    capture_request: dict[str, Any] | None = None,
    capture_evidence: dict[str, Any] | None = None,
    now: Callable[[], str] | None = None,
) -> dict[str, Any]:
    _ref(session_ref, "session_ref")
    _ref(instrument_ref, "instrument_ref")
    target = f"{SOUND_TARGET_PREFIX}{session_ref}/{instrument_ref}"
    captured_at = now() if now else datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    state = {"target": target, "instrument": "harness.sound_studio.compose_sound", "ready": True}
    state_sha = sha256_json(state)
    observation = {
        "observation_ref": "obs_" + state_sha[:16],
        "source": "flywheel.sound_studio.compose_state/v1",
        "delivery_mode": "measured_text_json",
        "state_sha256": state_sha,
    }
    try:
        capture = normalize_capture_evidence(capture_evidence, session_ref, instrument_ref)
        requested = normalize_capture_request(capture_request)
    except CaptureContractError as exc:
        raise BodyContractError(str(exc)) from exc
    frame = capture.get("latest_frame_ref")
    if frame:
        observation["latest_frame_ref"] = frame
    snapshot = {
        "snapshot_id": "snap_" + sha256_json({"target": target, "captured_at": captured_at})[:16],
        "captured_at": captured_at,
        "session_ref": session_ref,
        "instrument_ref": instrument_ref,
        "target": target,
        "capture_session_ref": capture.get("capture_session_ref"),
        "latest_frame_ref": frame,
        "latest_delivered_frame_age_ms": capture.get("latest_delivered_frame_age_ms"),
        "capture": capture,
        "requested_capture": requested,
        "observations": [observation],
    }
    return {"schema": "flywheel.studio.body.snapshot/v1", "snapshot": snapshot}


def _dict(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BodyContractError(f"{name} must be an object")
    return value


def _no_extra(value: dict[str, Any], allowed: set[str], name: str) -> None:
    extra = sorted(set(value) - allowed)
    if extra:
        raise BodyContractError(f"{name} has unsupported field(s): {', '.join(extra)}")


def _ref(value: Any, name: str) -> str:
    if not isinstance(value, str) or _REF.fullmatch(value) is None:
        raise BodyContractError(f"{name} must be a stable ref without slashes")
    return value


def _optional_ref(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _ref(value, name)


def _optional_capture_ref(value: Any, name: str) -> str | None:
    if value is None:
        return None
    try:
        return check_id(value, name)
    except LiveScreenError as exc:
        raise BodyContractError(f"{name} must be a stable ref without slashes") from exc


def _nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BodyContractError(f"{name} must be a non-empty string")
    return value


def _seed(value: Any) -> int:
    if type(value) is not int:
        raise BodyContractError("seed must be an integer")
    if not 0 <= value <= 0xFFFFFFFF:
        raise BodyContractError("seed must fit an unsigned 32-bit integer")
    return value


def _bounded_float(value: Any, name: str, lo: float, hi: float) -> float:
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise BodyContractError(f"{name} must be a finite number")
    out = float(value)
    if not lo <= out <= hi:
        raise BodyContractError(f"{name} must sit between {lo:g} and {hi:g}")
    return out


def _optional_age(value: Any) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise BodyContractError("latest_delivered_frame_age_ms must be a non-negative integer")
    return value


def _model_delivery(value: Any) -> dict[str, Any]:
    if value is None:
        return {"parts": []}
    if not isinstance(value, dict) or not isinstance(value.get("parts"), list):
        raise BodyContractError("model_delivery.parts must be a list")
    try:
        cleaned = json.loads(canonical_json(value))
    except (TypeError, ValueError) as exc:
        raise BodyContractError("model_delivery must be finite JSON") from exc
    for index, part in enumerate(cleaned["parts"]):
        if not isinstance(part, dict) or not isinstance(part.get("kind"), str):
            raise BodyContractError(f"model_delivery.parts[{index}] must name a kind")
        if "sha256" in part and not (
            isinstance(part["sha256"], str) and _RAW_SHA256.fullmatch(part["sha256"])
        ):
            raise BodyContractError(f"model_delivery.parts[{index}].sha256 must be raw sha256")
    return cleaned
