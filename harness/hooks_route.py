"""hooks_route.py -- accountable hook management routes.

GET  /api/hooks                  list the registry
POST /api/hooks/register         exact-grant registration (write scope)
POST /api/hooks/run              exact-grant firing (exec scope)

Registration and firing are separate grants: registering automation and
executing it are different authorities. The registry lives under the
run root; firing uses the production argv runner with a hard timeout.
"""
from __future__ import annotations

import json
from pathlib import Path

from .accountable_hooks import (
    event_blocked,
    load_registry,
    register_hook,
    run_hooks,
    save_registry,
    subprocess_runner,
    validate_hook_run_plan,
)
from .evidence_public import TransportError, error_response
from .gateway_grant_route import authorize_gateway_operation, gateway_error_response
from .gateway_operation import GatewayOperationError, thaw_operation


def _invalid(message: str) -> tuple[dict, int]:
    return error_response(TransportError("INVALID_REQUEST", message, 422))


def _deny(message: str) -> tuple[dict, int]:
    return error_response(TransportError("PERMISSION_DENIED", message, 403))


def _conflict(message: str) -> tuple[dict, int]:
    return error_response(TransportError("REGISTRY_CONFLICT", message, 409))


def _registry_path(run_root: Path) -> Path:
    return Path(run_root) / "hooks" / "registry.json"


def handle_hooks_get(path: str, *, run_root: Path) -> tuple[dict, int]:
    if path == "/api/hooks":
        try:
            registry = load_registry(_registry_path(run_root))
        except ValueError as exc:
            return _invalid(str(exc))
        return {"schema": "flywheel.hook-registry/v1",
                "hooks": registry,
                "count": len(registry)}, 200
    return error_response(TransportError("NOT_FOUND", "unknown hook route",
                                         404))


def _action_for_path(path: str) -> str | None:
    return {"/api/hooks/register": "hook.register",
            "/api/hooks/run": "hook.run"}.get(path)


def _looks_ungranted(raw: bytes) -> bool:
    try:
        body = json.loads(raw or b"{}")
    except Exception:
        return False
    return (isinstance(body, dict) and "grant_ref" not in body
            and ("event" in body or "argv" in body or "hook_id" in body))


def handle_hooks_post(path: str, raw: bytes, *, run_root: Path,
                      owner_ref: str, state_root: Path,
                      clock) -> tuple[dict, int]:
    action = path.rsplit("/", 1)[-1]
    grant_action = _action_for_path(path)
    if grant_action is None:
        return error_response(TransportError("NOT_FOUND",
                                             "unknown hook route", 404))
    try:
        authorized = authorize_gateway_operation(
            grant_action, raw, owner_ref=owner_ref, state_root=state_root,
            clock=clock)
        body = thaw_operation(authorized.operation)
    except Exception as exc:
        if (getattr(exc, "code", "") == "INVALID_REQUEST"
                and _looks_ungranted(raw)):
            exc = GatewayOperationError("PERMISSION_REQUIRED")
        return gateway_error_response(exc)
    if action == "register":
        required = ("event", "argv", "blocking", "hook_id")
        if any(not body.get(field) and body.get(field) is not False
               for field in required):
            return _invalid("the registration is incomplete")
        try:
            reg = register_hook(
                event=body["event"], argv=body["argv"],
                blocking=bool(body["blocking"]),
                hook_id=body["hook_id"], created_at=clock())
        except ValueError as exc:
            return _invalid(str(exc))
        registry = load_registry(_registry_path(run_root))
        registry = [r for r in registry if r["hook_id"] != reg["hook_id"]]
        registry.append(reg)
        save_registry(registry, registry_path=_registry_path(run_root))
        return {"schema": "flywheel.hook-registration-ack/v1",
                "hook": reg, "registered_at": clock(),
                "hook_receipts": [], "event_blocked": False}, 200
    if action == "run":
        event = body.get("event")
        context = body.get("context")
        registrations = body.get("registrations")
        try:
            validate_hook_run_plan(event=event, registrations=registrations,
                                   context=context)
        except ValueError as exc:
            return _invalid(str(exc))
        try:
            registry = load_registry(_registry_path(run_root))
        except ValueError as exc:
            return _conflict(str(exc))
        current = [r for r in registry if r["event"] == event]
        if current != registrations:
            return _conflict("approved hook registry snapshot changed")
        receipts = run_hooks(event, registrations,
                             runner=subprocess_runner(timeout_s=30.0),
                             context=context)
        return {"schema": "flywheel.hook-event-run/v1",
                "event": event,
                "hook_receipts": receipts,
                "event_blocked": event_blocked(receipts)}, 200
    return error_response(TransportError("NOT_FOUND", "unknown hook route",
                                         404))
