"""subagents_route.py -- swarm management routes.

GET  /api/subagents          list live + sealed swarms
GET  /api/subagents/swarm    ?id= live snapshot or sealed receipt
POST /api/subagents/spawn    fan out N role-prompted children

Spawning is exec authority: children are real processes. The runner is
a per-run-root singleton so concurrent swarms share one registry, and
the sealed fan-in receipt persists under <run_root>/subagents/.
"""
from __future__ import annotations

import threading
import urllib.parse
from pathlib import Path

from .evidence_public import TransportError, error_response
from .subagent_store import detached_summaries
from .subagents import (
    MAX_CHILDREN,
    SwarmRunner,
    load_swarm_receipt,
    sealed_summaries,
    swarm_dir,
)

_RUNNERS: "dict[str, SwarmRunner]" = {}
_LOCK = threading.Lock()


def _invalid(message: str) -> tuple[dict, int]:
    return error_response(TransportError("INVALID_REQUEST", message, 422))


def _runner(run_root: Path, clock=None) -> SwarmRunner:
    key = str(run_root)
    with _LOCK:
        runner = _RUNNERS.get(key)
        if runner is None:
            runner = SwarmRunner(run_root=run_root, clock=clock)
            _RUNNERS[key] = runner
        return runner


def _qs_value(qs: str, key: str) -> str:
    values = urllib.parse.parse_qs(qs).get(key, [])
    return values[0] if values else ""


def _safe_id(swarm_id: str) -> bool:
    return (swarm_id.startswith("swarm_")
            and set(swarm_id) <= set("abcdefghijklmnopqrstuvwxyz0123456789_"))


def handle_subagents_get(path: str, qs: str, *,
                         run_root) -> tuple[dict, int]:
    root = Path(run_root)
    runner = _runner(root)
    if path == "/api/subagents":
        live = runner.live_summaries()
        live_ids = {row["swarm_id"] for row in live}
        sealed = [row for row in sealed_summaries(root)
                  if row["swarm_id"] not in live_ids]
        sealed_ids = {row["swarm_id"] for row in sealed}
        detached = [row for row in detached_summaries(root)
                    if row["swarm_id"] not in live_ids
                    and row["swarm_id"] not in sealed_ids]
        rows = live + sealed + detached
        return {"schema": "flywheel.subagent-list/v1",
                "swarms": rows, "count": len(rows)}, 200
    if path == "/api/subagents/swarm":
        swarm_id = _qs_value(qs, "id")
        snap = runner.snapshot(swarm_id)
        if snap is not None:
            return snap, 200
        receipt = None
        if _safe_id(swarm_id):
            receipt = load_swarm_receipt(
                swarm_dir(root, swarm_id) / "swarm.json")
        if receipt is not None:
            return {"swarm_id": swarm_id, "status": "sealed",
                    "receipt": receipt}, 200
        return error_response(TransportError("NOT_FOUND",
                                             "unknown swarm", 404))
    return error_response(TransportError("NOT_FOUND",
                                         "unknown subagent route", 404))


def handle_subagents_post(path: str, body: dict, *, run_root, clock=None,
                          owner_ref=None, state_root=None,
                          operation_service=None, process_factory=None,
                          workspace_root=None,
                          parent_authority_validator=None,
                          handle_factory=None) -> tuple[dict, int]:
    action = path.rsplit("/", 1)[-1]
    if action not in ("spawn", "cancel"):
        return error_response(TransportError("NOT_FOUND",
                                             "unknown subagent route", 404))
    if action == "cancel":
        swarm_id = str((body or {}).get("swarm_id") or "")
        if not _safe_id(swarm_id):
            return _invalid("the cancel request names no valid swarm")
        res = _runner(Path(run_root), clock).cancel(swarm_id)
        if res.get("code") == "CANCEL_UNAVAILABLE":
            status = 409 if res.get("state") == "sealed" else 404
            return error_response(TransportError(
                "CANCEL_UNAVAILABLE", f"the swarm is {res.get('state')}",
                status))
        return res, 200
    if not isinstance(body, dict):
        return _invalid("the spawn request is a JSON object")
    if body.get("schema") == "flywheel.subagent-spawn-request/v2":
        try:
            if operation_service is None or process_factory is None \
                    or owner_ref is None or state_root is None:
                raise ValueError("gateway operation service is required")
            from .subagent_gateway_bridge import (
                aggregate_child_budget, authorize_parent_authority,
                parent_spawn_guard, preflight_child_credentials,
                preview_parent_authority)
            parent = preview_parent_authority(
                body.get("parent_authority"), owner_ref=owner_ref,
                state_root=Path(state_root), workspace_root=workspace_root)
            aggregate_child_budget(body.get("children", []), parent,
                                   body.get("timeout_s", 600.0))
            preflight_child_credentials(body.get("children", []), parent,
                goal=str(body.get("goal") or ""), state_root=Path(state_root),
                workspace_root=workspace_root)
            with parent_spawn_guard(Path(state_root), owner_ref):
                authorized = authorize_parent_authority(
                    body.get("parent_authority"), operation_service,
                    owner_ref=owner_ref, workspace_root=workspace_root)
                ack = _runner(Path(run_root), clock).spawn(
                    goal=body.get("goal"), children=body.get("children"),
                    parent_authority=authorized, quorum_policy=str(
                        body.get("quorum_policy") or "majority"),
                    timeout_s=body.get("timeout_s", 600.0),
                    workspace_root=workspace_root, state_root=Path(state_root),
                    operation_service=operation_service,
                    process_factory=process_factory,
                    handle_factory=handle_factory)
            return ack, 200
        except Exception as exc:
            return _invalid(str(getattr(exc, "code", exc)))
    children_raw = body.get("children")
    if not isinstance(children_raw, list) \
            or not 1 <= len(children_raw) <= MAX_CHILDREN:
        return _invalid(f"children carries 1..{MAX_CHILDREN} role bindings")
    from .subagents import validate_child
    children = []
    for raw in children_raw:
        if isinstance(raw, str):
            raw = {"role": raw}
        if not isinstance(raw, dict):
            return _invalid("every child binding is a role object")
        try:
            children.append(validate_child(
                str(raw.get("role", "")), str(raw.get("prompt") or ""),
                allow_write=bool(raw.get("allow_write")),
                allow_exec=bool(raw.get("allow_exec"))))
        except ValueError as exc:
            return _invalid(str(exc))
    try:
        ack = _runner(Path(run_root), clock).spawn(
            goal=body.get("goal"), endpoint=body.get("endpoint"),
            children=children, quorum_policy=str(
                body.get("quorum_policy") or "majority"),
            timeout_s=body.get("timeout_s", 600.0),
            max_steps=body.get("max_steps", 6),
            model=str(body.get("model") or ""))
    except (ValueError, TypeError) as exc:
        return _invalid(str(exc))
    return ack, 200
