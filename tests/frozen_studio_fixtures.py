"""Synthetic HTTP responses for frozen Studio acceptance controls."""
import base64
import copy
import hashlib
import json

ENGINE_ACTION_KIND = "flywheel.studio.engine.render-world/v1"
ENGINE_TARGET = "flywheel://studio/engine/session-1/visual-1"
CONTRACT_VERSION = "flywheel.studio.body/v1"
_PNG_BYTES = b"\x89PNG\r\n\x1a\nstudio-frame"
_PNG_SHA256 = hashlib.sha256(_PNG_BYTES).hexdigest()
_LEGACY_ARTIFACT_SHA = _PNG_SHA256[:16]


class _StudioStub:
    def __init__(self, *, corrupt_frame_hash: bool = False,
                 accept_ungranted: bool = False,
                 accept_exhausted: bool = False,
                 accept_off_target: bool = False,
                 artifact_mode: str | None = None):
        self.corrupt_frame_hash = corrupt_frame_hash
        self.accept_ungranted = accept_ungranted
        self.accept_exhausted = accept_exhausted
        self.accept_off_target = accept_off_target
        self.artifact_mode = artifact_mode
        self.calls: list[tuple[str, str | None, dict | None]] = []
        self.engine_bodies: list[dict] = []

    def request(self, _base: str, path: str, token: str | None, *,
                body: dict | None = None,
                secret_values: tuple[str, ...] = ()) -> tuple[int, dict]:
        self.calls.append((path, token, body))
        response = self._response(path, token, body)
        response_text = json.dumps(response[1], sort_keys=True)
        for secret in secret_values:
            assert not secret or secret not in response_text
        return response

    def _response(self, path: str, token: str | None,
                  body: dict | None) -> tuple[int, dict]:
        if path == "/api/studio/body/status" and token is None:
            return 401, {"error": {"code": "AUTH_REQUIRED"}}
        if path == "/api/studio/body/status":
            return 200, {
                "schema": "flywheel.studio.body.status/v1",
                "body_contract_version": CONTRACT_VERSION,
                "backend_ready": False,
                "unavailable_reason": "configured_unverified",
                "built": {
                    "routes": True,
                    "snapshot_contract": True,
                    "sound_effector": True,
                    "engine_visual_effector": True,
                    "live_screen_preview_gateway": True,
                },
                "verified": {
                    "usable_grant": False,
                    "effectors": [],
                    "status": "deferred_until_step",
                },
                "authority": {
                    "configured": True,
                    "available": True,
                    "grant_required": True,
                    "grant_verified": False,
                    "required_env": [
                        "ACCOUNTABLE_SURFACE_GRANTS",
                        "ACCOUNTABLE_SURFACE_AUTHORITY_STATE",
                    ],
                },
                "routes": {
                    "status": "/api/studio/body/status",
                    "snapshot": "/api/studio/body/snapshot",
                    "step": "/api/studio/body/step",
                },
            }
        if path == "/api/studio/body/step" and isinstance(body, dict):
            action = body.get("action") if isinstance(body.get("action"), dict) else {}
            if action.get("kind") != ENGINE_ACTION_KIND or action.get("target") != ENGINE_TARGET:
                if (action.get("kind") == ENGINE_ACTION_KIND and
                        action.get("target") != ENGINE_TARGET and self.accept_off_target):
                    return 200, self._accepted(body)
                if self.accept_ungranted:
                    return 200, self._accepted(body)
                return 403, {
                    "schema": "flywheel.studio.body.step-response/v1",
                    "accepted": False,
                    "status": "deny",
                    "action_kind": action.get("kind"),
                    "target": action.get("target"),
                    "receipt": None,
                    "authority_receipt": {
                        "decision": "deny",
                        "acted": False,
                        "verified": False,
                        "authority_state": {"usage_counted": 0},
                    },
                    "errors": ["grant_scope_refused"],
                }
            self.engine_bodies.append(body)
            if len(self.engine_bodies) > 1 and not self.accept_exhausted:
                return 403, {
                    "schema": "flywheel.studio.body.step-response/v1",
                    "accepted": False,
                    "status": "deny",
                    "action_kind": action.get("kind"),
                    "target": action.get("target"),
                    "receipt": None,
                    "authority_receipt": {
                        "decision": "deny",
                        "acted": False,
                        "verified": False,
                        "authority_state": {"usage_counted": 1},
                    },
                    "errors": ["action_budget_exhausted"],
                }
            return 200, self._accepted(body)
        raise AssertionError(path)

    def _accepted(self, body: dict) -> dict:
        out = {
            "schema": "flywheel.studio.body.step-response/v1",
            "accepted": True,
            "status": "accepted",
            "action_kind": body["action"]["kind"],
            "target": body["action"]["target"],
            "receipt": {
                "schema": "flywheel.studio.body.engine-render-receipt/v1",
                "world_id": "world-smoke",
                "frame_count": 1,
                "frames": [{
                    "sha256": _LEGACY_ARTIFACT_SHA,
                    "frame_sha256": _PNG_SHA256,
                    "png_base64": base64.b64encode(_PNG_BYTES).decode("ascii"),
                    "delivery_receipt": {"frame_sha256": _PNG_SHA256},
                }],
                "engine_receipt": {"artifact_shas": [_LEGACY_ARTIFACT_SHA]},
            },
            "authority_receipt": {
                "decision": "allow",
                "acted": True,
                "verified": True,
                "authority_state": {"usage_counted": 1},
                "reasons": [],
            },
            "errors": [],
        }
        if self.corrupt_frame_hash:
            corrupted = copy.deepcopy(out)
            corrupted["receipt"]["frames"][0]["frame_sha256"] = "0" * 64
            return corrupted
        if self.artifact_mode == "missing_sha":
            out["receipt"]["frames"][0].pop("sha256")
        elif self.artifact_mode == "missing_artifact_shas":
            out["receipt"]["engine_receipt"].pop("artifact_shas")
        elif self.artifact_mode == "artifact_shas_not_list":
            out["receipt"]["engine_receipt"]["artifact_shas"] = _LEGACY_ARTIFACT_SHA
        elif self.artifact_mode == "nonhex_legacy":
            out["receipt"]["frames"][0]["sha256"] = "legacy-artifact"
            out["receipt"]["engine_receipt"]["artifact_shas"] = ["legacy-artifact"]
        elif self.artifact_mode == "artifact_not_member":
            out["receipt"]["engine_receipt"]["artifact_shas"] = ["0" * 16]
        return out
