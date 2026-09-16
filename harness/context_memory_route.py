"""Authenticated context-memory capture and preflight route."""
from __future__ import annotations

from pathlib import Path

from .context_memory_bridge import ContextMemoryBridge, ContextMemoryError
from .evidence_public import TransportError, error_response, parse_json


def context_memory_post(path: str, raw: bytes, *, owner_ref: str,
                        state_root: Path, clock, bridge=None) -> tuple[dict, int]:
    try:
        action = path.rstrip("/").rsplit("/", 1)[-1]
        if action not in {"capture", "preflight", "status"}:
            raise TransportError("NOT_FOUND", "context-memory route not found", 404)
        service = bridge or ContextMemoryBridge()
        if action == "status":
            return service.health(), 200
        req = parse_json(raw)
        if action == "capture":
            return service.capture(owner_ref, req), 200
        return service.preflight(owner_ref, req), 200
    except ContextMemoryError as exc:
        return error_response(TransportError(exc.code, exc.message, exc.status))
    except TransportError as exc:
        return error_response(exc)
