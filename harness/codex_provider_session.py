from __future__ import annotations

import time
from typing import Callable

from .codex_provider_session_approval import (
    _APPROVAL_DENIAL, _approval_matches_session, _approval_result,
    _provider_approval, _reply_or_fail,
)
from .codex_provider_session_ordering import _InboundOrdering
from .codex_provider_session_shapes import (
    _codex_input, _emit_binding, _emit_input_sent, _find_turn, _history,
    _history_missing, _incomplete, _interrupt_turn, _notification_event,
    _observation_ref, _provider_observation, _required_text,
    _same_thread, _server_request_event, _session_event,
    _session_from_observed_thread, _thread_from, _thread_options, _timeout,
    _transport_failure, _turn_from,
    _turn_options, _turn_outcome, _wrong_thread, _wrong_turn,
)
from .codex_session_types import CodexSessionTransportError
from .provider_session_contract import (
    ProviderOperationOutcome, ProviderOperationRequest, ProviderRuntimeBinding,
    ProviderSessionError,
)


class CodexProviderSessionAdapter:
    provider = "codex"

    def __init__(
            self, *, client_supplier: Callable[[], Any],
            transport_supplier: Callable[[], Any] | None,
            runtime_binding_supplier: Callable[[], ProviderRuntimeBinding],
            idle_timeout_s: float = 1.0, max_events: int = 256):
        self._client_supplier = client_supplier
        self._transport_supplier = transport_supplier
        self._runtime_binding_supplier = runtime_binding_supplier
        self.idle_timeout_s = idle_timeout_s
        self.max_events = max_events

    def current_binding(self) -> ProviderRuntimeBinding:
        binding = self._runtime_binding_supplier()
        if (not isinstance(binding, ProviderRuntimeBinding)
                or binding.provider != self.provider):
            raise ProviderSessionError("AGENT_NATIVE_PROTOCOL_ERROR")
        return binding

    def start_turn(self, request: ProviderOperationRequest, *, emit,
                   request_approval, cancelled) -> ProviderOperationOutcome:
        try:
            binding = self.current_binding()
            self._check_binding(request.operation, binding)
            client = self._client()
            transport = self._transport(client)
            source = self._validated_source(request)
            if source is None:
                thread_response = client.thread_start(**_thread_options(request.operation))
                thread = _thread_from(thread_response)
                native_history = []
            else:
                thread_id = source["native_thread_id"]
                thread_response = client.thread_resume(
                    thread_id, **_thread_options(request.operation))
                thread = _thread_from(thread_response)
                _same_thread(thread_id, thread)
                native_history = _history(thread)
            session = _session_from_observed_thread(thread, binding, source)
            _emit_binding(emit, request, session)
            try:
                turn_response = client.turn_start(
                    session["native_thread_id"],
                    _codex_input(request.operation["input"]),
                    client_user_message_id=request.operation.get("client_user_message_id"),
                    **_turn_options(request.operation))
            except CodexSessionTransportError as exc:
                return _transport_failure(exc.code, input_sent=True, session=session)
            turn = _turn_from(turn_response)
            session["native_turn_id"] = turn["id"]
            _emit_input_sent(emit, request, session)
            return self._watch_turn(
                client, transport, request, emit, request_approval, cancelled,
                session, turn, native_history)
        except ProviderSessionError as exc:
            return ProviderOperationOutcome.failed(exc.code, **exc.detail)
        except CodexSessionTransportError as exc:
            return _transport_failure(exc.code, input_sent=False)

    def resume(self, request: ProviderOperationRequest, *, emit) -> ProviderOperationOutcome:
        try:
            binding = self.current_binding()
            self._check_binding(request.operation, binding)
            client = self._client()
            source = self._source_or_operation(request)
            thread_id = _required_text(source, "native_thread_id")
            response = client.thread_resume(thread_id, **_thread_options(request.operation))
            thread = _thread_from(response)
            _same_thread(thread_id, thread)
            read = client.thread_read(thread_id, include_turns=True)
            observed = _thread_from(read)
            _same_thread(thread_id, observed)
            session = _session_from_observed_thread(thread, binding, source)
            _emit_binding(emit, request, session)
            history = _history(observed)
            target_turn_id = source.get("native_turn_id", "")
            if _history_missing(observed) or (
                    target_turn_id and _find_turn(history, target_turn_id) is None):
                return ProviderOperationOutcome.failed(
                    "AGENT_NATIVE_INCOMPLETE",
                    provider_session=session, history_status="missing",
                    side_effect_status="none",
                    positive_observation_ref=_observation_ref(read),
                )
            return ProviderOperationOutcome.completed({
                "provider_session": session,
                "history_status": "complete",
                "side_effect_status": "none",
                "native_history": history,
                "positive_observation_ref": _observation_ref(read),
            })
        except ProviderSessionError as exc:
            return ProviderOperationOutcome.failed(exc.code, **exc.detail)
        except CodexSessionTransportError as exc:
            return _transport_failure(exc.code, input_sent=False)

    def reconcile(self, request: ProviderOperationRequest, *, emit) -> ProviderOperationOutcome:
        try:
            binding = self.current_binding()
            self._check_binding(request.operation, binding)
            client = self._client()
            source = self._source_or_operation(request)
            thread_id = _required_text(source, "native_thread_id")
            target_turn_id = source.get("native_turn_id") or request.operation.get("native_turn_id", "")
            read = client.thread_read(thread_id, include_turns=True)
            thread = _thread_from(read)
            _same_thread(thread_id, thread)
            session = _session_from_observed_thread(thread, binding, source)
            _emit_binding(emit, request, session)
            history = _history(thread)
            found = None if _history_missing(thread) else _find_turn(history, target_turn_id)
            target_ref = request.operation.get("target_operation_ref", "")
            if found is None:
                return ProviderOperationOutcome.failed(
                    "AGENT_NATIVE_INCOMPLETE",
                    provider_session=session, history_status="missing",
                    side_effect_status="indeterminate",
                    target_operation_ref=target_ref,
                )
            native_status = found.get("status", "")
            if native_status not in {"completed", "failed", "interrupted"}:
                return ProviderOperationOutcome.failed(
                    "AGENT_NATIVE_INCOMPLETE",
                    provider_session=session, history_status="complete",
                    side_effect_status="in_progress",
                    native_history=history, native_turn_status=native_status,
                    target_operation_ref=target_ref,
                )
            return ProviderOperationOutcome.completed({
                "provider_session": session,
                "history_status": "complete",
                "side_effect_status": "native_terminal_observed",
                "native_history": history,
                "native_turn_status": native_status,
                "target_operation_ref": target_ref,
                "provider_observation": _provider_observation(
                    session, target_ref, "native_terminal_observed"),
                "positive_observation_ref": _observation_ref(read),
            })
        except ProviderSessionError as exc:
            return ProviderOperationOutcome.failed(exc.code, **exc.detail)
        except CodexSessionTransportError as exc:
            return _transport_failure(exc.code, input_sent=False)

    def _client(self):
        client = self._client_supplier()
        if client is None:
            raise ProviderSessionError("AGENT_NATIVE_PROTOCOL_ERROR")
        return client

    def _transport(self, client):
        if self._transport_supplier is not None:
            return self._transport_supplier()
        transport = getattr(client, "transport", None)
        if transport is None:
            raise ProviderSessionError("AGENT_NATIVE_PROTOCOL_ERROR")
        return transport

    def _check_binding(self, operation: dict, binding: ProviderRuntimeBinding) -> None:
        for key, actual, required in (
                ("provider", binding.provider, True),
                ("workspace_ref", binding.workspace_ref, True),
                ("config_digest", binding.config_digest, True),
                ("capability_digest", binding.capability_digest, False)):
            expected = operation.get(key)
            if required or key in operation:
                if type(expected) is not str or not expected.strip() or expected != actual:
                    raise ProviderSessionError(
                        "AGENT_BINDING_DRIFT",
                        **{f"expected_{key}": expected, f"actual_{key}": actual})

    def _validated_source(self, request: ProviderOperationRequest) -> dict | None:
        policy = request.operation.get("resume_policy")
        source = request.source_provider_session
        if policy == "new_thread":
            if source is not None:
                raise ProviderSessionError("AGENT_BINDING_DRIFT")
            return None
        if type(source) is not dict:
            raise ProviderSessionError("AGENT_BINDING_DRIFT")
        self._check_source_owner(request, source)
        if source.get("provider") != self.provider:
            raise ProviderSessionError("AGENT_BINDING_DRIFT")
        if request.operation.get("source_operation_ref"):
            if (source.get("operation_ref")
                    and source["operation_ref"] != request.operation["source_operation_ref"]):
                raise ProviderSessionError("AGENT_BINDING_DRIFT")
        for key in ("native_session_id", "native_thread_id", "native_turn_id"):
            if request.operation.get(key) and source.get(key):
                if request.operation[key] != source[key]:
                    raise ProviderSessionError("AGENT_BINDING_DRIFT")
        _required_text(source, "native_thread_id")
        return dict(source)

    def _source_or_operation(self, request: ProviderOperationRequest) -> dict:
        source = dict(request.source_provider_session or {})
        self._check_source_owner(request, source)
        merged = {**request.operation, **source}
        if merged.get("provider") != self.provider:
            raise ProviderSessionError("AGENT_BINDING_DRIFT")
        return merged

    def _check_source_owner(self, request: ProviderOperationRequest, source: dict) -> None:
        for key, expected in (("owner_ref", request.owner_ref),
                              ("journey_ref", request.journey_ref)):
            if source.get(key) and source[key] != expected:
                raise ProviderSessionError("AGENT_BINDING_DRIFT")

    def _watch_turn(self, client, transport, request, emit, request_approval,
                    cancelled, session, first_turn, native_history):
        status = first_turn.get("status", "")
        if status in {"completed", "failed", "interrupted"}:
            return _turn_outcome(session, native_history, first_turn, False)
        deadline = time.monotonic() + _timeout(request.operation, self.idle_timeout_s)
        cancel_ack = False
        inbound = _InboundOrdering()
        for _ in range(self.max_events):
            kind, item = inbound.next(transport)
            if kind is None and cancelled() and not cancel_ack:
                cancel_ack = _interrupt_turn(client, request, emit, session)
                continue
            if kind is None:
                kind, item = inbound.next(transport, wait_s=0.02)
            if kind in {"missing_sequence", "ambiguous_sequence"}:
                return _incomplete(kind, session=session)
            if kind is None:
                protocol = transport.pop_protocol_event(timeout=0.0)
                if protocol is not None and protocol.kind in {
                        "eof", "read_failed", "malformed_frame"}:
                    return _transport_failure(
                        protocol.kind, input_sent=True, session=session)
                if time.monotonic() >= deadline:
                    return _incomplete("timeout", session=session)
                continue
            if kind == "server_request":
                self._reply_to_server_request(
                    transport, item, request, emit, request_approval, session)
                continue
            note = item
            event = _notification_event(note, request, session)
            if _wrong_thread(event, session) or _wrong_turn(event, session):
                emit.native("ignored_native_event", **event)
                continue
            session["last_provider_event_id"] = event["last_provider_event_id"]
            emit.native("provider_event", **event)
            if note.method == "turn/completed":
                turn = note.params.get("turn") or {}
                return _turn_outcome(session, native_history, turn, cancel_ack)
        return _incomplete("event_bound_exceeded", session=session)

    def _reply_to_server_request(self, transport, server_request, request, emit,
                                 request_approval, session):
        if server_request.method not in _APPROVAL_DENIAL:
            _reply_or_fail(transport, server_request, session, error={
                "code": -32603, "message": "unsupported server request"})
            emit.native("approval_replied", decision="error",
                        **_server_request_event(server_request, request, session))
            return
        approval = _provider_approval(server_request, session)
        if _approval_matches_session(server_request, session):
            try:
                decision = request_approval(approval)
            except Exception:
                decision = None
            result = _approval_result(server_request.method, approval, decision)
        else:
            result = dict(_APPROVAL_DENIAL[server_request.method])
        _reply_or_fail(transport, server_request, session, result=result)
        emit.native("approval_replied",
                    decision=str(result.get("decision", "permissions")),
                    **_server_request_event(server_request, request, session))
