"""Claude start-turn policy preparation."""
from __future__ import annotations

import inspect

from .claude_session_contract import ClaudeSessionLaunchConfig
from .claude_provider_session_shapes import base_session, unsupported
from .provider_session_contract import (
    ProviderOperationOutcome,
    ProviderOperationRequest,
    ProviderRuntimeBinding,
    ProviderSessionError,
)

_SESSION_KEYS = (
    "provider", "native_session_id", "native_thread_id", "native_turn_id",
    "last_provider_event_id", "config_digest", "capability_digest",
)


def prepare_start_session(request: ProviderOperationRequest,
                          binding: ProviderRuntimeBinding
                          ) -> dict | ProviderOperationOutcome:
    policy = request.operation.get("resume_policy")
    if policy == "new_thread":
        if request.source_provider_session is not None:
            raise ProviderSessionError("AGENT_BINDING_DRIFT")
        if (request.operation.get("native_thread_id")
                or request.operation.get("native_turn_id")):
            raise ProviderSessionError("AGENT_BINDING_DRIFT")
        return base_session(binding)
    if policy != "resume_after_reconcile":
        _validate_source_identity(request)
        return unsupported()
    _validate_source_identity(request)
    return _source_session(request.source_provider_session or {}, binding)


def client_from_supplier(supplier, session: dict):
    return _client_from_supplier(supplier, launch_config_for_session({}, session))


def launch_client_from_supplier(supplier, request: ProviderOperationRequest,
                                session: dict):
    return _client_from_supplier(
        supplier, launch_config_for_session(request.operation, session))


def _client_from_supplier(supplier, config: ClaudeSessionLaunchConfig):
    try:
        params = inspect.signature(supplier).parameters.values()
    except (TypeError, ValueError):
        return supplier()
    accepts = any(param.kind in {
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.VAR_POSITIONAL,
    } for param in params)
    return supplier(config) if accepts else supplier()


def launch_config_for_session(operation: dict,
                              session: dict) -> ClaudeSessionLaunchConfig:
    return ClaudeSessionLaunchConfig(
        executable=str(operation.get("claude_executable") or "claude"),
        model=str(operation.get("model") or ""),
        permission_mode="manual",
        resume_session_id=(
            session.get("native_session_id", "")
            if operation.get("resume_policy") == "resume_after_reconcile"
            else ""),
        persist_session=True,
        replay_user_messages=True,
    )


def _validate_source_identity(request: ProviderOperationRequest) -> None:
    source = request.source_provider_session or {}
    if not source:
        raise ProviderSessionError("AGENT_BINDING_DRIFT")
    if source.get("provider") != "claude":
        raise ProviderSessionError("AGENT_BINDING_DRIFT")
    for key, expected in (("owner_ref", request.owner_ref),
                          ("journey_ref", request.journey_ref)):
        if source.get(key) and source[key] != expected:
            raise ProviderSessionError("AGENT_BINDING_DRIFT")
    for key in ("native_session_id", "native_thread_id", "native_turn_id"):
        if (request.operation.get(key) and source.get(key)
                and request.operation[key] != source[key]):
            raise ProviderSessionError("AGENT_BINDING_DRIFT")


def _source_session(source: dict, binding: ProviderRuntimeBinding) -> dict:
    if type(source.get("native_session_id")) is not str or not source["native_session_id"]:
        raise ProviderSessionError("AGENT_BINDING_DRIFT")
    session = {key: source.get(key, "") for key in _SESSION_KEYS}
    for key, actual in (("config_digest", binding.config_digest),
                        ("capability_digest", binding.capability_digest)):
        if session.get(key) and session[key] != actual:
            raise ProviderSessionError("AGENT_BINDING_DRIFT")
        session[key] = actual
    return session
