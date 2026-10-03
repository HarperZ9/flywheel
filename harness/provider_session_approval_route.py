"""HTTP route helpers for live provider-session approval custody."""
from __future__ import annotations

from urllib.parse import parse_qs

from .gateway_operation import GatewayOperationError
from .gateway_operation_validation import OPERATION_REF_PATTERN
from .provider_session_approval_broker import ProviderApprovalBroker


def broker_from(process_factory) -> ProviderApprovalBroker:
    broker = getattr(process_factory, "provider_session_approval_broker", None)
    if broker is None:
        broker = ProviderApprovalBroker()
        try:
            setattr(process_factory, "provider_session_approval_broker", broker)
        except Exception:
            pass
    return broker


def read_pending(query: str, *, owner_ref: str, broker: ProviderApprovalBroker) -> dict:
    values = parse_qs(query, keep_blank_values=True, strict_parsing=True)
    if set(values) != {"operation_ref"} or len(values["operation_ref"]) != 1:
        raise GatewayOperationError("INVALID_REQUEST")
    ref = values["operation_ref"][0]
    if OPERATION_REF_PATTERN.fullmatch(ref) is None:
        raise GatewayOperationError("INVALID_REQUEST")
    return {
        "schema": "flywheel.provider-session-approvals/v1",
        "operation_ref": ref,
        "pending": broker.pending(owner_ref=owner_ref, operation_ref=ref),
    }


def respond(raw: bytes, *, owner_ref: str, service, process_factory,
            broker: ProviderApprovalBroker) -> dict:
    authorized = service.authorizer(
        "provider.session.approval.respond", raw, owner_ref=owner_ref,
        state_root=service.state_root, clock=service.clock)
    return broker.respond(authorized)
