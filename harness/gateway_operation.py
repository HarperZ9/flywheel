"""Strict canonical operations for exact gateway grants."""
from __future__ import annotations
from dataclasses import dataclass, field
import math
import re
from types import MappingProxyType
from typing import Mapping
from urllib.parse import unquote
from .evidence_json import canonical_sha256
from .gateway_secret_boundary import validate_no_raw_secrets
REQUEST_SCHEMA = "flywheel.gateway-operation/v1"
PROPOSAL_SCHEMA = "flywheel.gateway-grant-proposal/v1"
PROPOSAL_REF_PATTERN = re.compile(r"prp_[0-9a-f]{32}\Z")
CREDENTIAL_REF_PATTERN = re.compile(r"cred_[0-9a-f]{32}\Z")
_SCOPES = ("write", "exec", "network", "plugin", "secrets")
OPERATION_REF_PATTERN = re.compile(r"op_[0-9a-f]{32}\Z")
_SECRET_NAMES = frozenset(("api_key", "access_token", "refresh_token", "token",
    "password", "secret", "credential", "credentials", "private_key",
    "authorization", "cookie", "environment", "env"))
_COMMAND_SECRET = re.compile(
    r"(?i)(?:^|[_-])(api[_-]?key|token|secret|password|credential)(?:$|[=_-])")
