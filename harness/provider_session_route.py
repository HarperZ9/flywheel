"""Narrow provider-session HTTP routing helpers for gateway operations."""
from __future__ import annotations

from .gateway_operation import GatewayOperationError
from .provider_session_gateway_fields import PROVIDER_SESSION_PATHS


def route_provider_session(method: str, path: str, *, owner_ref: str, service,
                           process_factory, raw: bytes, query: str,
                           content_type: str, route_response, start):
    if path == "/api/provider-sessions/binding":
        if method != "POST" or query or content_type != "application/json":
            raise GatewayOperationError("INVALID_REQUEST")
        from .provider_session_runtime_binding import binding_route_body
        return route_response(200, binding_route_body(
            raw, owner_ref=owner_ref, state_root=service.state_root,
            registry=getattr(process_factory, "provider_session_registry", None)))
    if path == "/api/provider-sessions/approvals":
        if method != "GET":
            raise GatewayOperationError("INVALID_REQUEST")
        from .provider_session_approval_route import broker_from, read_pending
        return route_response(200, read_pending(query, owner_ref=owner_ref,
            broker=broker_from(process_factory)))
    if path == "/api/provider-sessions/approvals/respond":
        if method != "POST" or query or content_type != "application/json":
            raise GatewayOperationError("INVALID_REQUEST")
        from .provider_session_approval_route import broker_from, respond
        broker = broker_from(process_factory)
        return route_response(200, respond(raw, owner_ref=owner_ref,
            service=service, process_factory=process_factory, broker=broker))
    if path in PROVIDER_SESSION_PATHS:
        if method != "POST" or query or content_type != "application/json":
            raise GatewayOperationError("INVALID_REQUEST")
        from .provider_session_runner import ProviderSessionProcessFactory
        provider_factory = ProviderSessionProcessFactory(
            state_root=service.state_root,
            adapters=getattr(process_factory, "provider_session_adapters", None),
            approval_resolver=getattr(
                process_factory, "provider_session_approval_resolver", None),
            approval_broker=getattr(
                process_factory, "provider_session_approval_broker", None),
            registry=getattr(process_factory, "provider_session_registry", None))
        return start(PROVIDER_SESSION_PATHS[path], raw, owner_ref,
                     service, provider_factory)
    return None
