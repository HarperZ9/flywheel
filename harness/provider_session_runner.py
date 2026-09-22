"""Gateway-operation worker for provider-native session actions."""
from __future__ import annotations

from pathlib import Path
import threading
import time

from .gateway_agent_trace import AgentTrace
from .gateway_operation import AuthorizedOperation, thaw_operation
from .gateway_operation_process import WorkerOutcome
from .provider_session_contract import (
    ProviderApprovalDecision, ProviderApprovalRequest, ProviderOperationOutcome,
    ProviderOperationRequest, ProviderRuntimeBinding, ProviderSessionError,
    validate_provider,
)
from .provider_session_recovery import latest_provider_session_from_trace
from .provider_session_runtime_evidence import runtime_reconcile_evidence
from .provider_session_source import (
    bind_reconcile_result, source_context_for_operation,
)

PROVIDER_ACTIONS = frozenset({
    "provider.session.turn", "provider.session.resume",
    "provider.session.reconcile",
})
_WRITE_UNCERTAIN = frozenset({"write_uncertain", "response_write_uncertain"})


class ProviderSessionProcessFactory:
    def __init__(self, *, state_root: Path | str, adapters=None,
                 approval_resolver=None, approval_broker=None, registry=None):
        self.state_root = Path(state_root)
        self.adapters = dict(adapters or {})
        self.approval_resolver = approval_resolver
        self.approval_broker = approval_broker
        self.registry = registry
        self.provider_session_registry = registry

    def create(self, authorized: AuthorizedOperation, progress):
        if authorized.action not in PROVIDER_ACTIONS:
            raise ValueError("provider session action is invalid")
        ref = _operation_ref(authorized)
        return ProviderSessionWorker(
            authorized, ref, self.state_root, self.adapters,
            self.approval_resolver, self.approval_broker, self.registry, progress)


class ProviderSessionWorker:
    control_class = "windows_job_v1"

    def __init__(self, authorized, operation_ref, state_root, adapters,
                 approval_resolver, approval_broker, registry, progress):
        self.authorized, self.operation_ref = authorized, operation_ref
        self.state_root, self.adapters = Path(state_root), adapters
        self.approval_resolver, self.approval_broker = approval_resolver, approval_broker
        self.registry, self.progress = registry, progress
        self._done = threading.Event(); self._cancel = threading.Event()
        self._closed_frame = False
        self._outcome = None; self._thread = None; self.terminal_observed_at = None

    def resume(self) -> bool:
        if self._thread is not None:
            return False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def signal_tree(self) -> bool:
        if self._thread is None or self._done.is_set():
            return False
        self._cancel.set()
        return True

    def wait(self, timeout_s: float):
        self._done.wait(max(0.0, timeout_s))
        return self._outcome if self._done.is_set() else None

    def close(self) -> None:
        self._cancel.set()
        if self.approval_broker is not None:
            self.approval_broker.close_operation(
                owner_ref=self.authorized.owner_ref,
                operation_ref=self.operation_ref, reason="operation closed")
        if self._done.is_set() or self._closed_frame:
            return
        self._closed_frame = True
        try:
            op = thaw_operation(self.authorized.operation)
            trace = AgentTrace(
                self.state_root, self.authorized.owner_ref,
                self.authorized.journey_ref, self.operation_ref)
            trace.read()
            event = {"phase": "close_indeterminate",
                     "provider": op.get("provider", ""),
                     "action": self.authorized.action,
                     "operation_ref": self.operation_ref,
                     "history_status": "indeterminate",
                     "side_effect_status": "indeterminate"}
            trace.append("progress", event)
            self.progress({"provider_session": event})
        except Exception:
            pass

    def _run(self) -> None:
        try:
            self._outcome = _execute(
                self.authorized, self.operation_ref, self.state_root,
                self.adapters, self.approval_resolver, self.approval_broker,
                self.registry, self.progress, self._cancel.is_set)
        except Exception:
            self._outcome = WorkerOutcome(
                "failed", {"reason": "EXTERNAL_ACTION_FAILED"})
        self.terminal_observed_at = time.monotonic()
        if self.approval_broker is not None:
            self.approval_broker.close_operation(
                owner_ref=self.authorized.owner_ref,
                operation_ref=self.operation_ref, reason="operation terminal")
        self._done.set()


class _Emitter:
    def __init__(self, trace: AgentTrace, progress):
        self.trace, self.progress = trace, progress

    def native(self, phase: str, **payload) -> None:
        event = {"phase": phase, **payload}
        provider_session = _provider_session(event)
        if provider_session:
            event["provider_session"] = provider_session
        self.trace.append("progress", event)
        self.progress({"provider_session": event})