class GatewayOperationError(RuntimeError):
    """One fixed non-echoing operation-boundary failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)
@dataclass(frozen=True)
class CanonicalOperation:
    action: str
    tool: str
    destination: Mapping[str, str]
    operation: Mapping[str, object]
    operation_sha256: str
    arguments_sha256: str
    scopes: tuple[str, ...]
    data_refs: tuple[str, ...]
    credential_refs: tuple[str, ...]
@dataclass(frozen=True)
class AuthorizedOperation(CanonicalOperation):
    owner_ref: str
    journey_ref: str
    expected_event_head: str
    client_request_id: str
    grant_ref: str
    expires_at: str
    execution_plan: object | None = None
    credential_bindings: object | None = field(default=None, repr=False)

    @classmethod
    def for_test(cls, *, action: str, operation: dict,
                 scopes: tuple[str, ...]) -> "AuthorizedOperation":
        frozen = _freeze(_snapshot(operation))
        digest = canonical_sha256(operation)
        destination = _freeze(_destination(action, operation))
        tool = operation.get("tool", action)
        return cls(action, tool, destination, frozen, digest, digest,
                   scopes, tuple(operation.get("data_refs", ())),
                   tuple(operation.get("credential_refs", ())),
                   "owner_" + "a" * 32, "jrn_" + "a" * 32, "a" * 64,
                   "test-request", "gnt_" + "a" * 32,
                   "2026-08-15T12:02:00Z")
_REFS = {"data_refs", "credential_refs"}
_FIELDS = {
    "chat.complete": ({"model", "messages", "stream"} | _REFS, set()),
    "agent.run": ({"goal", "endpoint", "max_steps", "allow_write",
                   "allow_exec", "stream"} | _REFS,
                  {"root", "test_cmd", "attachment"}),
    "workflow.run": ({"workflow", "goal", "endpoint", "allow_write",
                      "allow_exec"} | _REFS,
                     {"profile", "root", "test_cmd"}),
    "plan.run": ({"workflow", "profile", "root", "endpoint", "allow_write",
                  "allow_exec", "binding"} | _REFS, {"test_cmd"}),
    "plugin.probe": ({"name"} | _REFS, set()),
    "plugin.call": ({"name", "tool", "arguments"} | _REFS, set()),
    "plugin.register": ({"name", "command", "detail", "requires"}
                        | _REFS, set()),
    "plugin.toggle": ({"name", "enabled"} | _REFS, set()),
    "plugin.remove": ({"name"} | _REFS, set()),
    "marketplace.install": ({"name"} | _REFS, set()),
    "marketplace.add": ({"name", "command", "detail", "requires",
                         } | _REFS, set()),
    "marketplace.remove": ({"name"} | _REFS, set()),
    "operation.cancel": ({"operation_ref", "timeout_ms"} | _REFS, set()),
    "companion.ask": ({"prompt"} | _REFS, {"solution_sig"}),
    "route.send": ({"prompt", "endpoint"} | _REFS, {"model"}),
    "forge.create": ({"goal"} | _REFS,
                     {"examples", "documentation", "context",
                      "intent_source", "architecture_source"}),
    "forge.recheck": ({"prp_id"} | _REFS, set()),
    "embeddings.create": ({"input"} | _REFS, {"model"}),
}
def action_for_path(path: str) -> str | None:
    return {
        "/v1/chat/completions": "chat.complete", "/api/agent": "agent.run",
        "/api/workflow": "workflow.run", "/api/plan/run": "plan.run",
        "/api/plugins/probe": "plugin.probe",
        "/api/plugins/call": "plugin.call",
        "/api/plugins/register": "plugin.register",
        "/api/plugins/toggle": "plugin.toggle",
        "/api/plugins/remove": "plugin.remove",
        "/api/marketplace/install": "marketplace.install",
        "/api/marketplace/add": "marketplace.add",
        "/api/marketplace/remove": "marketplace.remove",
        "/api/operations/cancel": "operation.cancel",
        "/api/companion": "companion.ask",
        "/api/route": "route.send",
        "/api/forge": "forge.create",
        "/api/forge/recheck": "forge.recheck",
        "/v1/embeddings": "embeddings.create",
    }.get(path)
def canonicalize_operation(action: str, operation: object) -> CanonicalOperation:
    try:
        if action not in _FIELDS or type(operation) is not dict:
            raise ValueError
        required, optional = _FIELDS[action]
        if set(operation) - required - optional or required - set(operation):
            raise ValueError
        snapshot = _snapshot(operation)
        _validate_shape(action, snapshot)
        validate_no_raw_secrets(snapshot)
        data_refs = tuple(snapshot["data_refs"])
        credentials = tuple(snapshot.get("credential_refs", ()))
        if (any(not _safe_ref(value, "data_") for value in data_refs)
                or any(CREDENTIAL_REF_PATTERN.fullmatch(value) is None
                       for value in credentials)
                or len(set(data_refs)) != len(data_refs)
                or len(set(credentials)) != len(credentials)
                or (action == "operation.cancel"
                    and bool(data_refs or credentials))):
            raise ValueError
        scopes = _derived_scopes(action, snapshot, bool(credentials))
        operation_sha = canonical_sha256({"action": action, "operation": snapshot})
        arguments_sha = canonical_sha256(snapshot)
        tool = snapshot.get("tool", action)
        return CanonicalOperation(action, tool, _freeze(_destination(
            action, snapshot)), _freeze(snapshot), operation_sha,
            arguments_sha, scopes, data_refs, credentials)
    except GatewayOperationError:
        raise
    except (KeyError, TypeError, ValueError, UnicodeError, RecursionError):
        raise GatewayOperationError("INVALID_REQUEST") from None
def thaw_operation(value: Mapping[str, object]) -> dict:
    def thaw(item):
        if isinstance(item, Mapping):
            return {key: thaw(child) for key, child in item.items()}
        if isinstance(item, tuple):
            return [thaw(child) for child in item]
        return item
    return thaw(value)
def materialize_agent_attachment(value: dict) -> dict:
    """Render an already-authorized relative attachment for the agent only."""
    result = dict(value)
    attachment = result.pop("attachment", None)
    if attachment is None:
        return result
    parts = [f"Active source: {attachment['relative_path']}"]
    if attachment.get("selection"):
        parts.append(f"Selected text:\n{attachment['selection']}")
    parts.append(f"Request:\n{result['goal']}")
    result["goal"] = "\n".join(parts)
    return result
def _snapshot(value: object) -> dict:
    remaining = [4096]
    def visit(item: object, depth: int):
        remaining[0] -= 1
        if remaining[0] < 0 or depth > 16:
            raise ValueError
        if item is None or type(item) in (str, bool, int):
            return item
        if type(item) is float and math.isfinite(item):
            return item
        if type(item) is list:
            return [visit(child, depth + 1) for child in item]
        if type(item) is dict and all(type(key) is str for key in item):
            return {key: visit(child, depth + 1) for key, child in item.items()}
        raise ValueError
    return visit(value, 0)


def _freeze(value: object):
    if type(value) is dict:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


def _text(value: object) -> bool:
    return type(value) is str and bool(value.strip())


def _relative_path(value: object) -> bool:
    if not _text(value) or len(value) > 1024:
        return False
    forms = [value]
    try:
        for _ in range(3):
            decoded = unquote(forms[-1], errors="strict")
            if decoded == forms[-1]:
                break
            forms.append(decoded)
    except (UnicodeError, ValueError):
        return False
    return all(not form.startswith(("/", "\\")) and ":" not in form
               and "\\" not in form
               and all(part not in ("", ".", "..")
                       for part in form.split("/")) for form in forms)


def _validate_shape(action: str, value: dict) -> None:
    # Lazy import: the shape module reads this module's patterns, so a
    # module-level import would cycle.
    from .gateway_operation_shape import validate_operation_shape
    validate_operation_shape(action, value)
    if "attachment" in value:
        attachment = value["attachment"]
        if (type(attachment) is not dict
                or set(attachment) not in ({"relative_path"},
                                           {"relative_path", "selection"})):
            raise ValueError
        path = attachment["relative_path"]
        if (not _relative_path(path)
                or ("selection" in attachment
                    and not _text(attachment["selection"]))):
            raise ValueError
    for name in ("command", "requires", "data_refs", "credential_refs"):
        if name in value and (type(value[name]) is not list
                              or any(not _text(item) for item in value[name])):
            raise ValueError
    if "command" in value:
        _validate_command(value["command"])
    if action == "plan.run":
        _validate_plan(value)


def _validate_plan(value: dict) -> None:
    from .plan_run_contract import PlanRunContractError, parse_plan_run_binding
    try:
        parse_plan_run_binding(value.get("binding"))
    except PlanRunContractError as exc:
        raise GatewayOperationError(exc.code) from None


def _validate_command(command: list) -> None:
    validate_no_raw_secrets({"argv": command})


def _safe_ref(value: object, prefix: str) -> bool:
    return (type(value) is str and value.startswith(prefix)
            and re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", value) is not None)


def _destination(action: str, value: dict) -> dict[str, str]:
    if action == "operation.cancel":
        return {"kind": "operation", "ref": value["operation_ref"]}
    if action == "chat.complete":
        return {"kind": "model", "ref": value["model"]}
    if action == "companion.ask":
        return {"kind": "model", "ref": "companion"}
    if action == "route.send":
        return {"kind": "endpoint", "ref": value["endpoint"]}
    if action == "forge.create":
        return {"kind": "forge", "ref": "forge"}
    if action == "forge.recheck":
        return {"kind": "forge", "ref": value["prp_id"]}
    if action == "embeddings.create":
        return {"kind": "model", "ref": value.get("model", "embeddings")}
    if action in {"agent.run", "workflow.run", "plan.run"}:
        return {"kind": "endpoint", "ref": value["endpoint"]}
    if action.startswith("plugin."):
        return {"kind": "plugin", "ref": value["name"]}
    return {"kind": "marketplace", "ref": value["name"]}


def _derived_scopes(action: str, value: dict, secrets: bool) -> tuple[str, ...]:
    selected = set()
    if action == "operation.cancel":
        selected.add("exec")
    if action in {"chat.complete", "agent.run", "workflow.run", "plan.run",
                  "companion.ask", "route.send", "forge.create",
                  "forge.recheck", "embeddings.create"}:
        selected.add("network")
    if action in {"plugin.call"}:
        selected.update(("write", "exec", "network", "plugin"))
    if action == "plugin.probe":
        selected.update(("exec", "network", "plugin"))
    if action in {"plugin.register", "plugin.toggle", "plugin.remove",
                  "marketplace.install", "marketplace.add",
                  "marketplace.remove"}:
        selected.update(("write", "plugin"))
    if action in {"agent.run", "workflow.run", "plan.run"}:
        if value.get("allow_write") is True: selected.add("write")
        if value.get("allow_exec") is True: selected.add("exec")
    if secrets: selected.add("secrets")
    return tuple(scope for scope in _SCOPES if scope in selected)
