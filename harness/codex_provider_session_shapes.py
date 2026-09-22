"""Shape, event, and approval helpers for Codex provider sessions."""
from __future__ import annotations

from typing import Any

from .codex_session_types import CodexSessionTransportError
from .evidence_json import canonical_sha256
from .provider_session_contract import (
    ProviderOperationOutcome, ProviderRuntimeBinding, ProviderSessionError,
)

_TURN_BOUND_EVENTS = frozenset({
    "agent/message/delta", "fileChange/output/delta", "item/completed",
    "item/started", "turn/completed", "turn/started",
})
_PROVIDER_OBSERVATION_KEYS = (
    "provider", "native_session_id", "native_thread_id", "native_turn_id",
    "last_provider_event_id", "config_digest", "capability_digest",
)


def _thread_options(operation: dict) -> dict:
    return {key: operation[key] for key in ("model",) if operation.get(key)}


def _turn_options(operation: dict) -> dict:
    return _thread_options(operation)


def _codex_input(value):
    if isinstance(value, str):
        return [{"type": "text", "text": value}]
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        raise ProviderSessionError("AGENT_NATIVE_PROTOCOL_ERROR")
    return [_input_item(item) for item in value]


def _input_item(item):
    if not isinstance(item, dict):
        raise ProviderSessionError("AGENT_NATIVE_PROTOCOL_ERROR")
    result = dict(item)
    if result.get("type") == "input_text":
        result["type"] = "text"
    if result.get("type") == "input_image":
        result["type"] = "image"
    return result


def _thread_from(response) -> dict:
    if not isinstance(response, dict) or not isinstance(response.get("thread"), dict):
        raise ProviderSessionError("AGENT_NATIVE_PROTOCOL_ERROR")
    thread = response["thread"]
    _required_text(thread, "id")
    return thread


def _turn_from(response) -> dict:
    if not isinstance(response, dict) or not isinstance(response.get("turn"), dict):
        raise ProviderSessionError("AGENT_NATIVE_PROTOCOL_ERROR")
    turn = response["turn"]
    _required_text(turn, "id")
    return turn


def _session_from_thread(thread: dict, binding: ProviderRuntimeBinding) -> dict:
    thread_id = _required_text(thread, "id")
    return {
        "provider": "codex",
        "native_session_id": str(thread.get("sessionId") or thread_id),
        "native_thread_id": thread_id,
        "config_digest": binding.config_digest,
        "capability_digest": binding.capability_digest,
    }


def _session_from_observed_thread(thread: dict, binding: ProviderRuntimeBinding,
                                  source: dict | None = None) -> dict:
    session = _session_from_thread(thread, binding)
    if source is None:
        return session
    for key in ("native_session_id", "native_thread_id"):
        if source.get(key) and source[key] != session.get(key):
            raise ProviderSessionError("AGENT_BINDING_DRIFT")
    for key in ("native_turn_id", "last_provider_event_id"):
        if source.get(key):
            session[key] = source[key]
    return session


def _history(thread: dict) -> list[dict]:
    turns = thread.get("turns")
    if not isinstance(turns, list):
        return []
    return [_turn_summary(turn) for turn in turns if isinstance(turn, dict)]


def _history_missing(thread: dict) -> bool:
    return not isinstance(thread.get("turns"), list)


def _turn_summary(turn: dict) -> dict:
    return {
        "id": str(turn.get("id", "")),
        "status": str(turn.get("status", "")),
        "item_count": len(turn.get("items") or []),
    }


def _find_turn(history: list[dict], turn_id: str):
    for turn in history:
        if turn.get("id") == turn_id:
            return turn
    return None


def _same_thread(thread_id: str, thread: dict) -> None:
    if thread.get("id") != thread_id:
        raise ProviderSessionError("AGENT_BINDING_DRIFT")


def _required_text(value: dict, key: str) -> str:
    text = value.get(key)
    if not isinstance(text, str) or not text:
        raise ProviderSessionError("AGENT_BINDING_DRIFT")
    return text


def _emit_binding(emit, request, session) -> None:
    emit.native("native_binding", **_session_event(request, session))


def _emit_input_sent(emit, request, session) -> None:
    emit.native("input_sent", side_effect_status="input_sent",
                **_session_event(request, session))


