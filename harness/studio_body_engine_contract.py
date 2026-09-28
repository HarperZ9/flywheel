"""Contract parser for Studio Engine body actions."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from typing import Any

from harness.studio_body_contract import CONTRACT_VERSION, BodyContractError, canonical_json
from harness.live_screen_types import LiveScreenError, check_id

ENGINE_ACTION_KIND = "flywheel.studio.engine.render-world/v1"
ENGINE_CONTENT_SCHEMA = "flywheel.studio.body.engine.render-world-request/v1"
ENGINE_TARGET_PREFIX = "flywheel://studio/engine/"
STUDIO_BODY_ENGINE_PATH_SHAPE = r"/engine/[^/]+/[^/]+"
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")
_SCHEMES = {"analogous", "triadic", "complementary", "wide"}


@dataclass(frozen=True)
class EngineRenderStep:
    client_action_id: str
    idempotency_key: str
    model_route_ref: str
    observation_ref: str
    target: str
    session_ref: str
    instrument_ref: str
    seed: int
    generator: str
    scheme: str
    max_steps: int
    target_score: float
    floor: float
    render_frames: bool
    capture_session_ref: str | None = None
    latest_frame_ref: str | None = None
    latest_delivered_frame_age_ms: int | None = None
    model_delivery: dict[str, Any] | None = None
    action_kind: str = ENGINE_ACTION_KIND

    def accountable_content(self) -> dict[str, Any]:
        return {
            "schema": ENGINE_CONTENT_SCHEMA,
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
            "args": {"seed": self.seed, "generator": self.generator,
                     "scheme": self.scheme, "max_steps": self.max_steps,
                     "target": self.target_score, "floor": self.floor,
                     "render_frames": self.render_frames},
            "model_delivery": copy.deepcopy(self.model_delivery or {"parts": []}),
        }

    def accountable_content_json(self) -> str:
        return canonical_json(self.accountable_content())


def parse_engine_body_step(body: Any) -> EngineRenderStep:
    if not isinstance(body, dict):
        raise BodyContractError("body must be an object")
    if body.get("schema") != CONTRACT_VERSION:
        raise BodyContractError(f"schema must be {CONTRACT_VERSION}")
    action = _dict(body.get("action"), "action")
    if action.get("kind") != ENGINE_ACTION_KIND:
        raise BodyContractError(f"action.kind must be {ENGINE_ACTION_KIND}")
    target = _nonempty(action.get("target"), "action.target")
    session_ref, instrument_ref = parse_engine_target(target)
    args = _dict(action.get("args"), "action.args")
    _no_extra(args, {"seed", "generator", "scheme", "max_steps", "target", "floor", "render_frames"}, "action.args")
    return EngineRenderStep(
        _nonempty(body.get("client_action_id"), "client_action_id"),
        _nonempty(body.get("idempotency_key"), "idempotency_key"),
        _nonempty(body.get("model_route_ref"), "model_route_ref"),
        _nonempty(body.get("observation_ref"), "observation_ref"),
        target, session_ref, instrument_ref, _seed(args.get("seed")),
        _generator(args.get("generator")), _scheme(args.get("scheme")),
        _bounded_int(args.get("max_steps"), "max_steps", 1, 16),
        _bounded_float(args.get("target"), "target", 0.0, 1.0),
        _bounded_float(args.get("floor"), "floor", 0.0, 1.0),
        _render_frames(args.get("render_frames")),
        _optional_capture_ref(body.get("capture_session_ref"), "capture_session_ref"),
        _optional_capture_ref(body.get("latest_frame_ref"), "latest_frame_ref"),
        _optional_age(body.get("latest_delivered_frame_age_ms")),
        _model_delivery(body.get("model_delivery")),
    )


def parse_engine_content(content: str | dict[str, Any]) -> EngineRenderStep:
    try:
        body = json.loads(content) if isinstance(content, str) else content
    except json.JSONDecodeError as exc:
        raise BodyContractError("content must be JSON") from exc
    if not isinstance(body, dict) or body.get("schema") != ENGINE_CONTENT_SCHEMA:
        raise BodyContractError(f"content schema must be {ENGINE_CONTENT_SCHEMA}")
    return parse_engine_body_step({
        "schema": CONTRACT_VERSION,
        "client_action_id": body.get("client_action_id"),
        "idempotency_key": body.get("idempotency_key"),
        "model_route_ref": body.get("model_route_ref"),
        "observation_ref": body.get("observation_ref"),
        "capture_session_ref": body.get("capture_session_ref"),
        "latest_frame_ref": body.get("latest_frame_ref"),
        "latest_delivered_frame_age_ms": body.get("latest_delivered_frame_age_ms"),
        "model_delivery": body.get("model_delivery"),
        "action": {"kind": ENGINE_ACTION_KIND, "target": body.get("target"),
                   "args": body.get("args")},
    })


def parse_engine_target(target: str) -> tuple[str, str]:
    if not target.startswith(ENGINE_TARGET_PREFIX):
        raise BodyContractError(f"target must start with {ENGINE_TARGET_PREFIX}")
    parts = target[len(ENGINE_TARGET_PREFIX):].split("/")
    if len(parts) != 2:
        raise BodyContractError("target must name session and instrument")
    return _ref(parts[0], "session_ref"), _ref(parts[1], "instrument_ref")


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


def _generator(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", value):
        raise BodyContractError("generator must be a stable Studio Engine generator id")
    return value


def _scheme(value: Any) -> str:
    if value not in _SCHEMES:
        raise BodyContractError("scheme must be one of the Studio Engine palette schemes")
    return value


def _seed(value: Any) -> int:
    if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
        raise BodyContractError("seed must fit an unsigned 32-bit integer")
    return value


def _bounded_int(value: Any, name: str, lo: int, hi: int) -> int:
    if type(value) is not int or not lo <= value <= hi:
        raise BodyContractError(f"{name} must sit between {lo:g} and {hi:g}")
    return value


def _bounded_float(value: Any, name: str, lo: float, hi: float) -> float:
    if type(value) not in (int, float):
        raise BodyContractError(f"{name} must be a finite number")
    out = float(value)
    if not lo <= out <= hi:
        raise BodyContractError(f"{name} must sit between {lo:g} and {hi:g}")
    return out


def _render_frames(value: Any) -> bool:
    if value is not True:
        raise BodyContractError("render_frames must be true for the visual engine bridge")
    return True


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
        return json.loads(canonical_json(value))
    except (TypeError, ValueError) as exc:
        raise BodyContractError("model_delivery must be finite JSON") from exc
