"""Accountable Surface effector for Studio Engine visual actions."""

from __future__ import annotations

import copy
import hashlib
from typing import Any

from harness.studio_body_contract import STUDIO_BODY_ORIGIN, STUDIO_BODY_SERVICE, canonical_json
from harness.studio_body_engine_contract import (
    ENGINE_ACTION_KIND,
    STUDIO_BODY_ENGINE_PATH_SHAPE,
    EngineRenderStep,
    parse_engine_content,
    parse_engine_target,
)
from harness.studio_body_engine_render import StudioEngineUnavailable, render_studio_engine_world


class StudioBodyEngineEffector:
    name = "studio-engine-effector"
    action_kind = ENGINE_ACTION_KIND

    def __init__(self) -> None:
        self._states: dict[str, dict[str, Any]] = {}
        self._results: dict[str, dict[str, Any]] = {}
        self._previous: dict[str, dict[str, Any] | None] = {}
        self._planned: dict[str, EngineRenderStep] = {}

    def bound(self) -> dict[str, Any]:
        return {"kind": "api", "origins": [STUDIO_BODY_ORIGIN], "intents": ["render_world"]}

    def perceive(self, target: str):
        from coherence_membrane.observation import Observation, Provenance, Status, sha256_hex
        parse_engine_target(target)
        state = copy.deepcopy(self._states.get(target)) or {
            "present": False, "target": target, "instrument": "studio_engine.engine.run"}
        payload = canonical_json(state).encode()
        return Observation(
            organ=self.name, subject=target,
            summary=("studio engine world rendered" if state.get("present") else "studio engine empty"),
            status=Status.PASS, provenance=Provenance.witness_bytes(target, payload, "high"),
            data={"url": target, "status": 200, "state": state, "sha256": sha256_hex(payload)})

    def preview(self, target: str, step: EngineRenderStep, before: Any | None = None):
        from accountable_surface.effector import Plan, RefusedActuation
        from coherence_membrane.observation import sha256_hex
        if step.target != target:
            raise RefusedActuation("body action target does not match the effector target")
        content_sha = sha256_hex(step.accountable_content_json().encode())
        digest = "sha256:" + sha256_hex(f"{ENGINE_ACTION_KIND}|{target}|{content_sha}".encode())
        self._planned[digest] = step
        existed = bool(((before.data if before is not None else {}) or {}).get("state", {}).get("present"))
        return Plan(ENGINE_ACTION_KIND, target, content_sha, True, existed, digest)

    def act(self, plan: Any, allow_receipt: Any, step: EngineRenderStep):
        from accountable_surface.effector import RefusedActuation
        if getattr(allow_receipt, "decision", None) != "allow":
            raise RefusedActuation("no gate allow -- the engine effector will not act")
        planned = (getattr(allow_receipt, "request", {}) or {}).get("planned_action", {})
        if planned.get("action_kind") != plan.action_kind or planned.get("target") != plan.target:
            raise RefusedActuation("allow receipt does not match the engine plan")
        if self._content_sha(step) != plan.content_sha256 or self._planned.get(plan.digest) != step:
            raise RefusedActuation("engine step does not match the authorized plan")
        self._previous[plan.digest] = copy.deepcopy(self._states.get(plan.target))
        try:
            result = render_studio_engine_world(step)
        except StudioEngineUnavailable as exc:
            raise RefusedActuation(f"{exc.code}: {exc}") from exc
        self._results[plan.target] = copy.deepcopy(result)
        self._states[plan.target] = _state(plan.target, step, result)
        return self.perceive(plan.target)

    def verify(self, plan: Any, after: Any):
        from accountable_surface.effector import Verdict
        result = self._results.get(plan.target)
        state = ((after.data if after is not None else {}) or {}).get("state", {})
        if not result or state.get("world_id") != result.get("world_id"):
            return Verdict("failed", "engine world is absent after actuation")
        if state.get("first_frame_sha256") != result["frames"][0]["frame_sha256"]:
            return Verdict("failed", "engine frame hash does not match rendered bytes")
        return Verdict("pass", "")

    def rollback(self, plan: Any) -> None:
        prev = self._previous.get(plan.digest)
        if prev is None:
            self._states.pop(plan.target, None)
        else:
            self._states[plan.target] = prev
        self._results.pop(plan.target, None)

    def last_result(self, target: str) -> dict[str, Any] | None:
        result = self._results.get(target)
        return copy.deepcopy(result) if result is not None else None

    @staticmethod
    def _content_sha(step: EngineRenderStep) -> str:
        return hashlib.sha256(step.accountable_content_json().encode()).hexdigest()


def make_studio_engine_exposed(effector: StudioBodyEngineEffector | None = None):
    from accountable_surface.registry import Exposed
    return Exposed(
        ENGINE_ACTION_KIND, effector or StudioBodyEngineEffector(), _decode_engine_content,
        "Flywheel Studio Engine visual world renderer via Accountable Surface remote_durable",
        describe_engine_read, lambda payload: ("before", "after", "rollback"))


def studio_engine_read_scope(*, phases: tuple[str, ...] = ("before", "after", "rollback")) -> dict[str, Any]:
    return {
        "observation_kind": "api.resource", "phases": list(phases),
        "target_scope": {"kind": "api", "service": STUDIO_BODY_SERVICE,
                         "origins": [STUDIO_BODY_ORIGIN], "intents": ["render_world"],
                         "paths": [STUDIO_BODY_ENGINE_PATH_SHAPE]},
    }


def describe_engine_read(target: str, payload: EngineRenderStep, phase: str, request_id: str):
    from accountable_surface.api_effector import ApiCall, ApiOperation, ApiService
    from accountable_surface.read_authority import describe_api_read
    service = ApiService(
        name=STUDIO_BODY_SERVICE, host="studio", auth_env="", scheme="flywheel",
        operations=(ApiOperation(intent="render_world", action_kind=ENGINE_ACTION_KIND,
                                 method="POST", path_shape=STUDIO_BODY_ENGINE_PATH_SHAPE),),
    )
    return describe_api_read(service, target, ApiCall("render_world", {}), phase, request_id)


def _decode_engine_content(content: str) -> EngineRenderStep:
    try:
        return parse_engine_content(content)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc


def _state(target: str, step: EngineRenderStep, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "present": True, "target": target, "client_action_id": step.client_action_id,
        "model_route_ref": step.model_route_ref, "observation_ref": step.observation_ref,
        "capture_session_ref": step.capture_session_ref, "latest_frame_ref": step.latest_frame_ref,
        "world_id": result["world_id"], "world_sha256": result["world_sha256"],
        "frame_count": result["frame_count"],
        "first_frame_sha256": result["frames"][0]["frame_sha256"],
        "engine_head": result["engine_head"],
    }
