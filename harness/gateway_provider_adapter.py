"""Fixed public failures for authorized external-action adapters."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .credential_handles import CredentialHandleStore
from .gateway_operation import GatewayOperationError


_LOCAL_MODELS = frozenset((
    "", "flywheel", "flywheel-serve", "serve", "default", "local", "auto",
))


def _credential_plan(operation) -> tuple[tuple[str, ...], tuple[str, ...]]:
    value, action = operation.operation, operation.action
    if action == "chat.complete":
        name = value["model"].split(":", 1)[0]
        if name in _LOCAL_MODELS:
            return (), ()
        from .endpoint_registry import credential_slots_for_endpoint
        return credential_slots_for_endpoint(name), ()
    if action in {"agent.run", "workflow.run"}:
        from .endpoint_registry import credential_slots_for_endpoint
        return credential_slots_for_endpoint(value["endpoint"]), ()
    if action in {"plugin.probe", "plugin.call"}:
        from .plugins import plugin_credentials
        return plugin_credentials(value["name"])
    if action == "plugin.register":
        return tuple(value["requires"]), ()
    if action in {"marketplace.install", "marketplace.remove"}:
        from .marketplace import marketplace_credentials
        return marketplace_credentials(value["name"])
    if action == "marketplace.add":
        return tuple(value["requires"]), ()
    return (), ()


def credential_slots(
        operation, owner_ref: str, state_root: Path) -> tuple[str, ...]:
    """Validate owner handle metadata against the server-derived frozen plan."""
    try:
        required, frozen_refs = _credential_plan(operation)
        refs = operation.credential_refs
        store = CredentialHandleStore(
            state_root, keychain_get=lambda _slot: None)
        actual = store.slot_names_exact(owner_ref, refs)
        if actual != required or frozen_refs and tuple(refs) != frozen_refs:
            raise GatewayOperationError("PERMISSION_REQUIRED")
        return required
    except GatewayOperationError:
        raise
    except Exception:
        raise GatewayOperationError("PERMISSION_REQUIRED") from None


def resolve_credentials(operation, state_root: Path):
    """Resolve exact handle values only after grant consumption."""
    required = credential_slots(operation, operation.owner_ref, state_root)
    try:
        from .keychain import keychain_get
        bindings = CredentialHandleStore(
            state_root, keychain_get=keychain_get).resolve_exact(
                operation.owner_ref, operation.credential_refs, required)
        return replace(operation, credential_bindings=bindings)
    except Exception:
        raise GatewayOperationError("PERMISSION_REQUIRED") from None


def fixed_external_failure() -> tuple[dict, int]:
    """Return the only public envelope for a failed external action."""
    return ({
        "schema": "flywheel.evidence-transport-error/v1",
        "error": {
            "code": "EXTERNAL_ACTION_FAILED",
            "message": "authorized external action failed",
        },
    }, 502)
