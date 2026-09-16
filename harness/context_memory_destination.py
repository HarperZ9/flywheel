"""Owner-scoped destination binding for the Canon context bridge."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

from .canon_context_runtime import context_db_configured
from .operation_grants import OWNER_REF_PATTERN

DESTINATION_BINDING_SCHEMA = "flywheel.context-memory-destination-binding/v1"
ENV_CONTEXT_CONTAINER = "FLYWHEEL_CANON_CONTEXT_CONTAINER_ID"
DEFAULT_CONTEXT_CONTAINER = "flywheel-desktop"
_SAFE_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_STORE_ID = re.compile(r"ctxstore_[0-9a-f]{32}\Z")


class DestinationBindingError(ValueError):
    def __init__(self, code: str, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


@dataclass(frozen=True)
class ContextMemoryConfig:
    workspace_id: str = ""
    project_id: str = ""
    project_aliases: tuple[str, ...] = ()
    owner_refs: tuple[str, ...] = ()
    container_id: str = ""
    db_path_sha256: str = ""

    @classmethod
    def from_environment(cls, env: dict[str, str] | None = None) -> "ContextMemoryConfig":
        env = env or os.environ
        raw_container = env.get(ENV_CONTEXT_CONTAINER)
        container_id = (_env_ref(raw_container) if raw_container is not None
                        else DEFAULT_CONTEXT_CONTAINER)
        return cls(workspace_id=_env_ref(env.get("FLYWHEEL_CANON_CONTEXT_WORKSPACE_ID")),
                   project_id=_env_ref(env.get("FLYWHEEL_CANON_CONTEXT_PROJECT_ID")),
                   project_aliases=_safe_csv(env.get("FLYWHEEL_CANON_CONTEXT_PROJECT_ALIASES"), _env_ref),
                   owner_refs=_safe_csv(env.get("FLYWHEEL_CANON_CONTEXT_OWNER_REFS"), _owner_env_ref),
                   container_id=container_id,
                   db_path_sha256=_db_path_sha256(env.get("FLYWHEEL_CANON_CONTEXT_DB")))

    def scope_binding(self, owner_ref: str, project_ref: str) -> dict:
        owner, requested = _owner(owner_ref), _safe_ref(project_ref, "project_ref")
        if not self.workspace_id or not self.project_id:
            raise DestinationBindingError("CANON_CONTEXT_SCOPE_UNCONFIGURED",
                                          "Canon context workspace/project binding is not configured", 503)
        if not self.owner_refs:
            raise DestinationBindingError("CANON_CONTEXT_OWNER_UNCONFIGURED",
                                          "Canon context owner binding is not configured", 503)
        if owner not in self.owner_refs:
            raise DestinationBindingError("CONTEXT_OWNER_NOT_BOUND",
                                          "gateway owner is not bound to this Canon scope", 403)
        allowed = {self.project_id, *self.project_aliases}
        if requested not in allowed:
            raise DestinationBindingError("CONTEXT_SCOPE_NOT_BOUND",
                                          "requested project is not bound to this Canon scope", 403)
        return {"workspace_id": self.workspace_id, "canonical_project_id": self.project_id,
                "request_project_ref": requested, "owner_ref": owner,
                "binding_source": "configured-owner-and-canon-scope/v1"}

    def config_generation(self, owner_ref: str) -> str:
        owner = _owner(owner_ref)
        if not (self.workspace_id and self.project_id and self.container_id and self.db_path_sha256):
            raise DestinationBindingError("CANON_CONTEXT_DESTINATION_UNCONFIGURED",
                                          "Canon context destination binding is not configured", 503)
        if not self.owner_refs:
            raise DestinationBindingError("CANON_CONTEXT_OWNER_UNCONFIGURED",
                                          "Canon context owner binding is not configured", 503)
        if owner not in self.owner_refs:
            raise DestinationBindingError("CONTEXT_OWNER_NOT_BOUND",
                                          "gateway owner is not bound to this Canon scope", 403)
        return _canonical_sha256({
            "schema": "flywheel.context-memory-config-generation/v1",
            "backend": "canon.context_mcp",
            "container_id": self.container_id,
            "workspace_id": self.workspace_id,
            "canonical_project_id": self.project_id,
            "project_aliases": sorted(set(self.project_aliases)),
            "owner_ref": owner,
            "db_path_sha256": self.db_path_sha256,
        })

    def destination_binding(self, owner_ref: str, canon_health: dict) -> dict:
        store_id = canon_health.get("store_id") if isinstance(canon_health, dict) else None
        if not valid_store_id(store_id):
            raise DestinationBindingError("CANON_CONTEXT_STORE_UNBOUND",
                                          "Canon context store identity is unavailable", 503)
        return destination_binding(self.config_generation(owner_ref), store_id)


def request_destination_binding(req: dict) -> dict | None:
    has_generation = "config_generation" in req
    has_store = "canon_store_id" in req
    if has_generation != has_store:
        raise DestinationBindingError("INVALID_DESTINATION_BINDING",
                                      "context destination binding is incomplete")
    if not has_generation:
        return None
    return destination_binding(_sha256_ref(req["config_generation"], "config_generation"),
                               _store_id(req["canon_store_id"]))


def context_memory_tool_descriptors() -> list[dict]:
    owner = {"type": "string", "description": "gateway owner_ref allowed by configured binding"}
    project = {"type": "string", "description": "configured Canon project id or alias"}
    destination = {
        "config_generation": {"type": "string", "description": "opaque status binding generation"},
        "canon_store_id": {"type": "string", "description": "Canon health store_id expected by operation"},
    }
    base = {"owner_ref": owner, "schema": {"type": "string"}, "project_ref": project}
    return [
        {"name": "flywheel.context.health",
         "description": "Report Canon-backed context memory bridge status and limits.",
         "inputSchema": {"type": "object", "properties": {"owner_ref": owner},
                         "additionalProperties": False}},
        {"name": "flywheel.context.capture",
         "description": "Capture received context into the configured Canon context store.",
         "inputSchema": {"type": "object", "required": ["owner_ref", "schema", "project_ref", "event"],
                         "properties": dict(base, **destination, event={"type": "object"}),
                         "additionalProperties": False}},
        {"name": "flywheel.context.preflight",
         "description": "Search the configured Canon context store before assuming context is new.",
         "inputSchema": {"type": "object", "required": ["owner_ref", "schema", "project_ref", "query"],
                         "properties": dict(base, **destination,
                                            query={"type": "string"}, top_k={"type": "integer"},
                                            include_pending_extraction={"type": "boolean"}),
                         "additionalProperties": False}},
    ]


def destination_binding(config_generation: str, canon_store_id: str) -> dict:
    return {"schema": DESTINATION_BINDING_SCHEMA,
            "config_generation": config_generation,
            "canon_store_id": canon_store_id,
            "same_store_check": "canon.expected_store_id.transaction/v1"}


def valid_store_id(value: Any) -> bool:
    return type(value) is str and _STORE_ID.fullmatch(value) is not None


def canon_store_identity_error(text: str) -> bool:
    normalized = text.lower()
    return "context store identity" in normalized or "expected_store_id" in normalized


def _owner(value: str) -> str:
    if type(value) is not str or OWNER_REF_PATTERN.fullmatch(value) is None:
        raise DestinationBindingError("OWNER_REQUIRED", "valid owner_ref is required", 403)
    return value


def _safe_ref(value: Any, field: str) -> str:
    if type(value) is not str or _SAFE_REF.fullmatch(value) is None:
        raise DestinationBindingError("INVALID_REQUEST", f"{field} is invalid")
    return value


def _env_ref(value: str | None) -> str:
    return value if type(value) is str and _SAFE_REF.fullmatch(value) else ""


def _owner_env_ref(value: str | None) -> str:
    return value if type(value) is str and OWNER_REF_PATTERN.fullmatch(value) else ""


def _safe_csv(value: str | None, clean) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item for raw in value.split(",") if (item := clean(raw.strip())))


def _sha256_ref(value: Any, field: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise DestinationBindingError("INVALID_DESTINATION_BINDING", f"{field} is invalid")
    return value


def _store_id(value: Any) -> str:
    if not valid_store_id(value):
        raise DestinationBindingError("INVALID_DESTINATION_BINDING", "canon_store_id is invalid")
    return value


def _canonical_sha256(value: dict) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _db_path_sha256(value: str | None) -> str:
    if not context_db_configured(value):
        return ""
    normalized = str(Path(value).expanduser().resolve(strict=False)).replace("\\", "/")
    if os.name == "nt":
        normalized = normalized.lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
