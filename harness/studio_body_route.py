"""Gateway handlers for the Studio programmatic body."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from harness.studio_body_contract import (
    CONTRACT_VERSION,
    SOUND_ACTION_KIND,
    BodyContractError,
    build_body_snapshot,
    parse_body_step,
)
from harness.studio_body_engine import (
    ENGINE_ACTION_KIND,
    StudioBodyEngineEffector,
    make_studio_engine_exposed,
    parse_engine_body_step,
)
from harness.studio_body_live_screen import (
    capture_claim_problem,
    capture_request_from_body,
    capture_snapshot_evidence,
)
from harness.studio_body_route_status import body_step_status
from harness.studio_body_sound import StudioBodySoundEffector, make_studio_sound_exposed

AUTHORITY_GRANTS_ENV = "ACCOUNTABLE_SURFACE_GRANTS"
AUTHORITY_STATE_ENV = "ACCOUNTABLE_SURFACE_AUTHORITY_STATE"
AUTHORITY_JOURNAL_ENV = "ACCOUNTABLE_SURFACE_JOURNAL"


def handle_body_get(path: str) -> tuple[dict[str, Any], int]:
    if path == "/api/studio/body/status":
        return handle_body_status_get()
    return _invalid("unknown Studio body GET route"), 404


def handle_body_post(path: str, body: Any, *, clock=None, capture_manager=None,
                     capture_scheduler=None, owner_ref: str | None = None,
                     now_ns: int | None = None) -> tuple[dict[str, Any], int]:
    if path == "/api/studio/body/snapshot":
        return handle_body_snapshot_post(
            body, clock=clock, capture_manager=capture_manager,
            capture_scheduler=capture_scheduler, owner_ref=owner_ref, now_ns=now_ns)
    if path == "/api/studio/body/step":
        return handle_body_step_post(
            body, clock=clock, capture_manager=capture_manager,
            capture_scheduler=capture_scheduler, owner_ref=owner_ref, now_ns=now_ns)
    return _invalid("unknown Studio body POST route"), 404


def handle_body_gateway_post(path: str, body: Any, handler) -> tuple[dict[str, Any], int]:
    from harness.live_screen_gateway_mount import live_screen_components
    manager, scheduler = live_screen_components(handler)
    return handle_body_post(
        path, body, clock=handler.clock, capture_manager=manager,
        capture_scheduler=scheduler, owner_ref=handler.owner_ref)


def handle_body_status_get() -> tuple[dict[str, Any], int]:
    authority = _authority_probe()
    return {
        "schema": "flywheel.studio.body.status/v1",
        "body_contract_version": CONTRACT_VERSION,
        "backend_ready": False,
        "unavailable_reason": authority["verification_status"],
        "available_effectors": [],
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
            "status": "deferred_until_step" if authority["configured"] else authority["verification_status"],
        },
        "delivery_modes": ["deterministic_text_controls", "image_frame_refs"],
        "authority": {
            "mode": "accountable_surface_remote_durable",
            "configured": authority["configured"],
            "available": authority["available"],
            "grant_required": True,
            "grant_verified": False,
            "required_env": [AUTHORITY_GRANTS_ENV, AUTHORITY_STATE_ENV],
        },
        "screen_feed": {
            "capture_session_ref": None,
            "preview_available": False,
            "native_video": "unavailable_from_body_route",
            "latest_frame_ref": None,
            "latest_delivered_frame_age_ms": None,
        },
        "routes": {
            "status": "/api/studio/body/status",
            "snapshot": "/api/studio/body/snapshot",
            "step": "/api/studio/body/step",
            "live_screen_preview": "/api/live-screen/sessions/{session}/sources/{source}/frames/{sequence}/preview",
        },
    }, 200


def handle_body_snapshot_post(body: Any, *, clock=None, capture_manager=None,
                              capture_scheduler=None, owner_ref: str | None = None,
                              now_ns: int | None = None) -> tuple[dict[str, Any], int]:
    try:
        session_ref = _field(body, "session_ref")
        instrument_ref = _field(body, "instrument_ref")
        out = build_body_snapshot(
            session_ref,
            instrument_ref,
            capture_request=capture_request_from_body(body),
            capture_evidence=capture_snapshot_evidence(
                session_ref, instrument_ref, body, capture_manager=capture_manager,
                capture_scheduler=capture_scheduler, owner_ref=owner_ref, now_ns=now_ns),
            now=clock,
        )
    except BodyContractError as exc:
        return _invalid(str(exc)), 400
    return out, 200


def handle_body_step_post(body: Any, *, clock=None, capture_manager=None,
                          capture_scheduler=None, owner_ref: str | None = None,
                          now_ns: int | None = None) -> tuple[dict[str, Any], int]:
    try:
        step = _parse_body_step(body)
    except BodyContractError as exc:
        return _step_response(False, "invalid_request", errors=[str(exc)]), 400

    action_kind = _step_action_kind(step)
    capture_problem = capture_claim_problem(
        step, capture_manager=capture_manager, capture_scheduler=capture_scheduler,
        owner_ref=owner_ref, now_ns=now_ns)
    if capture_problem:
        return _step_response(
            False, "capture_evidence_unverified", action_kind=action_kind,
            target=step.target, errors=[capture_problem],
        ), 503

    configured, reason = _authority_configured()
    if not configured:
        return _step_response(
            False,
            "authority_unconfigured",
            action_kind=action_kind,
            target=step.target,
            errors=[reason],
        ), 503
    return _run_accountable_step(step)


def _run_accountable_step(step) -> tuple[dict[str, Any], int]:
    try:
        _add_optional_source_paths()
        from accountable_surface.authority_store import AuthorityStore
        from accountable_surface.registry import EffectorRegistry
        from accountable_surface.remote_actuation import actuate_impl
        from accountable_surface.surface import AccountableSurface
    except Exception as exc:
        return _step_response(
            False, "authority_unavailable", action_kind=SOUND_ACTION_KIND,
            target=step.target, errors=[type(exc).__name__],
        ), 503

    action_kind, effector, exposed = _effector_for_step(step)
    store = AuthorityStore(
        os.environ.get(AUTHORITY_GRANTS_ENV),
        authority_state_path=os.environ.get(AUTHORITY_STATE_ENV),
        journal_path=os.environ.get(AUTHORITY_JOURNAL_ENV),
    )
    surface = AccountableSurface(journal_path=os.environ.get(AUTHORITY_JOURNAL_ENV))
    registry = EffectorRegistry({action_kind: exposed}, [])
    out = actuate_impl(
        surface,
        store,
        registry,
        action_kind,
        step.target,
        step.accountable_content_json(),
        idempotency_key=step.idempotency_key,
    )
    accepted = out.get("decision") == "allow" and out.get("acted") is True and out.get("verified") is True
    errors = list(out.get("reasons") or [])
    status, code = body_step_status(accepted, out, errors)
    return _step_response(
        accepted,
        status,
        action_kind=action_kind,
        target=step.target,
        receipt=effector.last_result(step.target),
        authority_receipt=_authority_receipt(out),
        errors=errors,
    ), code


def _parse_body_step(body: Any):
    action = body.get("action") if isinstance(body, dict) else None
    kind = action.get("kind") if isinstance(action, dict) else None
    if kind == SOUND_ACTION_KIND:
        return parse_body_step(body)
    if kind == ENGINE_ACTION_KIND:
        return parse_engine_body_step(body)
    raise BodyContractError(f"action.kind must be {SOUND_ACTION_KIND} or {ENGINE_ACTION_KIND}")


def _step_action_kind(step) -> str:
    return getattr(step, "action_kind", SOUND_ACTION_KIND)


def _effector_for_step(step):
    if _step_action_kind(step) == ENGINE_ACTION_KIND:
        effector = StudioBodyEngineEffector()
        return ENGINE_ACTION_KIND, effector, make_studio_engine_exposed(effector)
    effector = StudioBodySoundEffector()
    return SOUND_ACTION_KIND, effector, make_studio_sound_exposed(effector)


def _authority_configured() -> tuple[bool, str]:
    _add_optional_source_paths()
    try:
        import accountable_surface.authority_store  # noqa: F401
        import accountable_surface.remote_actuation  # noqa: F401
    except Exception:
        return False, "accountable_surface_unavailable"
    grants = os.environ.get(AUTHORITY_GRANTS_ENV)
    if not grants:
        return False, "authority_unconfigured"
    if not Path(grants).is_file():
        return False, "authority_grants_unreadable"
    if not os.environ.get(AUTHORITY_STATE_ENV):
        return False, "authority_state_unconfigured"
    return True, ""


def _authority_probe() -> dict[str, Any]:
    configured, reason = _authority_configured()
    return {
        "available": reason != "accountable_surface_unavailable",
        "configured": configured,
        "configuration_status": "configured" if configured else reason,
        "verification_status": "configured_unverified" if configured else reason,
    }


def _add_optional_source_paths() -> None:
    for name in ("COHERENCE_MEMBRANE_SRC", "PROOF_SURFACE_SRC", "ACCOUNTABLE_SURFACE_SRC"):
        value = os.environ.get(name)
        if value and value not in sys.path:
            sys.path.insert(0, value)


def _authority_receipt(out: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision": out.get("decision"),
        "acted": out.get("acted"),
        "verified": out.get("verified"),
        "verdict": out.get("verdict"),
        "rolled_back": out.get("rolled_back"),
        "reasons": list(out.get("reasons") or []),
        "authority_state": out.get("authority_state"),
        "journal_entry": out.get("journal_entry"),
    }


def _step_response(
    accepted: bool,
    status: str,
    *,
    action_kind: str | None = None,
    target: str | None = None,
    receipt: dict[str, Any] | None = None,
    authority_receipt: dict[str, Any] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema": "flywheel.studio.body.step-response/v1",
        "accepted": accepted,
        "status": status,
        "action_kind": action_kind,
        "target": target,
        "receipt": receipt,
        "authority_receipt": authority_receipt,
        "errors": errors or [],
    }


def _invalid(message: str) -> dict[str, Any]:
    return {"schema": "flywheel.studio.body.error/v1", "error": message}


def _field(body: Any, name: str) -> Any:
    return body.get(name) if isinstance(body, dict) else None
