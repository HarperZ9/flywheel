"""Adapter dispatch step for the provider-session gateway worker."""
from __future__ import annotations

from .provider_session_contract import ProviderOperationOutcome, ProviderSessionError


def dispatch_provider_operation(adapter, authorized, request, emit, approval_callback, cancelled):
    try:
        if authorized.action == "provider.session.turn":
            outcome = adapter.start_turn(
                request, emit=emit, request_approval=approval_callback(),
                cancelled=cancelled)
        elif authorized.action == "provider.session.resume":
            outcome = adapter.resume(request, emit=emit)
        else:
            outcome = adapter.reconcile(request, emit=emit)
    except ProviderSessionError as exc:
        outcome = ProviderOperationOutcome.failed(exc.code, **exc.detail)
    if not isinstance(outcome, ProviderOperationOutcome):
        outcome = ProviderOperationOutcome.failed("AGENT_NATIVE_PROTOCOL_ERROR")
    return outcome
