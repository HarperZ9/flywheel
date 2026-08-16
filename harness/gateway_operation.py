"""Strict canonical operations for exact gateway grants."""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from types import MappingProxyType
from typing import Mapping
from urllib.parse import parse_qsl, urlsplit

from .bundle import scan_for_secrets
from .evidence_json import canonical_sha256
from .journey_types import JOURNEY_REF_PATTERN, SHA256_PATTERN

REQUEST_SCHEMA = "flywheel.gateway-operation/v1"
PROPOSAL_SCHEMA = "flywheel.gateway-grant-proposal/v1"
PROPOSAL_REF_PATTERN = re.compile(r"prp_[0-9a-f]{32}\Z")
CREDENTIAL_REF_PATTERN = re.compile(r"cred_[0-9a-f]{32}\Z")
_SCOPES = ("write", "exec", "network", "plugin", "secrets")
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

    @classmethod
    def for_test(cls, *, action: str, operation: dict,
                 scopes: tuple[str, ...]) -> "AuthorizedOperation":
        frozen = _freeze(_snapshot(operation))
        digest = canonical_sha256(operation)
        return cls(action, action, frozen, digest, digest, scopes, (), (),
                   "owner_" + "a" * 32, "jrn_" + "a" * 32, "a" * 64,
                   "test-request", "gnt_" + "a" * 32,
                   "2026-08-15T12:02:00Z")


_FIELDS = {
    "chat.complete": ({"model", "messages", "stream"}, set()),
    "agent.run": ({"goal", "endpoint", "max_steps", "allow_write",
                   "allow_exec", "stream"}, {"root", "test_cmd"}),
    "workflow.run": ({"workflow", "goal", "endpoint", "allow_write",
                      "allow_exec"}, {"profile", "root", "test_cmd"}),
    "plugin.probe": ({"name"}, set()),
    "plugin.call": ({"name", "tool", "arguments", "credential_refs"}, set()),
    "plugin.register": ({"name", "command", "detail", "credential_refs"}, set()),
    "plugin.toggle": ({"name", "enabled"}, set()),
    "plugin.remove": ({"name"}, set()),
    "marketplace.install": ({"name"}, set()),
    "marketplace.add": ({"name", "command", "detail", "requires",
                         "credential_refs"}, set()),
    "marketplace.remove": ({"name"}, set()),
}


def action_for_path(path: str) -> str | None:
    return {
        "/v1/chat/completions": "chat.complete", "/api/agent": "agent.run",
        "/api/workflow": "workflow.run", "/api/plugins/probe": "plugin.probe",
        "/api/plugins/call": "plugin.call",
        "/api/plugins/register": "plugin.register",
        "/api/plugins/toggle": "plugin.toggle",
        "/api/plugins/remove": "plugin.remove",
        "/api/marketplace/install": "marketplace.install",
        "/api/marketplace/add": "marketplace.add",
        "/api/marketplace/remove": "marketplace.remove",
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
        _reject_secrets(snapshot)
        credentials = tuple(snapshot.get("credential_refs", ()))
        if any(CREDENTIAL_REF_PATTERN.fullmatch(value) is None
               for value in credentials):
            raise ValueError
        scopes = _derived_scopes(action, snapshot, bool(credentials))
        operation_sha = canonical_sha256({"action": action, "operation": snapshot})
        arguments_sha = canonical_sha256(snapshot)
        return CanonicalOperation(
            action, action, _freeze(snapshot), operation_sha, arguments_sha,
            scopes, credentials, credentials)
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


def _validate_shape(action: str, value: dict) -> None:
    text_fields = {"model", "goal", "endpoint", "workflow", "profile", "root",
                   "test_cmd", "name", "tool", "detail"}
    if any(key in value and not _text(value[key]) for key in text_fields):
        raise ValueError
    if action == "chat.complete":
        messages = value["messages"]
        if (type(messages) is not list or not messages
                or any(type(item) is not dict
                       or set(item) != {"role", "content"}
                       or item["role"] not in {"system", "user", "assistant"}
                       or type(item["content"]) is not str for item in messages)):
            raise ValueError
    for name in ("stream", "allow_write", "allow_exec", "enabled"):
        if name in value and type(value[name]) is not bool:
            raise ValueError
    if "max_steps" in value and (type(value["max_steps"]) is not int
                                  or not 1 <= value["max_steps"] <= 12):
        raise ValueError
    if "arguments" in value and type(value["arguments"]) is not dict:
        raise ValueError
    for name in ("command", "requires", "credential_refs"):
        if name in value and (type(value[name]) is not list
                              or any(not _text(item) for item in value[name])):
            raise ValueError
    if "command" in value:
        _validate_command(value["command"])


def _secret_name(value: str) -> bool:
    name = value.lower().replace("-", "_")
    return name in _SECRET_NAMES or name.endswith((
        "_api_key", "_private_key", "_password", "_secret", "_credential",
        "_token"))


def _reject_secrets(value: object, key: str = "") -> None:
    if type(value) is dict:
        for name, item in value.items():
            if name != "credential_refs" and _secret_name(name):
                raise ValueError
            _reject_secrets(item, name)
    elif type(value) is list:
        for item in value:
            _reject_secrets(item, key)
    elif type(value) is str and key != "credential_refs":
        if scan_for_secrets(value):
            raise ValueError
        try:
            parsed = urlsplit(value)
            names = [name for name, _ in parse_qsl(parsed.query)]
            if parsed.username is not None or parsed.password is not None or any(
                    _secret_name(name) for name in names):
                raise ValueError
        except ValueError:
            raise


def _validate_command(command: list) -> None:
    for index, value in enumerate(command):
        if ("=" in value and _COMMAND_SECRET.search(value.partition("=")[0])
                or value.startswith("-") and _COMMAND_SECRET.search(value)
                or index and _COMMAND_SECRET.search(command[index - 1])):
            raise ValueError


def _derived_scopes(action: str, value: dict, secrets: bool) -> tuple[str, ...]:
    selected = set()
    if action in {"chat.complete", "agent.run", "workflow.run"}:
        selected.add("network")
    if action in {"plugin.call"}:
        selected.update(("write", "exec", "network", "plugin"))
    if action == "plugin.probe":
        selected.update(("exec", "network", "plugin"))
    if action in {"plugin.register", "plugin.toggle", "plugin.remove",
                  "marketplace.install", "marketplace.add",
                  "marketplace.remove"}:
        selected.update(("write", "plugin"))
    if action in {"agent.run", "workflow.run"}:
        if value.get("allow_write") is True: selected.add("write")
        if value.get("allow_exec") is True: selected.add("exec")
    if secrets: selected.add("secrets")
    return tuple(scope for scope in _SCOPES if scope in selected)
