"""Private route for provider-neutral continuation previews and Journey start."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .continuation_context import PRIVATE_CONTEXT_SCHEMA
from .continuation_preview import build_continuation
from .continuation_replay import ack_from_record, matching_request_event
from .continuation_store import intake_ref, load_preview, load_start_binding, start_lock, write_preview, write_start_binding
from .evidence_public import TransportError, error_response, exact_request, parse_json
from .grant_route import grant_post
from .journey_route import journey_post
from .journey_store import JourneyStore, JourneyStoreError
from .journey_types import JOURNEY_REF_PATTERN, SHA256_PATTERN

ROUTE_PREFIX = "/api/continuation/"
START_SCHEMA = "flywheel.native-continuation-start/v1"
UNDO_SCHEMA = "flywheel.native-continuation-undo/v1"

def _raw_json(value: dict) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode()

def _sha(value: object, name: str) -> str:
    if type(value) is not str or SHA256_PATTERN.fullmatch(value) is None:
        raise TransportError("INVALID_CONTINUATION", f"{name} is invalid", 422)
    return value

def _client_id(req: dict) -> str:
    value = req.get("client_request_id")
    if type(value) is not str or not value.strip():
        raise TransportError("INVALID_CONTINUATION", "client_request_id is invalid", 422)
    return value

def _root_from(req: dict, root: Path | None) -> Path:
    if type(req.get("root")) is not str or not req["root"].strip():
        raise TransportError("ROOT_UNAVAILABLE", "workspace root is unavailable")
    try:
        candidate = Path(root) if root is not None else Path(req["root"])
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise TransportError("ROOT_UNAVAILABLE", "workspace root is unavailable") from exc
    if not resolved.is_dir():
        raise TransportError("ROOT_UNAVAILABLE", "workspace root is unavailable")
    return resolved

def _export_from(req: dict) -> Path | None:
    value = req.get("export_path")
    if value is None:
        return None
    if type(value) is not str or not value.strip():
        raise TransportError("INVALID_CONTINUATION", "export_path is invalid", 422)
    return Path(value)

def _preview(req: dict, *, state_root: Path, root: Path | None) -> dict:
    exact_request(req, {"root", "export_path"}, optional={"export_path"})
    preview, intake = build_continuation(
        _root_from(req, root), export_path=_export_from(req))
    return write_preview(state_root, preview, intake)

def _recompute(stored: dict) -> dict:
    source = stored.get("source") if type(stored.get("source")) is dict else {}
    root = source.get("root")
    if type(root) is not str:
        raise TransportError("INVALID_CONTINUATION", "continuation preview is invalid", 422)
    export = source.get("export_path")
    preview, _ = build_continuation(
        Path(root), export_path=Path(export) if type(export) is str else None)
    return preview

def _ensure_current(req: dict, stored: dict) -> None:
    _sha(req.get("preview_sha256"), "preview_sha256")
    _sha(req.get("source_state_sha256"), "source_state_sha256")
    if (req["preview_sha256"] != stored.get("preview_sha256")
            or req["source_state_sha256"] != stored.get("source_state_sha256")):
        raise TransportError("PREVIEW_MISMATCH", "continuation preview does not match request", 409)
    current = _recompute(stored)
    if current.get("source_state_sha256") != stored.get("source_state_sha256"):
        raise TransportError("SOURCE_DRIFT", "source changed since continuation preview", 409)

def _recovery_action(stored: dict) -> dict:
    return {
        "action_id": "continue-" + stored["preview_ref"],
        "kind": "repair",
        "description": "Open the private continuation context and run the existing agent loop from the source-bound preview.",
        "basis_refs": [stored["preview_ref"], stored["intake_ref"]],
    }

def _recovery_request_id(req: dict) -> str:
    return req["client_request_id"] + ":recovery-action"

def _start_response(req: dict, journey: dict) -> dict:
    return {"schema": START_SCHEMA, "mode": "provider_neutral",
            "preview_ref": req["preview_ref"], "open_lens": "Rescue",
            "journey": journey,
            "does_not_prove": ["provider-native web session resume"]}

def _grant_and_run(action: str, request: dict, *, owner_ref: str,
                   state_root: Path, clock: Callable[[], str]) -> dict:
    evidence_root = state_root / "artifacts"
    proposed, status = grant_post(f"/api/grants/prepare/{action}", _raw_json(request),
        owner_ref=owner_ref, state_root=state_root, evidence_root=evidence_root,
        clock=clock)
    if status != 200:
        raise TransportError(proposed["error"]["code"], proposed["error"]["message"], status)
    approved, status = grant_post("/api/grants/approve-once",
        _raw_json({"proposal_ref": proposed["proposal_ref"]}), owner_ref=owner_ref,
        state_root=state_root, evidence_root=evidence_root, clock=clock)
    if status != 200:
        raise TransportError(approved["error"]["code"], approved["error"]["message"], status)
    journey, status = journey_post(f"/api/journeys/{action}",
        _raw_json({**request, "grant_ref": approved["grant_ref"]}),
        owner_ref=owner_ref, state_root=state_root, evidence_root=evidence_root,
        clock=clock)
    if status != 200:
        raise TransportError(journey["error"]["code"], journey["error"]["message"], status)
    return journey

def _private_context(req: dict, *, state_root: Path) -> dict:
    exact_request(req, {"preview_ref", "preview_sha256", "source_state_sha256"})
    stored = load_preview(state_root, req["preview_ref"])
    _ensure_current(req, stored)
    health = stored.get("health") if type(stored.get("health")) is dict else {}
    if health.get("state") != "ready":
        raise TransportError(
            "CONTINUATION_BLOCKED", "continuation source is incomplete", 409)
    context = stored.get("context_package")
    runner = stored.get("runner_context")
    if type(context) is not dict or type(runner) is not dict:
        raise TransportError("INVALID_CONTINUATION", "continuation preview is invalid", 422)
    return {"schema": PRIVATE_CONTEXT_SCHEMA, "mode": "provider_neutral",
            "preview_ref": stored["preview_ref"],
            "source_state_sha256": stored["source_state_sha256"],
            "context_package": context, "runner_context": runner,
            "does_not_prove": [
                "provider-native web session resume",
                "selected context is complete",
                "a model has executed the runner context"]}

def _start_replay(req: dict, *, goal: str, owner_ref: str,
                  state_root: Path) -> dict | None:
    found = matching_request_event(
        JourneyStore(state_root), owner_ref=owner_ref, journey_ref=None,
        request_id=req["client_request_id"])
    if found is None:
        return None
    record, event, events = found
    intake = event.get("payload", {}).get("intake")
    if (event.get("sequence") != 0 or event.get("event_type") != "intake"
            or event.get("payload", {}).get("goal") != goal
            or type(intake) is not dict
            or intake.get("preview_ref") != req["preview_ref"]
            or intake.get("preview_sha256") != req["preview_sha256"]):
        raise JourneyStoreError("IDEMPOTENCY_MISMATCH")
    stored = {"preview_ref": req["preview_ref"],
              "intake_ref": intake_ref(req["preview_ref"])}
    recovery = matching_request_event(
        JourneyStore(state_root), owner_ref=owner_ref,
        journey_ref=event["journey_ref"], request_id=_recovery_request_id(req))
    if recovery is None:
        return None
    recovery_record, recovery_event, recovery_events = recovery
    if (recovery_event.get("event_type") != "record_next_action"
            or recovery_event.get("payload") != {
                "next_actions": [_recovery_action(stored)]}):
        raise JourneyStoreError("IDEMPOTENCY_MISMATCH")
    return ack_from_record(recovery_record, recovery_event, recovery_events)

def _undo_replay(req: dict, *, owner_ref: str, state_root: Path) -> dict | None:
    found = matching_request_event(
        JourneyStore(state_root), owner_ref=owner_ref,
        journey_ref=req["journey_ref"], request_id=req["client_request_id"])
    if found is None:
        return None
    record, event, events = found
    expected_action = {"action_id": "undo-" + req["preview_ref"],
                       "kind": "rollback",
                       "description": "Review and detach this provider-neutral continuation package before another turn.",
                       "basis_refs": [req["preview_ref"]]}
    if (event.get("event_type") != "record_next_action"
            or event.get("prior_event_sha256") != req["expected_event_head"]
            or event.get("payload") != {"next_actions": [expected_action]}):
        raise JourneyStoreError("IDEMPOTENCY_MISMATCH")
    return ack_from_record(record, event, events)

def _start(req: dict, *, owner_ref: str, state_root: Path,
           clock: Callable[[], str]) -> dict:
    exact_request(req, {"preview_ref", "preview_sha256", "source_state_sha256",
                       "client_request_id", "goal"}, optional={"goal"})
    _client_id(req)
    goal = req.get("goal") or "Continue work with provider-neutral Flywheel context"
    with start_lock(state_root, owner_ref, req["preview_ref"],
                    req["client_request_id"]):
        stored = load_preview(state_root, req["preview_ref"])
        _sha(req.get("preview_sha256"), "preview_sha256")
        if req["preview_sha256"] != stored.get("preview_sha256"):
            raise TransportError("PREVIEW_MISMATCH", "continuation preview does not match request", 409)
        try:
            binding = load_start_binding(state_root, owner_ref, req["preview_ref"])
        except TransportError as exc:
            if exc.code != "CONTINUATION_NOT_STARTED":
                raise
        else:
            bound = {**req, "client_request_id": binding["start_client_request_id"]}
            replay = _start_replay(bound, goal=goal, owner_ref=owner_ref,
                                   state_root=state_root)
            if replay is None:
                raise JourneyStoreError("IDEMPOTENCY_MISMATCH")
            return _start_response(req, replay)
        replay = _start_replay(req, goal=goal, owner_ref=owner_ref,
                               state_root=state_root)
        if replay is not None:
            write_start_binding(state_root, stored, owner_ref, replay, req["client_request_id"], _recovery_request_id(req))
            return _start_response(req, replay)
        _ensure_current(req, stored)
        health = stored.get("health") if type(stored.get("health")) is dict else {}
        if health.get("state") != "ready":
            raise TransportError(
                "CONTINUATION_BLOCKED", "continuation source is incomplete", 409)
        create = {"goal": goal, "intake_ref": intake_ref(req["preview_ref"]),
                  "client_request_id": req["client_request_id"]}
        created = _grant_and_run("create", create, owner_ref=owner_ref,
                                 state_root=state_root, clock=clock)
        append = {"journey_ref": created["journey_ref"],
                  "expected_event_head": created["event_head_sha256"],
                  "client_request_id": _recovery_request_id(req),
                  "command": {"type": "record_next_action",
                              "next_action": _recovery_action(stored)}}
        journey = _grant_and_run("append", append, owner_ref=owner_ref,
                                 state_root=state_root, clock=clock)
        write_start_binding(state_root, stored, owner_ref, journey, req["client_request_id"], _recovery_request_id(req))
        return _start_response(req, journey)

def _undo(req: dict, *, owner_ref: str, state_root: Path,
          clock: Callable[[], str]) -> dict:
    exact_request(req, {"journey_ref", "expected_event_head", "preview_ref",
                       "preview_sha256", "client_request_id"})
    if type(req["journey_ref"]) is not str or JOURNEY_REF_PATTERN.fullmatch(req["journey_ref"]) is None:
        raise TransportError("INVALID_CONTINUATION", "journey_ref is invalid", 422)
    _sha(req.get("expected_event_head"), "expected_event_head")
    _sha(req.get("preview_sha256"), "preview_sha256")
    _client_id(req)
    stored = load_preview(state_root, req["preview_ref"])
    if req["preview_sha256"] != stored.get("preview_sha256"):
        raise TransportError("PREVIEW_MISMATCH", "continuation preview does not match request", 409)
    replay = _undo_replay(req, owner_ref=owner_ref, state_root=state_root)
    if replay is not None:
        return {"schema": UNDO_SCHEMA, "preview_ref": req["preview_ref"],
                "journey": replay}
    command = {"type": "record_next_action", "next_action": {
        "action_id": "undo-" + req["preview_ref"], "kind": "rollback",
        "description": "Review and detach this provider-neutral continuation package before another turn.",
        "basis_refs": [req["preview_ref"]]}}
    append = {"journey_ref": req["journey_ref"],
              "expected_event_head": req["expected_event_head"],
              "client_request_id": req["client_request_id"],
              "command": command}
    journey = _grant_and_run("append", append, owner_ref=owner_ref,
                             state_root=state_root, clock=clock)
    return {"schema": UNDO_SCHEMA, "preview_ref": req["preview_ref"],
            "journey": journey}

def handle_continuation_post(path: str, raw: bytes, *, owner_ref: str,
                             state_root: Path, root: Path | None = None,
                             clock: Callable[[], str]) -> tuple[dict, int]:
    try:
        if type(path) is not str or not path.startswith(ROUTE_PREFIX):
            raise TransportError("NOT_FOUND", "continuation route not found", 404)
        action = path[len(ROUTE_PREFIX):]
        if action not in {"preview", "start", "undo", "context"} or "/" in action:
            raise TransportError("NOT_FOUND", "continuation route not found", 404)
        req = parse_json(raw)
        if action == "preview":
            return _preview(req, state_root=state_root, root=root), 200
        if action == "context":
            return _private_context(req, state_root=state_root), 200
        if action == "start":
            return _start(req, owner_ref=owner_ref, state_root=state_root,
                          clock=clock), 200
        return _undo(req, owner_ref=owner_ref, state_root=state_root,
                     clock=clock), 200
    except TransportError as exc:
        return error_response(exc)
    except JourneyStoreError as exc:
        statuses = {"IDEMPOTENCY_MISMATCH": 409, "STORE_BUSY": 503,
                    "STORE_COMMIT_FAILED": 500, "VERSION_MISMATCH": 409,
                    "JOURNEY_NOT_FOUND": 404}
        return error_response(TransportError(
            exc.code, "continuation replay is unavailable",
            statuses.get(exc.code, 500)))
    except Exception as exc:
        return error_response(TransportError(
            "STORE_COMMIT_FAILED", "continuation operation failed", 500))
