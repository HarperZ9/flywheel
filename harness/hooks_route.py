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
)
from .evidence_public import TransportError, error_response


def _invalid(message: str) -> tuple[dict, int]:
    return error_response(TransportError("INVALID_REQUEST", message, 422))


def _deny(message: str) -> tuple[dict, int]:
    return error_response(TransportError("PERMISSION_DENIED", message, 403))


def _registry_path(run_root: Path) -> Path:
    return Path(run_root) / "hooks" / "registry.json"


def handle_hooks_get(path: str, *, run_root: Path) -> tuple[dict, int]:
    if path == "/api/hooks":
        registry = load_registry(_registry_path(run_root))
        return {"schema": "flywheel.hook-registry/v1",
                "hooks": registry,
                "count": len(registry)}, 200
    return error_response(TransportError("NOT_FOUND", "unknown hook route",
                                         404))


def handle_hooks_post(path: str, body: dict, *, run_root: Path,
                      owner_ref: str, clock) -> tuple[dict, int]:
    action = path.rsplit("/", 1)[-1]
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
        # Fire hook.registered so registration itself is observable.
        receipts = run_hooks("hook.registered", registry,
                             runner=subprocess_runner(timeout_s=15.0),
                             context={"hook_id": reg["hook_id"],
                                      "event": reg["event"]})
        return {"schema": "flywheel.hook-registration-ack/v1",
                "hook": reg, "registered_at": clock(),
                "hook_receipts": receipts,
                "event_blocked": event_blocked(receipts)}, 200
    if action == "run":
        event = body.get("event", "")
        context = body.get("context", {})
        if not event:
            return _invalid("the event to fire is required")
        registry = load_registry(_registry_path(run_root))
        receipts = run_hooks(event, registry,
                             runner=subprocess_runner(timeout_s=30.0),
                             context=context if isinstance(context, dict)
                             else {})
        return {"schema": "flywheel.hook-event-run/v1",
                "event": event,
                "hook_receipts": receipts,
                "event_blocked": event_blocked(receipts)}, 200
    return error_response(TransportError("NOT_FOUND", "unknown hook route",
                                         404))
