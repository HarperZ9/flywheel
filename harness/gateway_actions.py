"""Dispatch helpers for already-authorized external gateway operations."""
from __future__ import annotations

from collections.abc import Callable, Mapping

from .gateway_operation import AuthorizedOperation


class GatewayDispatchError(RuntimeError):
    """A fixed error which never carries adapter exception text."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def dispatch_authorized(
        operation: AuthorizedOperation,
        handlers: Mapping[str, Callable[[AuthorizedOperation], object]]) -> object:
    """Invoke only the handler named by an immutable authorized operation."""
    if not isinstance(operation, AuthorizedOperation):
        raise GatewayDispatchError("INVALID_REQUEST")
    handler = handlers.get(operation.action)
    if not callable(handler):
        raise GatewayDispatchError("INVALID_REQUEST")
    try:
        return handler(operation)
    except GatewayDispatchError:
        raise
    except Exception:
        raise GatewayDispatchError("STORE_COMMIT_FAILED") from None


def _plugin(operation: AuthorizedOperation) -> object:
    from . import plugins
    value = operation.operation
    result = {
        "plugin.probe": lambda: plugins.probe_plugin(value["name"]),
        "plugin.call": lambda: plugins.call_plugin(
            value["name"], value["tool"], dict(value["arguments"])),
        "plugin.register": lambda: plugins.register_mcp(
            value["name"], list(value["command"]), value["detail"]),
        "plugin.toggle": lambda: plugins.toggle_mcp(
            value["name"], value["enabled"]),
        "plugin.remove": lambda: plugins.remove_mcp(value["name"]),
    }[operation.action]()
    if isinstance(result, dict) and result.get("status") == "unreachable":
        return {"name": value["name"], "kind": result.get("kind", "mcp"),
                "status": "unreachable", "detail": "plugin probe is unavailable"}
    if isinstance(result, dict) and "error" in result:
        return {"error": "plugin call is unavailable", "name": value["name"],
                "tool": value.get("tool", "")}
    return result


def _marketplace(operation: AuthorizedOperation) -> object:
    from . import marketplace
    value = operation.operation
    return {
        "marketplace.install": lambda: marketplace.install_from_catalog(
            value["name"]),
        "marketplace.add": lambda: marketplace.add_user_entry(
            value["name"], list(value["command"]), detail=value["detail"],
            requires=list(value["requires"])),
        "marketplace.remove": lambda: marketplace.remove_user_entry(
            value["name"]),
    }[operation.action]()


def dispatch_builtin(operation: AuthorizedOperation) -> tuple[object, int] | None:
    """Dispatch a short plugin/marketplace action after grant consumption."""
    groups = {
        "plugin.probe": _plugin, "plugin.call": _plugin,
        "plugin.register": _plugin, "plugin.toggle": _plugin,
        "plugin.remove": _plugin, "marketplace.install": _marketplace,
        "marketplace.add": _marketplace, "marketplace.remove": _marketplace,
    }
    if operation.action not in groups:
        return None
    result = dispatch_authorized(operation, groups)
    return result, 400 if isinstance(result, dict) and "error" in result else 200
