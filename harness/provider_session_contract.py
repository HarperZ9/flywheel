"""Provider-native session contracts for the gateway operation seam."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .evidence_json import canonical_sha256
from .journey_types import SHA256_PATTERN

PROVIDERS = frozenset({"codex", "claude"})
TURN_POLICIES = frozenset({
    "new_thread", "resume_after_reconcile", "reconcile_before_resend",
})


class ProviderSessionError(RuntimeError):
    def __init__(self, code: str, **detail):
        self.code = code
        self.detail = dict(detail)
        super().__init__(code)


@dataclass(frozen=True)
class ProviderRuntimeBinding:
    provider: str
    workspace_ref: str
    config_digest: str
    capability_digest: str = ""

    def as_result(self) -> dict:
        return {
            "provider": self.provider,
            "workspace_ref": self.workspace_ref,
            "config_digest": self.config_digest,
            "capability_digest": self.capability_digest,
        }


@dataclass(frozen=True)
class ProviderApprovalRequest:
    provider: str
    native_request_id: str
    tool: str
    payload_sha256: str
    native_session_id: str = ""
    native_thread_id: str = ""
    native_turn_id: str = ""
    native_item_id: str = ""

    def identity(self) -> str:
        if not (self.provider in PROVIDERS and self.native_request_id
                and self.tool and SHA256_PATTERN.fullmatch(self.payload_sha256)):
            raise ProviderSessionError("AGENT_NATIVE_PROTOCOL_ERROR")
        return canonical_sha256({
            "provider": self.provider,
            "native_request_id": self.native_request_id,
            "tool": self.tool,
            "payload_sha256": self.payload_sha256,
            "native_session_id": self.native_session_id,
            "native_thread_id": self.native_thread_id,
            "native_turn_id": self.native_turn_id,
            "native_item_id": self.native_item_id,
        })


@dataclass(frozen=True)
class ProviderApprovalDecision:
    behavior: str
    request_identity: str
    message: str = ""
    updated_input: dict[str, Any] | None = None

    @classmethod
    def deny(cls, request: ProviderApprovalRequest,
             message: str = "approval unavailable") -> "ProviderApprovalDecision":
        return cls("deny", request.identity(), message, None)

    @classmethod
    def allow(cls, request: ProviderApprovalRequest,
              updated_input: dict[str, Any]) -> "ProviderApprovalDecision":
        if type(updated_input) is not dict:
            raise ProviderSessionError("AGENT_NATIVE_PROTOCOL_ERROR")
        return cls("allow", request.identity(), "", dict(updated_input))


@dataclass(frozen=True)
class ProviderOperationOutcome:
    state: str
    result: dict[str, Any]

    @classmethod
    def completed(cls, result: dict[str, Any]) -> "ProviderOperationOutcome":
        return cls("completed", dict(result))

    @classmethod
    def failed(cls, reason: str, **result) -> "ProviderOperationOutcome":
        return cls("failed", {"reason": reason, **result})


@dataclass(frozen=True)
class ProviderOperationRequest:
    owner_ref: str
    journey_ref: str
    operation_ref: str
    action: str
    operation: dict[str, Any]
    source_provider_session: dict[str, Any] | None = None
    source_context: dict[str, Any] | None = None
    runtime_evidence: dict[str, Any] | None = None
    state_root: Any = None


class ProviderEventSink(Protocol):
    def native(self, phase: str, **payload) -> None: ...


class ProviderSessionAdapter(Protocol):
    provider: str
    def current_binding(self) -> ProviderRuntimeBinding: ...
    def start_turn(
        self, request: ProviderOperationRequest, *, emit: ProviderEventSink,
        request_approval: Callable[[ProviderApprovalRequest],
                                   ProviderApprovalDecision],
        cancelled: Callable[[], bool]) -> ProviderOperationOutcome: ...
    def resume(self, request: ProviderOperationRequest, *,
               emit: ProviderEventSink) -> ProviderOperationOutcome: ...
    def reconcile(self, request: ProviderOperationRequest, *,
                  emit: ProviderEventSink) -> ProviderOperationOutcome: ...


def validate_provider(value: object) -> str:
    if type(value) is not str or value not in PROVIDERS:
        raise ProviderSessionError("AGENT_NATIVE_PROTOCOL_ERROR")
    return value


def validate_turn_policy(value: object) -> str:
    if type(value) is not str or value not in TURN_POLICIES:
        raise ProviderSessionError("AGENT_NATIVE_PROTOCOL_ERROR")
    return value
