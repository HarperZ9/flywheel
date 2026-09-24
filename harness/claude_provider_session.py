"""Claude ProviderSessionAdapter over an injected Claude session client.

This file does not launch Claude or prove runtime admission. It translates the
existing injected Claude session client into the generic provider-session seam and
keeps unsupported native history/reconcile evidence explicit.
"""
from __future__ import annotations

import time
from typing import Any, Callable

from .claude_session_transport import ClaudeSessionTransportError
from .claude_session_contract import ClaudePermissionDecision
from .claude_provider_session_custody import (
    ToolUseCustody,
    control_tool_use_id,
)
from .claude_provider_session_reconcile import reconcile_outcome
from .claude_provider_session_resume import (
    launch_client_from_supplier, prepare_start_session,
)
from .claude_provider_session_shapes import (
    FATAL_PROTOCOL,
    cancelled as cancelled_outcome,
    claude_decision,
    event_payload,
    has_pending_controls,
    incomplete,
    input_receipt,
    mark_recovery,
    native_request_id,
    observe_event_session,
    pop_control,
    pop_event,
    pop_protocol,
    provider_approval,
    require_surface,
    result_outcome,
    send_input,
    send_permission,
    session_event,
    surface_session_id,
    timeout,
    transport_failure,
    unsupported,
)
from .provider_session_contract import (
    ProviderOperationOutcome,
    ProviderOperationRequest,
    ProviderRuntimeBinding,
    ProviderSessionError,
)

_PRE_WRITE_ERRORS = {
    "not_initialized", "pending_control_request", "transport_recovery_needed",
    "turn_in_flight",
}


