"""Strict gateway-operation grammar and interrupted-startup recovery."""
from __future__ import annotations

from pathlib import Path
import re

from .evidence_json import canonical_sha256
from .journey_service import JourneyService
from .journey_store import JourneyStore
from .journey_types import SHA256_PATTERN
from .operation_grants import GrantStore, OWNER_REF_PATTERN

LIFECYCLE = frozenset((
    "operation_queued", "operation_started", "cancel_requested",
    "operation_completed", "operation_failed", "operation_cancelled",
))
TERMINAL_EVENTS = frozenset((
    "operation_completed", "operation_failed", "operation_cancelled",
))
FAILURE_REASONS = frozenset((
    "EXTERNAL_ACTION_FAILED", "OWNERSHIP_UNAVAILABLE", "OPERATION_INTERRUPTED",
    "RESULT_SEAL_FAILED",
))


def _terminal(history: list[dict]) -> dict | None:
    return next((event for event in history
                 if event["event_type"] in TERMINAL_EVENTS), None)


def history_state(history: list[dict]) -> tuple[str, dict | None]:
    terminal = _terminal(history)
    if terminal:
        return terminal["event_type"].removeprefix("operation_"), terminal
    kinds = {event["event_type"] for event in history}
    if "cancel_requested" in kinds:
        return "cancel_requested", None
    if "operation_started" in kinds:
        return "running", None
    return "queued", None


def started_event(history: list[dict]) -> dict:
    return next(event for event in history
                if event["event_type"] == "operation_started")


def validate_result(value: object, operation_ref: str,
                    action: str, state: str) -> None:
    fields = {"schema", "operation_ref", "action", "state", "result"}
    if (type(value) is not dict or set(value) != fields
            or value.get("schema") != "flywheel.gateway-operation-result/v1"
            or value.get("operation_ref") != operation_ref
            or value.get("action") != action or value.get("state") != state
            or type(value.get("result")) is not dict):
        raise ValueError("gateway operation result is invalid")


def normalize_outcome(current: str, state: object,
                      result: object) -> tuple[str, dict]:
    allowed = {
        "queued": {"failed"},
        "running": {"completed", "failed"},
        "cancel_requested": {"cancelled", "completed", "failed"},
    }
    if (state not in allowed.get(current, set()) or type(result) is not dict
            or state == "failed" and result.get("reason") not in FAILURE_REASONS):
        return "failed", {"reason": "EXTERNAL_ACTION_FAILED"}
    return state, result


def seal_outcome(seal, owner_ref: str, operation_ref: str, action: str,
                 state: str, result: dict) -> tuple[str, dict, str]:
    try:
        return state, result, seal(
            owner_ref, operation_ref, action, state, result)
    except Exception as exc:
        if getattr(exc, "code", None) != "STORE_COMMIT_FAILED":
            raise
        failed = {"reason": "RESULT_SEAL_FAILED"}
        return "failed", failed, seal(
            owner_ref, operation_ref, action, "failed", failed)


def validate_history(history: list[dict], operation_ref: str) -> None:
    if not history:
        return
    queued = history[0]
    qkeys = {"operation_ref", "client_request_id", "action", "tool",
             "authorization_sha256", "operation_sha256", "arguments_sha256",
             "grant_ref_sha256", "execution_plan_sha256"}
    if (queued["event_type"] != "operation_queued"
            or set(queued["payload"]) != qkeys
            or queued["payload"].get("operation_ref") != operation_ref
            or re.fullmatch(r"op_[0-9a-f]{32}\Z", operation_ref) is None
            or queued["payload"].get("action") != "agent.run"
            or queued["payload"].get("tool") != "agent.run"
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z",
                            queued["payload"].get("client_request_id", ""))
            is None
            or any(SHA256_PATTERN.fullmatch(queued["payload"].get(key, ""))
                   is None for key in qkeys if key.endswith("sha256"))):
        raise ValueError("ambiguous gateway operation history")
    kinds = [event["event_type"] for event in history]
    if (kinds.count("operation_queued") != 1
            or kinds.count("operation_started") > 1
            or kinds.count("cancel_requested") > 1
            or sum(kind in TERMINAL_EVENTS for kind in kinds) > 1):
        raise ValueError("ambiguous gateway operation history")
    started = next((event for event in history
                    if event["event_type"] == "operation_started"), None)
    cancel = next((event for event in history
                   if event["event_type"] == "cancel_requested"), None)
    terminal = _terminal(history)
    _validate_started(started, queued)
    _validate_cancel(cancel, started)
    _validate_terminal(terminal, cancel or started or queued)
    positions = {kind: kinds.index(kind) for kind in set(kinds)}
    if (started and positions["operation_started"] < 1
            or cancel and positions["cancel_requested"]
            < positions["operation_started"]
            or terminal and positions[terminal["event_type"]]
            < positions[(cancel or started or queued)["event_type"]]):
        raise ValueError("ambiguous gateway operation history")


