"""Sound instrument effector for the Studio programmatic body."""

from __future__ import annotations

import copy
import hashlib
from typing import Any

from harness.sound_studio import compose_sound
from harness.studio_body_contract import (
    SOUND_ACTION_KIND,
    STUDIO_BODY_ORIGIN,
    STUDIO_BODY_SERVICE,
    STUDIO_BODY_SOUND_PATH_SHAPE,
    SoundComposeStep,
    canonical_bytes,
    parse_sound_content,
    parse_sound_target,
)


class StudioBodySoundEffector:
    """Accountable Surface effector over the deterministic sound composer."""

    name = "studio-sound-effector"
    action_kind = SOUND_ACTION_KIND

    def __init__(self) -> None:
        self._states: dict[str, dict[str, Any]] = {}
        self._results: dict[str, dict[str, Any]] = {}
        self._previous: dict[str, tuple[dict[str, Any] | None, dict[str, Any] | None]] = {}
        self._planned: dict[str, SoundComposeStep] = {}

    def bound(self) -> dict[str, Any]:
        return {"kind": "api", "origins": [STUDIO_BODY_ORIGIN], "intents": ["compose_sound"]}

    def perceive(self, target: str):
        from coherence_membrane.observation import Observation, Provenance, Status, sha256_hex

        parse_sound_target(target)
        state = copy.deepcopy(self._states.get(target)) or {
            "present": False,
            "target": target,
            "instrument": "harness.sound_studio.compose_sound",
        }
        payload = canonical_bytes(state)
        return Observation(
            organ=self.name,
            subject=target,
            summary=("studio sound composed" if state.get("present") else "studio sound empty"),
            status=Status.PASS,
            provenance=Provenance.witness_bytes(target, payload, "high"),
            data={"url": target, "status": 200, "state": state, "sha256": sha256_hex(payload)},
        )

    def preview(self, target: str, step: SoundComposeStep, before: Any | None = None):
        from accountable_surface.effector import Plan, RefusedActuation
        from coherence_membrane.observation import sha256_hex

        if step.target != target:
            raise RefusedActuation("body action target does not match the effector target")
        parse_sound_target(target)
        content_sha = sha256_hex(step.accountable_content_json().encode("utf-8"))
        digest = "sha256:" + sha256_hex(f"{SOUND_ACTION_KIND}|{target}|{content_sha}".encode("utf-8"))
        self._planned[digest] = step
        existed = bool(((before.data if before is not None else {}) or {}).get("state", {}).get("present"))
        return Plan(SOUND_ACTION_KIND, target, content_sha, True, existed, digest)

    def act(self, plan: Any, allow_receipt: Any, step: SoundComposeStep):
        from accountable_surface.effector import RefusedActuation

        if getattr(allow_receipt, "decision", None) != "allow":
            raise RefusedActuation("no gate allow -- the sound effector will not act")
        planned = (getattr(allow_receipt, "request", {}) or {}).get("planned_action", {})
        if planned.get("action_kind") != plan.action_kind or planned.get("target") != plan.target:
            raise RefusedActuation("allow receipt does not match the sound plan")
        if self._content_sha(step) != plan.content_sha256:
            raise RefusedActuation("sound content does not match the authorized plan")
        if self._planned.get(plan.digest) != step:
            raise RefusedActuation("sound step was not previewed for this plan")

        self._previous[plan.digest] = (
            copy.deepcopy(self._states.get(plan.target)),
            copy.deepcopy(self._results.get(plan.target)),
        )
        out = compose_sound(seed=step.seed, duration=step.duration_s, root=step.root_hz)
        if out.get("refused"):
            raise RefusedActuation("compose_sound refused: " + "; ".join(out.get("refusals") or []))
        receipt = copy.deepcopy(out["receipt"])
        self._results[plan.target] = copy.deepcopy(out)
        self._states[plan.target] = {
            "present": True,
            "target": plan.target,
            "client_action_id": step.client_action_id,
            "model_route_ref": step.model_route_ref,
            "observation_ref": step.observation_ref,
            "capture_session_ref": step.capture_session_ref,
            "latest_frame_ref": step.latest_frame_ref,
            "audio": {
                "wav_sha256": receipt["wav_sha256"],
                "score_sha256": receipt["score_sha256"],
                "duration_s": receipt["duration_s"],
                "root_hz": receipt["root_hz"],
            },
            "receipt": receipt,
        }
        return self.perceive(plan.target)

    def verify(self, plan: Any, after: Any):
        from accountable_surface.effector import Verdict

        result = self._results.get(plan.target)
        state = ((after.data if after is not None else {}) or {}).get("state", {})
        receipt = state.get("receipt") if isinstance(state, dict) else None
        if not result or not isinstance(receipt, dict):
            return Verdict("failed", "sound composition is absent after actuation")
        if receipt.get("wav_sha256") != result["receipt"].get("wav_sha256"):
            return Verdict("failed", "sound receipt does not match composed bytes")
        return Verdict("pass", "")

    def rollback(self, plan: Any) -> None:
        state, result = self._previous.get(plan.digest, (None, None))
        if state is None:
            self._states.pop(plan.target, None)
        else:
            self._states[plan.target] = state
        if result is None:
            self._results.pop(plan.target, None)
        else:
            self._results[plan.target] = result

    def last_result(self, target: str) -> dict[str, Any] | None:
        result = self._results.get(target)
        return copy.deepcopy(result) if result is not None else None

    @staticmethod
    def _content_sha(step: SoundComposeStep) -> str:
        return hashlib.sha256(step.accountable_content_json().encode("utf-8")).hexdigest()


def make_studio_sound_exposed(effector: StudioBodySoundEffector | None = None):
    from accountable_surface.registry import Exposed

    return Exposed(
        SOUND_ACTION_KIND,
        effector or StudioBodySoundEffector(),
        _decode_sound_content,
        "Flywheel Studio sound composer via Accountable Surface remote_durable",
        describe_sound_read,
        lambda payload: ("before", "after", "rollback"),
    )


def studio_sound_read_scope(*, phases: tuple[str, ...] = ("before", "after", "rollback")) -> dict[str, Any]:
    return {
        "observation_kind": "api.resource",
        "phases": list(phases),
        "target_scope": {
            "kind": "api",
            "service": STUDIO_BODY_SERVICE,
            "origins": [STUDIO_BODY_ORIGIN],
            "intents": ["compose_sound"],
            "paths": [STUDIO_BODY_SOUND_PATH_SHAPE],
        },
    }


def describe_sound_read(target: str, payload: SoundComposeStep, phase: str, request_id: str):
    from accountable_surface.api_effector import ApiCall, ApiOperation, ApiService
    from accountable_surface.read_authority import describe_api_read

    service = ApiService(
        name=STUDIO_BODY_SERVICE,
        host="studio",
        auth_env="",
        scheme="flywheel",
        operations=(ApiOperation(
            intent="compose_sound",
            action_kind=SOUND_ACTION_KIND,
            method="POST",
            path_shape=STUDIO_BODY_SOUND_PATH_SHAPE,
        ),),
    )
    return describe_api_read(service, target, ApiCall("compose_sound", {}), phase, request_id)


def _decode_sound_content(content: str) -> SoundComposeStep:
    try:
        return parse_sound_content(content)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