def _execute(authorized, ref, state_root, adapters, approval_resolver,
             approval_broker, registry, progress, cancelled):
    op = thaw_operation(authorized.operation)
    provider = validate_provider(op.get("provider"))
    trace = AgentTrace(state_root, authorized.owner_ref, authorized.journey_ref, ref)
    adapter = _adapter_for(provider, authorized, ref, registry, adapters)
    if adapter is None:
        return _finish(trace, "failed", {"reason": "AGENT_NATIVE_INCOMPLETE",
            "runtime_execution_disabled": True, "side_effect_status": "none",
            "history_status": "indeterminate"})
    try:
        source, source_binding = source_context_for_operation(
            authorized, op, state_root)
        binding = adapter.current_binding()
        runtime_evidence = (runtime_reconcile_evidence(
            registry, authorized=authorized, operation_ref=ref, operation=op, source_context=source_binding or {},
            binding=binding, state_root=state_root) if authorized.action == "provider.session.reconcile" else {})
    except ProviderSessionError as exc:
        return _finish(trace, "failed", {"reason": exc.code, **exc.detail})
    drift = _binding_drift(op, binding)
    if drift is not None:
        return _finish(trace, "failed", {"reason": "AGENT_BINDING_DRIFT", **drift})
    trace.append("progress", {
        "phase": "dispatch_intent", "provider": provider,
        "action": authorized.action, "operation_ref": ref,
        "side_effect_status": "not_sent"})
    request = ProviderOperationRequest(
        authorized.owner_ref, authorized.journey_ref, ref,
        authorized.action, op, source, source_binding, runtime_evidence,
        state_root)
    emit = _Emitter(trace, progress)
    try:
        if authorized.action == "provider.session.turn":
            outcome = adapter.start_turn(
                request, emit=emit,
                request_approval=_approval_callback(
                    approval_resolver, approval_broker, authorized, source),
                cancelled=cancelled)
        elif authorized.action == "provider.session.resume":
            outcome = adapter.resume(request, emit=emit)
        else:
            outcome = adapter.reconcile(request, emit=emit)
    except ProviderSessionError as exc:
        outcome = ProviderOperationOutcome.failed(exc.code, **exc.detail)
    if not isinstance(outcome, ProviderOperationOutcome):
        outcome = ProviderOperationOutcome.failed("AGENT_NATIVE_PROTOCOL_ERROR")
    try:
        state, result = _normalize_result(
            authorized.action, outcome, op, source_binding)
    except ProviderSessionError as exc:
        state, result = "failed", {"reason": exc.code, **exc.detail}
    if "provider_session" not in result:
        result["provider_session"] = (
            latest_provider_session_from_trace(trace.read()) or source or {
                "provider": provider, "config_digest": binding.config_digest,
                "capability_digest": binding.capability_digest})
    return _finish(trace, state, result)


def _finish(trace: AgentTrace, state: str, result: dict) -> WorkerOutcome:
    kind = "result" if state == "completed" else "failure"
    trace.append(kind, result)
    result = {**result, "trace_ref": trace.ref, "record_count": trace.count,
              "trace_head_sha256": trace.head}
    return WorkerOutcome(state, result)


def _normalize_result(action: str, outcome: ProviderOperationOutcome,
                      operation: dict | None = None,
                      source_binding: dict | None = None):
    result = dict(outcome.result)
    state = outcome.state if outcome.state in {"completed", "failed"} else "failed"
    if state == "failed":
        result.setdefault("reason", "AGENT_NATIVE_INCOMPLETE")
    uncertainty = _write_uncertainty(result)
    if uncertainty is not None:
        return "failed", {**result, "reason": "AGENT_NATIVE_INCOMPLETE",
            "history_status": "indeterminate",
            "side_effect_status": "indeterminate",
            "transport_uncertainty": uncertainty}
    if action == "provider.session.reconcile" and state == "completed":
        result = bind_reconcile_result(operation or {}, result, source_binding)
    return state, result


def _write_uncertainty(result: dict) -> str | None:
    for key in ("side_effect_status", "history_status", "transport_status",
                "transport_error", "provider_error_code", "reason"):
        value = result.get(key)
        if value in _WRITE_UNCERTAIN:
            return value
    return None


def _adapter_for(provider, authorized, ref, registry, adapters):
    if registry is not None:
        method = getattr(registry, "adapter_for", None)
        if callable(method):
            adapter = method(authorized=authorized, operation_ref=ref)
            if adapter is not None:
                return adapter
    return adapters.get(provider)


def _approval_callback(resolver, broker, authorized, source):
    def decide(request: ProviderApprovalRequest) -> ProviderApprovalDecision:
        try:
            identity = request.identity()
            if broker is not None:
                return _approval_decision_or_deny(
                    broker.request(request, authorized=authorized,
                                   source_provider_session=source), identity)
            if not callable(resolver):
                return ProviderApprovalDecision("deny", identity,
                                                "approval unavailable")
            decision = resolver(request, authorized=authorized,
                                source_provider_session=source)
            return _approval_decision_or_deny(decision, identity)
        except Exception:
            return ProviderApprovalDecision(
                "deny", "invalid", "approval unavailable")
    return decide


def _approval_decision_or_deny(decision, identity):
    if (not isinstance(decision, ProviderApprovalDecision)
            or decision.request_identity != identity
            or type(decision.message) is not str):
        return ProviderApprovalDecision("deny", identity,
                                        "approval identity mismatch")
    if decision.behavior == "deny" and decision.updated_input is None:
        return ProviderApprovalDecision("deny", identity, decision.message)
    if decision.behavior == "allow" and type(decision.updated_input) is dict:
        return ProviderApprovalDecision(
            "allow", identity, "", dict(decision.updated_input))
    return ProviderApprovalDecision("deny", identity,
                                    "approval shape invalid")


def _binding_drift(operation: dict, binding: ProviderRuntimeBinding):
    checks = (("provider", binding.provider, True),
              ("workspace_ref", binding.workspace_ref, True),
              ("config_digest", binding.config_digest, True),
              ("capability_digest", binding.capability_digest, False))
    for key, actual, required in checks:
        expected = operation.get(key)
        if required or key in operation:
            if type(expected) is not str or not expected.strip() or expected != actual:
                return {f"expected_{key}": expected, f"actual_{key}": actual}
    return None


def _provider_session(value: dict) -> dict:
    keys = ("provider", "native_session_id", "native_thread_id",
            "native_turn_id", "last_provider_event_id",
            "config_digest", "capability_digest")
    result = {key: value[key] for key in keys if type(value.get(key)) is str}
    return result if result.get("provider") else result


def _operation_ref(authorized: AuthorizedOperation) -> str:
    from .gateway_operation_route import operation_ref_for
    return operation_ref_for(
        authorized.owner_ref, authorized.journey_ref,
        authorized.client_request_id)