def _validate_started(started: dict | None, queued: dict) -> None:
    if started is None:
        return
    payload = started["payload"]
    if (set(payload) != {"operation_ref", "queued_event_sha256", "control_class"}
            or payload.get("operation_ref") != queued["payload"]["operation_ref"]
            or payload.get("queued_event_sha256") != queued["event_sha256"]
            or payload.get("control_class") != "windows_job_v1"):
        raise ValueError("ambiguous gateway operation history")


def _validate_cancel(cancel: dict | None, started: dict | None) -> None:
    if cancel is None:
        return
    payload = cancel["payload"]
    keys = {"operation_ref", "started_event_sha256", "client_request_id",
            "authorization_sha256", "timeout_ms"}
    if (started is None or set(payload) != keys
            or payload.get("operation_ref") != started["payload"]["operation_ref"]
            or payload.get("started_event_sha256") != started["event_sha256"]
            or SHA256_PATTERN.fullmatch(payload.get("authorization_sha256", ""))
            is None or type(payload.get("timeout_ms")) is not int
            or not 1 <= payload["timeout_ms"] <= 30_000):
        raise ValueError("ambiguous gateway operation history")


def _validate_terminal(terminal: dict | None, basis: dict) -> None:
    if terminal is None:
        return
    payload = terminal["payload"]
    common = {"operation_ref", "basis_event_sha256", "result_sha256"}
    allowed = {
        "operation_queued": {"operation_failed"},
        "operation_started": {"operation_completed", "operation_failed"},
        "cancel_requested": TERMINAL_EVENTS,
    }
    expected = common | ({"reason"}
                         if terminal["event_type"] == "operation_failed"
                         else set())
    if (set(payload) != expected
            or payload.get("operation_ref") != basis["payload"]["operation_ref"]
            or payload.get("basis_event_sha256") != basis["event_sha256"]
            or SHA256_PATTERN.fullmatch(payload.get("result_sha256", "")) is None
            or terminal["event_type"] not in allowed.get(basis["event_type"], set())
            or terminal["event_type"] == "operation_failed"
            and payload.get("reason") not in FAILURE_REASONS):
        raise ValueError("ambiguous gateway operation history")


def _groups(service: JourneyService) -> list[tuple[str, list[dict]]]:
    groups: dict[str, list[dict]] = {}
    for projection in service.list():
        for event in service._events(projection["journey_ref"]):
            ref = event["payload"].get("operation_ref")
            if event["event_type"] in LIFECYCLE and type(ref) is str:
                groups.setdefault(ref, []).append(event)
    return sorted(groups.items())


def recover_gateway_operations(state_root: Path, now: str) -> dict:
    """Fail exact abandoned runs; retain ambiguous histories for diagnosis."""
    from .gateway_operation_process import WorkerOutcome
    from .gateway_operations import GatewayOperations, TERMINALS
    root, closed, ambiguous, diagnostics = Path(state_root), 0, 0, []
    owners = root / "journeys" / "v2" / "owners"
    for owner_dir in sorted(owners.glob("owner_*")) if owners.exists() else ():
        if OWNER_REF_PATTERN.fullmatch(owner_dir.name) is None:
            continue
        service = JourneyService(
            owner_ref=owner_dir.name, store=JourneyStore(root),
            grants=GrantStore(root, clock=lambda: now), clock=lambda: now)
        operations = GatewayOperations(root, clock=lambda: now)
        for ref, history in _groups(service):
            try:
                validate_history(history, ref)
                state, _ = history_state(history)
                if state in TERMINALS:
                    operations.result(owner_dir.name, ref)
                    continue
                operations._terminal(owner_dir.name, ref, WorkerOutcome(
                    "failed", {"reason": "OPERATION_INTERRUPTED"}))
                closed += 1
            except Exception:
                ambiguous += 1
                diagnostics.append(canonical_sha256({
                    "owner_ref": owner_dir.name, "operation_ref": ref,
                    "event_refs": [event["event_sha256"] for event in history]}))
    return {"closed": closed, "ambiguous": ambiguous,
            "diagnostic_refs": diagnostics}