class ClaudeProviderSessionAdapter:
    provider = "claude"

    def __init__(self, *, client_supplier: Callable[[], Any],
                 transport_supplier: Callable[[], Any] | None = None,
                 runtime_binding_supplier: Callable[[], ProviderRuntimeBinding],
                 launcher_supplier: Callable[[], Any] | None = None,
                 idle_timeout_s: float = 1.0, max_events: int = 256):
        self._client_supplier = client_supplier
        self._transport_supplier = transport_supplier
        self._runtime_binding_supplier = runtime_binding_supplier
        self._launcher_supplier = launcher_supplier
        self.idle_timeout_s = idle_timeout_s
        self.max_events = max_events
        self._spent_surfaces: set[int] = set()

    def current_binding(self) -> ProviderRuntimeBinding:
        binding = self._runtime_binding_supplier()
        if not isinstance(binding, ProviderRuntimeBinding) or binding.provider != self.provider:
            raise ProviderSessionError("AGENT_NATIVE_PROTOCOL_ERROR")
        return binding

    def start_turn(self, request: ProviderOperationRequest, *, emit,
                   request_approval, cancelled) -> ProviderOperationOutcome:
        try:
            binding = self.current_binding()
            self._check_binding(request.operation, binding)
            prepared = prepare_start_session(request, binding)
            if isinstance(prepared, ProviderOperationOutcome):
                return prepared
            session = prepared
            client = self._client(request, session)
            surface = self._surface(client)
            require_surface(surface, client, request.operation)
            emit.native("native_binding", **session_event(request, session))
            request_id = native_request_id(request)
            if self._surface_is_spent(surface):
                mark_recovery(surface)
                return transport_failure(
                    "stale_transport_session", input_sent=False, session=session)
            if has_pending_controls(surface):
                mark_recovery(surface)
                return transport_failure("pending_control_request", input_sent=False, session=session)
            if cancelled():
                return cancelled_outcome("not_sent", "not_requested", session, side_effect="none")
            fresh_claim = self._claim_surface(surface)
            receipt = session_event(request, session)
            receipt.update(input_receipt(request))
            emit.native("input_receipt", **receipt)
            try:
                send_input(client, request.operation["input"])
            except ClaudeSessionTransportError as exc:
                return self._fail_input_error(surface, exc, session)
            emit.native("input_sent", native_request_id=request_id,
                        side_effect_status="input_sent", **session_event(request, session))
            try:
                return self._watch(
                    client, surface, request, emit, request_approval, cancelled,
                    session, request_id, fresh_claim)
            except ClaudeSessionTransportError as exc:
                return self._fail_after_input(surface, exc.code, session)
        except ProviderSessionError as exc:
            return ProviderOperationOutcome.failed(exc.code, **exc.detail)
        except ClaudeSessionTransportError as exc:
            return transport_failure(exc.code, input_sent=False)

    def resume(self, request: ProviderOperationRequest, *, emit) -> ProviderOperationOutcome:
        try:
            self._check_binding(request.operation, self.current_binding())
            self._validate_source_identity(request)
            return unsupported()
        except ProviderSessionError as exc:
            return ProviderOperationOutcome.failed(exc.code, **exc.detail)

    def reconcile(self, request: ProviderOperationRequest, *, emit) -> ProviderOperationOutcome:
        try:
            binding = self.current_binding()
            self._check_binding(request.operation, binding)
            self._validate_source_identity(request, allow_operation=True)
            return reconcile_outcome(request, binding)
        except ProviderSessionError as exc:
            return ProviderOperationOutcome.failed(exc.code, **exc.detail)

    def _client(self, request, session=None):
        client = launch_client_from_supplier(
            self._client_supplier, request, session or {})
        if client is None:
            raise ProviderSessionError("AGENT_NATIVE_PROTOCOL_ERROR")
        return client

    def _surface(self, client):
        if self._transport_supplier is None:
            return client
        surface = self._transport_supplier()
        if surface is None:
            raise ProviderSessionError(
                "AGENT_NATIVE_PROTOCOL_ERROR",
                history_status="indeterminate",
                side_effect_status="none",
                surface_error="missing_transport")
        return surface

    def _surface_is_spent(self, surface) -> bool:
        return id(surface) in self._spent_surfaces or bool(surface_session_id(surface))

    def _claim_surface(self, surface) -> bool:
        self._spent_surfaces.add(id(surface))
        return True

    def _seal_surface(self, surface) -> None:
        self._spent_surfaces.add(id(surface))

    def _fail_input_error(self, surface, exc, session):
        self._seal_surface(surface)
        mark_recovery(surface)
        return transport_failure(
            exc.code, input_sent=exc.code not in _PRE_WRITE_ERRORS,
            session=session)

    def _fail_after_input(self, surface, code: str, session):
        self._seal_surface(surface)
        mark_recovery(surface)
        return transport_failure(code, input_sent=True, session=session)

    def _cancel_after_input(self, surface, status: str, outcome: str,
                            session, **detail):
        self._seal_surface(surface)
        mark_recovery(surface)
        return cancelled_outcome(status, outcome, session, **detail)

    def _check_binding(self, operation: dict, binding: ProviderRuntimeBinding) -> None:
        for key, actual in (("provider", binding.provider),
                            ("workspace_ref", binding.workspace_ref),
                            ("config_digest", binding.config_digest),
                            ("capability_digest", binding.capability_digest)):
            expected = operation.get(key)
            if expected and expected != actual:
                raise ProviderSessionError(
                    "AGENT_BINDING_DRIFT",
                    **{f"expected_{key}": expected, f"actual_{key}": actual})

    def _validate_source_identity(self, request: ProviderOperationRequest,
                                  *, allow_operation: bool = False) -> None:
        source = request.source_provider_session or {}
        if not source and not allow_operation:
            raise ProviderSessionError("AGENT_BINDING_DRIFT")
        if source and source.get("provider") != self.provider:
            raise ProviderSessionError("AGENT_BINDING_DRIFT")
        for key, expected in (("owner_ref", request.owner_ref),
                              ("journey_ref", request.journey_ref)):
            if source.get(key) and source[key] != expected:
                raise ProviderSessionError("AGENT_BINDING_DRIFT")
        for key in ("native_session_id", "native_thread_id", "native_turn_id"):
            if request.operation.get(key) and source.get(key) and request.operation[key] != source[key]:
                raise ProviderSessionError("AGENT_BINDING_DRIFT")

    def _watch(self, client, surface, request, emit, request_approval,
               cancelled, session, request_id, fresh_claim):
        deadline = time.monotonic() + timeout(request.operation, self.idle_timeout_s)
        cancel_ack = False
        custody = ToolUseCustody(allow_unobserved_first=fresh_claim)
        for _ in range(self.max_events):
            protocol = pop_protocol(surface)
            if protocol is not None and protocol.kind in FATAL_PROTOCOL:
                return self._fail_after_input(surface, protocol.kind, session)
            event = pop_event(surface, timeout=0.02)
            if event is not None:
                observed = observe_event_session(session, event)
                if observed is not None:
                    self._seal_surface(surface)
                    mark_recovery(surface)
                    return observed
                custody.observe(event)
                emit.native("provider_event", **event_payload(request, session, event))
                if event.kind == "result":
                    self._seal_surface(surface)
                    if has_pending_controls(surface):
                        return self._fail_after_input(
                            surface, "pending_control_request", session)
                    return result_outcome(request, session, event, request_id, cancel_ack)
            control = pop_control(surface)
            if control is not None:
                admitted, reason = custody.admit_control(control)
                if not admitted:
                    try:
                        self._deny_control(client, surface, control, request,
                                           emit, session, reason)
                    except ClaudeSessionTransportError as exc:
                        return self._fail_after_input(surface, exc.code, session)
                    return self._fail_after_input(surface, reason, session)
                try:
                    self._reply_to_control(client, surface, control, request, emit,
                                           request_approval, session)
                    custody.answer_control(control)
                except ClaudeSessionTransportError as exc:
                    return self._fail_after_input(surface, exc.code, session)
                continue
            if not cancel_ack and cancelled():
                emit.native("cancel_requested", **session_event(request, session))
                try:
                    client.interrupt(timeout=timeout(request.operation, self.idle_timeout_s))
                    cancel_ack = True
                    emit.native("cancel_acknowledged", **session_event(request, session))
                except ClaudeSessionTransportError as exc:
                    return self._cancel_after_input(
                        surface, "unknown", "indeterminate", session,
                        side_effect="input_sent", transport_error=exc.code)
                continue
            if event is None:
                if cancel_ack:
                    return self._cancel_after_input(
                        surface, "acknowledged", "indeterminate", session)
                if time.monotonic() >= deadline:
                    return self._fail_after_input(surface, "timeout", session)
                continue
        return self._fail_after_input(surface, "event_bound_exceeded", session)

    def _deny_control(self, client, surface, control, request, emit, session, reason) -> None:
        tool_use_id = control_tool_use_id(control)
        send_permission(
            client, surface, control,
            ClaudePermissionDecision.deny("approval unavailable"))
        emit.native("approval_denied_unbound", native_request_id=control.request_id,
                    native_item_id=tool_use_id, denial_reason=reason,
                    **session_event(request, session))

    def _reply_to_control(self, client, surface, control, request, emit,
                          request_approval, session) -> None:
        provider_request = provider_approval(control, session)
        emit.native("approval_requested", native_request_id=provider_request.native_request_id,
                    tool=provider_request.tool, payload_sha256=provider_request.payload_sha256,
                    **session_event(request, session))
        try:
            decision = request_approval(provider_request)
        except Exception:
            decision = None
        native_decision = claude_decision(provider_request, decision)
        send_permission(client, surface, control, native_decision)
        emit.native("approval_replied", native_request_id=provider_request.native_request_id,
                    decision=native_decision.behavior, **session_event(request, session))
