"""Contracts shared by the frozen Studio gateway smoke helper."""
from __future__ import annotations
import base64
from dataclasses import dataclass
import hashlib, json
from pathlib import Path
import re
AUTHORITY_GRANTS_ENV = "ACCOUNTABLE_SURFACE_GRANTS"
AUTHORITY_STATE_ENV = "ACCOUNTABLE_SURFACE_AUTHORITY_STATE"
AUTHORITY_JOURNAL_ENV = "ACCOUNTABLE_SURFACE_JOURNAL"
CONTRACT_VERSION = "flywheel.studio.body/v1"
ENGINE_ACTION_KIND = "flywheel.studio.engine.render-world/v1"
ENGINE_TARGET_PREFIX = "flywheel://studio/engine/"
ENGINE_TARGET = ENGINE_TARGET_PREFIX + "session-1/visual-1"
ENGINE_TARGET_RESOURCE = "/engine/session-1/visual-1"
OFF_TARGET_ENGINE_TARGET = ENGINE_TARGET_PREFIX + "session-1/visual-2"
SOUND_ACTION_KIND = "flywheel.studio.sound.compose/v1"
SOUND_TARGET = "flywheel://studio/sound/session-1/instrument-1"
STATUS_ROUTE = "/api/studio/body/status"
STEP_ROUTE = "/api/studio/body/step"
SUMMARY_SCHEMA = "flywheel.frozen-gateway-studio-smoke/v1"
STEP_SCHEMA = "flywheel.studio.body.step-response/v1"
RENDER_RECEIPT_SCHEMA = "flywheel.studio.body.engine-render-receipt/v1"
EXPECTED_AUTHORITY = {
    "decision": "allow", "acted": True, "verified": True, "usage_counted": 1}
UNVERIFIED = ["semantic_render_criteria"]
SUMMARY_KEYS = {
    "schema", "unauthenticated_status", "status", "ungranted_action_status",
    "off_target_action_status", "exhausted_action_status", "accepted",
    "action_kind", "target", "world_id", "frame_count", "first_frame_sha256",
    "authority", "exact_scope_checked", "routes", "unverified"}
STATUS_KEYS = {
    "backend_ready", "authority_configured", "authority_available",
    "verified_status"}
AUTHORITY_KEYS = {"decision", "acted", "verified", "usage_counted"}
_RAW_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_LEGACY_ID = re.compile(r"^[0-9a-f]{16}$")
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
@dataclass(frozen=True)
class StudioSmokeFixture:
    home: Path; grants_path: Path; state_path: Path; journal_path: Path; env: dict[str, str]
