"""Event and control steps of the Claude provider-session watch loop.

Each step returns ``(done, outcome)``: ``done`` is true when the watch loop must
return ``outcome``, and false when the loop continues.
"""
from __future__ import annotations

from .claude_session_transport import ClaudeSessionTransportError
from .claude_provider_session_shapes import (
    event_payload,
    has_pending_controls,
    mark_recovery,
    observe_event_session,
    result_outcome,
)


def watch_event(adapter, surface, request, emit, session, event, custody,
                request_id, cancel_ack):
    observed = observe_event_session(session, event)
    if observed is not None:
        adapter._seal_surface(surface)
        mark_recovery(surface)
        return True, observed
    custody.observe(event)
    emit.native("provider_event", **event_payload(request, session, event))
    if event.kind == "result":
        adapter._seal_surface(surface)
        if has_pending_controls(surface):
            return True, adapter._fail_after_input(
                surface, "pending_control_request", session)
        return True, result_outcome(request, session, event, request_id, cancel_ack)
    return False, None


def watch_control(adapter, client, surface, control, request, emit,
                  request_approval, session, custody):
    admitted, reason = custody.admit_control(control)
    if not admitted:
        try:
            adapter._deny_control(client, surface, control, request,
                                  emit, session, reason)
        except ClaudeSessionTransportError as exc:
            return True, adapter._fail_after_input(surface, exc.code, session)
        return True, adapter._fail_after_input(surface, reason, session)
    try:
        adapter._reply_to_control(client, surface, control, request, emit,
                                  request_approval, session)
        custody.answer_control(control)
    except ClaudeSessionTransportError as exc:
        return True, adapter._fail_after_input(surface, exc.code, session)
    return False, None