def _interrupt_turn(client, request, emit, session) -> bool:
    emit.native("cancel_requested", **_session_event(request, session))
    try:
        client.turn_interrupt(
            session["native_thread_id"], session["native_turn_id"])
    except CodexSessionTransportError as exc:
        raise ProviderSessionError(
            "AGENT_NATIVE_INCOMPLETE", provider_session=dict(session),
            history_status="indeterminate",
            side_effect_status="unknown_after_send",
            transport_error=exc.code)
    emit.native("cancel_acknowledged", **_session_event(request, session))
    return True


def _session_event(request, session) -> dict:
    payload = dict(session)
    for key in ("source_operation_ref", "target_operation_ref"):
        if isinstance(request.operation.get(key), str):
            payload[key] = request.operation[key]
    return payload


def _notification_event(note, request, session) -> dict:
    params = note.params if isinstance(note.params, dict) else {}
    turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
    item = params.get("item") if isinstance(params.get("item"), dict) else {}
    raw_thread_id = params.get("threadId")
    thread_id = "" if raw_thread_id is None else str(raw_thread_id)
    if raw_thread_id is None and note.method not in _TURN_BOUND_EVENTS:
        thread_id = event_thread_id = session["native_thread_id"]
    else:
        event_thread_id = thread_id
    event = _session_event(request, session)
    event.update({
        "raw_event_type": note.method,
        "last_provider_event_id": f"event-{note.sequence}",
        "native_thread_id": event_thread_id,
        "native_turn_id": str(turn.get("id") or params.get("turnId") or event.get("native_turn_id", "")),
        "native_item_id": str(item.get("id") or params.get("itemId") or ""),
    })
    return event


def _wrong_thread(event: dict, session: dict) -> bool:
    if event.get("raw_event_type") not in _TURN_BOUND_EVENTS:
        return False
    expected = session.get("native_thread_id", "")
    observed = event.get("native_thread_id", "")
    return bool(expected and observed != expected)


def _wrong_turn(event: dict, session: dict) -> bool:
    if event.get("raw_event_type") not in _TURN_BOUND_EVENTS:
        return False
    expected = session.get("native_turn_id", "")
    observed = event.get("native_turn_id", "")
    return bool(expected and observed != expected)


def _server_request_event(server_request, request, session) -> dict:
    event = _session_event(request, session)
    event.update({
        "raw_event_type": server_request.method,
        "native_request_id": str(server_request.id),
    })
    return event


def _turn_outcome(session, native_history, turn, cancelled):
    status = str(turn.get("status", ""))
    session = {**session, "native_turn_id": str(turn.get("id") or session["native_turn_id"])}
    result = {
        "provider_session": session,
        "history_status": "complete",
        "side_effect_status": "input_sent",
        "native_history": [*native_history, _turn_summary(turn)],
        "native_turn_status": status,
    }
    if cancelled:
        return ProviderOperationOutcome.failed(
            "AGENT_NATIVE_CANCELLED", **result,
            cancellation_status="acknowledged",
            cancellation_outcome=status or "indeterminate")
    if status == "completed":
        return ProviderOperationOutcome.completed(result)
    return ProviderOperationOutcome.failed("AGENT_NATIVE_TURN_FAILED", **result)


def _provider_observation(session: dict, target_ref: str,
                          observed_status: str) -> dict:
    return {
        **{key: str(session.get(key, "")) for key in _PROVIDER_OBSERVATION_KEYS},
        "target_operation_ref": target_ref,
        "observed_status": observed_status,
    }


def _incomplete(reason: str, *, session=None):
    result = {
        "reason": "AGENT_NATIVE_INCOMPLETE",
        "history_status": "indeterminate",
        "side_effect_status": "unknown_after_send",
        "transport_error": reason,
    }
    if session:
        result["provider_session"] = dict(session)
    return ProviderOperationOutcome("failed", result)


def _transport_failure(code: str, *, input_sent: bool, session=None):
    if input_sent:
        return _incomplete(code, session=session)
    return ProviderOperationOutcome.failed(
        "AGENT_NATIVE_INCOMPLETE",
        history_status="indeterminate",
        side_effect_status="none",
        transport_error=code)


def _timeout(operation: dict, default: float) -> float:
    value = operation.get("timeout_s", default)
    return float(value) if isinstance(value, int) and value > 0 else default


def _observation_ref(value: Any) -> str:
    return "codex.thread.read:" + canonical_sha256(value)