def require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)
def prepare_studio_smoke_fixture(home: Path) -> StudioSmokeFixture:
    home = Path(home).resolve()
    home.mkdir(parents=True, exist_ok=True)
    grants_path = home / "studio-authority-grants.json"
    state_path = home / "studio-authority-state.sqlite3"
    journal_path = home / "studio-authority-journal.jsonl"
    require(not any(p.exists() for p in (grants_path, state_path, journal_path)),
            "STUDIO_FIXTURE_EXISTS")
    grants_path.write_text(
        json.dumps([_studio_engine_grant()], indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    return StudioSmokeFixture(home, grants_path, state_path, journal_path, {
        AUTHORITY_GRANTS_ENV: str(grants_path),
        AUTHORITY_STATE_ENV: str(state_path),
        AUTHORITY_JOURNAL_ENV: str(journal_path),
    })
def validate_studio_smoke_summary(summary: dict) -> None:
    require(type(summary) is dict and set(summary) == SUMMARY_KEYS,
            "STUDIO_SUMMARY_KEYS")
    require(summary.get("schema") == SUMMARY_SCHEMA, "STUDIO_SUMMARY_SCHEMA")
    status, authority = summary["status"], summary["authority"]
    require(type(status) is dict and set(status) == STATUS_KEYS,
            "STUDIO_SUMMARY_STATUS_KEYS")
    require(type(authority) is dict and set(authority) == AUTHORITY_KEYS,
            "STUDIO_SUMMARY_AUTHORITY_KEYS")
    require(summary["unauthenticated_status"] == 401, "STUDIO_SUMMARY_AUTH")
    require(status["backend_ready"] is False, "STUDIO_SUMMARY_STATUS")
    require(status["authority_configured"] is True
            and status["authority_available"] is True,
            "STUDIO_SUMMARY_AUTHORITY_STATUS")
    require(summary["ungranted_action_status"] == 403
            and summary["off_target_action_status"] == 403
            and summary["exhausted_action_status"] == 403,
            "STUDIO_SUMMARY_REFUSALS")
    require(summary["exact_scope_checked"] is True, "STUDIO_SUMMARY_SCOPE")
    require(summary["accepted"] is True and summary["action_kind"] == ENGINE_ACTION_KIND,
            "STUDIO_SUMMARY_ACCEPTED")
    require(summary["target"] == ENGINE_TARGET, "STUDIO_SUMMARY_TARGET")
    require(isinstance(summary["world_id"], str) and summary["world_id"],
            "STUDIO_SUMMARY_WORLD")
    require(type(summary["frame_count"]) is int and summary["frame_count"] > 0,
            "STUDIO_SUMMARY_FRAME_COUNT")
    require(_is_sha256(summary["first_frame_sha256"]), "STUDIO_SUMMARY_FRAME_HASH")
    require(authority == EXPECTED_AUTHORITY, "STUDIO_SUMMARY_AUTHORITY")
    require(type(summary["routes"]) is list and STATUS_ROUTE in summary["routes"]
            and STEP_ROUTE in summary["routes"], "STUDIO_SUMMARY_ROUTE_MISSING")
    require(summary["unverified"] == UNVERIFIED, "STUDIO_SUMMARY_UNVERIFIED")
def validate_fixture(fixture: StudioSmokeFixture) -> None:
    require(isinstance(fixture, StudioSmokeFixture), "STUDIO_FIXTURE")
    require(fixture.grants_path.is_file(), "STUDIO_GRANTS_MISSING")
    for key, path in ((AUTHORITY_GRANTS_ENV, fixture.grants_path),
                      (AUTHORITY_STATE_ENV, fixture.state_path),
                      (AUTHORITY_JOURNAL_ENV, fixture.journal_path)):
        require(fixture.env.get(key) == str(path), "STUDIO_FIXTURE_ENV")
def validate_status(status: dict) -> None:
    require(status.get("schema") == "flywheel.studio.body.status/v1",
            "STUDIO_STATUS_SCHEMA")
    require(status.get("body_contract_version") == CONTRACT_VERSION,
            "STUDIO_STATUS_CONTRACT")
    built, authority = status.get("built"), status.get("authority")
    require(isinstance(built, dict) and built.get("engine_visual_effector") is True,
            "STUDIO_ENGINE_NOT_BUILT")
    require(isinstance(authority, dict), "STUDIO_AUTHORITY_STATUS")
    require(authority.get("configured") is True and authority.get("available") is True,
            "STUDIO_AUTHORITY_NOT_CONFIGURED")
    require(authority.get("grant_required") is True
            and authority.get("grant_verified") is False,
            "STUDIO_AUTHORITY_HONESTY")
    require({AUTHORITY_GRANTS_ENV, AUTHORITY_STATE_ENV}
            <= set(authority.get("required_env") or []), "STUDIO_AUTHORITY_ENV")
    verified, routes = status.get("verified"), status.get("routes")
    require(isinstance(verified, dict)
            and verified.get("status") == "deferred_until_step",
            "STUDIO_STATUS_NOT_DEFERRED")
    require(status.get("backend_ready") is False, "STUDIO_STATUS_READY_CLAIM")
    require(isinstance(routes, dict) and routes.get("status") == STATUS_ROUTE
            and routes.get("step") == STEP_ROUTE, "STUDIO_ROUTES")
def validate_authority(value: object) -> dict:
    require(isinstance(value, dict), "STUDIO_AUTHORITY_RECEIPT")
    state = value.get("authority_state")
    require(isinstance(state, dict), "STUDIO_AUTHORITY_STATE")
    authority = {"decision": value.get("decision"), "acted": value.get("acted"),
                 "verified": value.get("verified"),
                 "usage_counted": state.get("usage_counted")}
    require(authority == EXPECTED_AUTHORITY, "STUDIO_AUTHORITY_RECEIPT")
    return authority
def validate_engine_receipt(value: object) -> tuple[str, int]:
    require(isinstance(value, dict), "STUDIO_RECEIPT")
    require(value.get("schema") == RENDER_RECEIPT_SCHEMA, "STUDIO_RECEIPT_SCHEMA")
    require(isinstance(value.get("world_id"), str) and value["world_id"],
            "STUDIO_WORLD_ID")
    frame_count, frames = value.get("frame_count"), value.get("frames")
    require(type(frame_count) is int and frame_count > 0, "STUDIO_FRAME_COUNT")
    require(type(frames) is list and len(frames) == frame_count,
            "STUDIO_FRAME_COUNT")
    engine_receipt = value.get("engine_receipt")
    artifact_shas = engine_receipt.get("artifact_shas") if isinstance(engine_receipt, dict) else None
    require(type(artifact_shas) is list and artifact_shas, "STUDIO_FRAME_ARTIFACT_HASH")
    require(all(_is_legacy_id(item) for item in artifact_shas),
            "STUDIO_FRAME_ARTIFACT_HASH")
    first_hash = ""
    for index, frame in enumerate(frames):
        actual = _validate_frame(frame, set(artifact_shas))
        if index == 0:
            first_hash = actual
    return first_hash, frame_count
def status_summary(status: dict) -> dict:
    return {
        "backend_ready": status.get("backend_ready"),
        "authority_configured": status.get("authority", {}).get("configured"),
        "authority_available": status.get("authority", {}).get("available"),
        "verified_status": status.get("verified", {}).get("status"),
    }
def engine_render_body(index: int = 1) -> dict:
    return _body(ENGINE_ACTION_KIND, ENGINE_TARGET, {
        "seed": 7, "generator": "gyroid", "scheme": "analogous",
        "max_steps": 4, "target": 0.9, "floor": 0.6, "render_frames": True,
    }, client=f"client-frozen-studio-engine-{index}",
        text="render a bounded gyroid world")
def off_target_engine_render_body() -> dict:
    return _body(ENGINE_ACTION_KIND, OFF_TARGET_ENGINE_TARGET, {
        "seed": 9, "generator": "gyroid", "scheme": "analogous",
        "max_steps": 4, "target": 0.9, "floor": 0.6, "render_frames": True,
    }, client="client-frozen-studio-engine-off-target",
        text="attempt a valid render outside the grant target")
def ungranted_sound_body() -> dict:
    return _body(SOUND_ACTION_KIND, SOUND_TARGET, {
        "seed": 8, "duration_s": 6.0, "root_hz": 220.0,
    }, client="client-frozen-studio-ungranted-1",
        text="attempt an ungranted sound action")
def _validate_frame(frame: object, artifact_shas: set[str]) -> str:
    require(isinstance(frame, dict), "STUDIO_FRAME_SHAPE")
    raw = _decode_frame_png(frame.get("png_base64"))
    actual, claimed = hashlib.sha256(raw).hexdigest(), frame.get("frame_sha256")
    require(_is_sha256(claimed) and actual == claimed, "STUDIO_FRAME_HASH")
    receipt = frame.get("delivery_receipt")
    if isinstance(receipt, dict) and "frame_sha256" in receipt:
        require(receipt.get("frame_sha256") == claimed, "STUDIO_FRAME_RECEIPT_HASH")
    artifact = frame.get("sha256")
    require(_is_legacy_id(artifact), "STUDIO_FRAME_ARTIFACT_HASH")
    require(artifact in artifact_shas, "STUDIO_FRAME_ARTIFACT_HASH")
    return actual
def _decode_frame_png(value: object) -> bytes:
    require(isinstance(value, str) and bool(value), "STUDIO_FRAME_BASE64")
    try:
        raw = base64.b64decode(value, validate=True)
    except Exception as exc:
        raise RuntimeError("STUDIO_FRAME_BASE64") from exc
    require(raw.startswith(_PNG_SIGNATURE) and len(raw) > len(_PNG_SIGNATURE),
            "STUDIO_FRAME_PNG")
    return raw
def _body(action_kind: str, target: str, args: dict, *, client: str, text: str) -> dict:
    return {
        "schema": CONTRACT_VERSION,
        "client_action_id": client,
        "idempotency_key": "idem-" + client,
        "model_route_ref": "deterministic-stub/v1",
        "observation_ref": "obs_" + client.replace("-", "_"),
        "action": {"kind": action_kind, "target": target, "args": args},
        "model_delivery": {"parts": [{"kind": "text", "text": text}]},
    }
def _studio_engine_grant() -> dict:
    return {
        "authorization_version": "0.1",
        "receipt_id": "rcpt-frozen-studio-engine",
        "kind": "authorization-grant",
        "principal": {"id": "operator-1", "role": "operator"},
        "agent": {"id": "frozen-studio-smoke"},
        "intent": "render one bounded Studio Engine visual world",
        "scope": {
            "allowed_actions": [ENGINE_ACTION_KIND],
            "allowed_targets": [ENGINE_TARGET],
            "allowed_reads": [_studio_engine_read_scope()],
            "allowed_bounds": [{
                "kind": "api", "origins": ["flywheel://studio"],
                "intents": ["render_world"]}],
            "max_actions": 1,
        },
        "granted_at": "2026-09-15T00:00:00+00:00",
        "expires_at": "2030-01-01T00:00:00+00:00",
        "revoked": False,
    }
def _studio_engine_read_scope() -> dict:
    return {
        "observation_kind": "api.resource",
        "phases": ["before", "after", "rollback"],
        "target_scope": {
            "kind": "api", "service": "flywheel-studio-body",
            "origins": ["flywheel://studio"], "intents": ["render_world"],
            "paths": [ENGINE_TARGET_RESOURCE],
        },
    }
def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _RAW_SHA256.fullmatch(value) is not None
def _is_legacy_id(value: object) -> bool:
    return isinstance(value, str) and _LEGACY_ID.fullmatch(value) is not None
