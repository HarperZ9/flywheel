"""Private runtime evidence handoff for provider-session workers."""
from __future__ import annotations

from .provider_session_contract import ProviderSessionError


def runtime_reconcile_evidence(registry, **kwargs) -> dict:
    if registry is None:
        return {}
    method = getattr(registry, "reconcile_evidence", None)
    if not callable(method):
        return {}
    try:
        value = method(**kwargs)
    except ProviderSessionError:
        raise
    except Exception as exc:
        raise ProviderSessionError(
            "AGENT_NATIVE_INCOMPLETE",
            history_status="indeterminate",
            side_effect_status="indeterminate",
            detail_code="runtime_evidence_unavailable") from exc
    if type(value) is not dict:
        raise ProviderSessionError(
            "AGENT_NATIVE_INCOMPLETE",
            history_status="indeterminate",
            side_effect_status="indeterminate",
            detail_code="runtime_evidence_unavailable")
    return dict(value)
