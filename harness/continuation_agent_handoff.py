"""Source-bound validation for native continuation handoff to agent.run."""
from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .continuation_context import RUNNER_CONTEXT_SCHEMA
from .evidence_json import canonical_sha256
from .continuation_preview import build_continuation
from .continuation_replay import matching_request_event
from .continuation_store import load_preview, load_start_binding
from .evidence_public import TransportError
from .gateway_operation import GatewayOperationError, thaw_operation
from .journey_store import JourneyStore, JourneyStoreError

AGENT_HANDOFF_SCHEMA = "flywheel.native-continuation-agent-handoff/v1"


def validate_continuation_agent_operation(
        operation, state_root: Path, *, owner_ref: str, journey_ref: str,
        journey_events: list[dict] | None = None) -> None:
    """Revalidate a continuation-bound agent.run before grant or dispatch."""
    op = _operation_dict(operation)
    handoff = op.get("continuation")
    if handoff is None:
        return
    try:
        stored = load_preview(state_root, handoff["preview_ref"])
        _ensure_current(handoff, stored)
        _ensure_ready(stored)
        runner = _runner(stored)
        binding = load_start_binding(
            state_root, owner_ref, handoff["preview_ref"])
    except TransportError as exc:
        raise GatewayOperationError(exc.code) from None
    _ensure_start_binding(
        handoff, stored, binding, owner_ref, journey_ref, state_root,
        journey_events)
    if op.get("root") != runner["root"]:
        raise GatewayOperationError("CONTINUATION_ROOT_MISMATCH")
    if str(runner["goal"]) not in str(op.get("goal", "")):
        raise GatewayOperationError("CONTINUATION_CONTEXT_MISMATCH")
    if handoff["selected_files"] != list(runner.get("selected_files", [])):
        raise GatewayOperationError("CONTINUATION_CONTEXT_MISMATCH")


def _ensure_start_binding(handoff: dict, stored: dict, binding: dict,
                          owner_ref: str, journey_ref: str,
                          state_root: Path,
                          journey_events: list[dict] | None) -> None:
    if (binding["preview_sha256"] != handoff["preview_sha256"]
            or binding["source_state_sha256"]
            != handoff["source_state_sha256"]):
        raise GatewayOperationError("PREVIEW_MISMATCH")
    _ensure_start_evidence(
        binding, stored, state_root, owner_ref, journey_ref, journey_events)
    if binding["owner_ref"] != owner_ref or binding["journey_ref"] != journey_ref:
        raise GatewayOperationError("CONTINUATION_JOURNEY_MISMATCH")


def _ensure_start_evidence(binding: dict, stored: dict, state_root: Path,
                           owner_ref: str, journey_ref: str,
                           journey_events: list[dict] | None) -> None:
    store = JourneyStore(state_root)
    try:
        if (journey_events is not None and binding["owner_ref"] == owner_ref
                and binding["journey_ref"] == journey_ref):
            start = _matching_request_event_at_head(
                store, binding, binding["start_client_request_id"],
                journey_events)
            recovery = _matching_request_event_at_head(
                store, binding, binding["recovery_client_request_id"],
                journey_events)
        else:
            start = matching_request_event(
                store, owner_ref=binding["owner_ref"],
                journey_ref=binding["journey_ref"],
                request_id=binding["start_client_request_id"])
            recovery = matching_request_event(
                store, owner_ref=binding["owner_ref"],
                journey_ref=binding["journey_ref"],
                request_id=binding["recovery_client_request_id"])
    except JourneyStoreError as exc:
        code = "STORE_BUSY" if exc.code == "STORE_BUSY" else "CONTINUATION_BINDING_DRIFT"
        raise GatewayOperationError(code) from None
    if start is None or recovery is None:
        raise GatewayOperationError("CONTINUATION_BINDING_DRIFT")
    _, start_event, _ = start
    recovery_record, recovery_event, _ = recovery
    intake = start_event.get("payload", {}).get("intake")
    expected_action = {
        "action_id": "continue-" + stored["preview_ref"],
        "kind": "repair",
        "description": "Open the private continuation context and run the existing agent loop from the source-bound preview.",
        "basis_refs": [stored["preview_ref"], stored["intake_ref"]],
    }
    if (start_event.get("sequence") != 0
            or start_event.get("event_type") != "intake"
            or type(intake) is not dict
            or intake.get("preview_ref") != stored["preview_ref"]
            or intake.get("preview_sha256") != stored["preview_sha256"]
            or recovery_event.get("event_type") != "record_next_action"
            or recovery_event.get("payload") != {"next_actions": [expected_action]}
            or recovery_event.get("event_sha256")
            != binding["recovery_event_sha256"]
            or recovery_record.get("event_head_sha256")
            != binding["recovery_event_head_sha256"]):
        raise GatewayOperationError("CONTINUATION_BINDING_DRIFT")


def _matching_request_event_at_head(store: JourneyStore, binding: dict,
                                    request_id: str,
                                    events: list[dict]):
    request_key = canonical_sha256(request_id)
    directory = store._journey_dir(binding["owner_ref"], binding["journey_ref"])
    path = directory / "requests" / f"{request_key}.json"
    if not path.exists():
        return None
    record = store._read_json(path)
    if record.get("client_request_sha256") != request_key:
        raise JourneyStoreError("STORE_COMMIT_FAILED")
    event = next((item for item in events
                  if item["event_sha256"] == record.get("event_sha256")), None)
    if event is None:
        raise JourneyStoreError("STORE_COMMIT_FAILED")
    return record, event, events


def _operation_dict(operation) -> dict:
    value = getattr(operation, "operation", operation)
    if not isinstance(value, Mapping):
        raise GatewayOperationError("INVALID_REQUEST")
    return thaw_operation(value)


def _runner(stored: dict) -> dict:
    runner = stored.get("runner_context")
    if (type(runner) is not dict
            or runner.get("schema") != RUNNER_CONTEXT_SCHEMA
            or type(runner.get("root")) is not str
            or type(runner.get("goal")) is not str
            or type(runner.get("selected_files")) is not list):
        raise TransportError(
            "INVALID_CONTINUATION", "continuation preview is invalid", 422)
    return runner


def _ensure_ready(stored: dict) -> None:
    health = stored.get("health") if type(stored.get("health")) is dict else {}
    if health.get("state") != "ready":
        raise TransportError(
            "CONTINUATION_BLOCKED", "continuation source is incomplete", 409)


def _ensure_current(handoff: dict, stored: dict) -> None:
    if (handoff["schema"] != AGENT_HANDOFF_SCHEMA
            or handoff["preview_sha256"] != stored.get("preview_sha256")
            or handoff["source_state_sha256"]
            != stored.get("source_state_sha256")):
        raise TransportError(
            "PREVIEW_MISMATCH",
            "continuation preview does not match request", 409)
    source = stored.get("source") if type(stored.get("source")) is dict else {}
    root, export = source.get("root"), source.get("export_path")
    if type(root) is not str:
        raise TransportError(
            "INVALID_CONTINUATION", "continuation preview is invalid", 422)
    current, _ = build_continuation(
        Path(root), export_path=Path(export) if type(export) is str else None)
    if current.get("source_state_sha256") != stored.get("source_state_sha256"):
        raise TransportError(
            "SOURCE_DRIFT", "source changed since continuation preview", 409)
