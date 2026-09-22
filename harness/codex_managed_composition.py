"""Server-owned composition for managed Codex account and runtime seams."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
from typing import Any

from .codex_account_safety import owner_ref as checked_owner_ref
from .codex_account_state import rejected_response, route_state
from .codex_account_sessions import CodexAccountSessionManager, CodexAccountUnavailable
from .codex_account_binding import ManagedCodexAccountBinding
from .evidence_json import canonical_sha256
from .private_artifact_fs import root_identity

_HEX64 = re.compile(r"[0-9a-fA-F]{64}\Z")


class ManagedCodexCompositionError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class StartupWorkspaceBinding:
    root: Path; workspace_ref: str; identity: dict


@dataclass(frozen=True)
class ManagedCodexServerConfig:
    executable: Path; executable_sha256: str; model: str
    codex_version: str; policy_root: Path; version_provenance: str = "configured"

    def as_digest_material(self) -> dict:
        return {"executable": str(self.executable),
            "executable_sha256": self.executable_sha256, "model": self.model,
            "codex_version": self.codex_version, "policy_root": str(self.policy_root),
            "version_provenance": self.version_provenance}


@dataclass(frozen=True)
class ManagedCodexComponents:
    operation_service: Any; operation_process_factory: Any
    codex_account_manager: Any; provider_session_registry: Any
    composition: Any; digest: str; state_root: Path

    def shutdown(self) -> bool:
        manager_close = getattr(self.codex_account_manager, "shutdown", None)
        manager_ok = True if manager_close is None else manager_close()
        composition_close = getattr(self.composition, "shutdown", None)
        composition_ok = True if composition_close is None else composition_close()
        return bool(manager_ok and composition_ok)


def managed_codex_server_config(*, executable: str | os.PathLike[str] | None = None,
        executable_sha256: str | None = None, model: str | None = None,
        codex_version: str | None = None,
        policy_root: str | os.PathLike[str] | None = None,
        version_provenance: str = "configured") -> ManagedCodexServerConfig | None:
    values = (executable, executable_sha256, model, codex_version, policy_root)
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise ManagedCodexCompositionError("AGENT_NATIVE_CONFIG_INCOMPLETE")
    model_value = _public_text(model)
    if model_value is None:
        raise ManagedCodexCompositionError("MODEL_SELECTION_REQUIRED")
    version_value = _public_text(codex_version)
    provenance = _public_text(version_provenance)
    if version_value is None:
        raise ManagedCodexCompositionError("AGENT_NATIVE_CONFIG_INCOMPLETE")
    if provenance is None:
        raise ManagedCodexCompositionError("AGENT_NATIVE_CONFIG_INCOMPLETE")
    digest = str(executable_sha256).lower()
    if _HEX64.fullmatch(digest) is None:
        raise ManagedCodexCompositionError("AGENT_NATIVE_CONFIG_INCOMPLETE")
    exe = Path(executable).expanduser().resolve()
    policy = Path(policy_root).expanduser().resolve()
    if not exe.is_file():
        raise ManagedCodexCompositionError("AGENT_NATIVE_EXECUTABLE_UNAVAILABLE")
    if _sha256_file(exe) != digest:
        raise ManagedCodexCompositionError("AGENT_NATIVE_EXECUTABLE_MISMATCH")
    return ManagedCodexServerConfig(exe, digest, model_value, version_value, policy, provenance)


def startup_workspace_binding(root: str | os.PathLike[str]) -> StartupWorkspaceBinding:
    path = Path(root).expanduser().resolve()
    if not path.is_dir():
        raise ManagedCodexCompositionError("AGENT_NATIVE_WORKSPACE_UNAVAILABLE")
    identity_key = str(path).lower() if os.name == "nt" else str(path)
    return StartupWorkspaceBinding(
        path, hashlib.sha256(identity_key.encode("utf-8")).hexdigest(),
        root_identity(path).to_json_dict())


def build_managed_codex_components(
        *, repo_root: str | os.PathLike[str], run_root: str | os.PathLike[str],
        state_root: str | os.PathLike[str], clock, config: ManagedCodexServerConfig | None = None,
        current: ManagedCodexComponents | None = None,
        lifecycle: Any = None) -> ManagedCodexComponents:
    workspace = startup_workspace_binding(repo_root)
    state = Path(state_root).expanduser().resolve()
    run = Path(run_root).expanduser().resolve()
    desired = _composition_digest(workspace, state, config)
    if current is not None and current.digest == desired:
        return current
    held = None
    disabled_reason = None
    if current is not None and not current.shutdown():
        held = current.composition
        disabled_reason = "AGENT_NATIVE_CLEANUP_REQUIRED"
        config = None
    composition = ManagedCodexComposition(
        state_root=state, workspace=workspace, config=config,
        lifecycle=lifecycle, disabled_reason=disabled_reason,
        held_composition=held)
    registry = composition.runtime_registry()
    manager = _account_manager(composition, config, disabled_reason)
    from .gateway_operations import GatewayOperations
    from .gateway_operation_process import GatewayOperationProcessFactory
    from .provider_session_approval_broker import ProviderApprovalBroker
    factory = GatewayOperationProcessFactory(
        repo_root=workspace.root, run_root=run, state_root=state)
    factory.provider_session_registry = registry
    factory.provider_session_adapters = {}
    factory.provider_session_approval_resolver = None
    factory.provider_session_approval_broker = ProviderApprovalBroker()
    return ManagedCodexComponents(
        GatewayOperations(state, clock=clock), factory, manager, registry,
        composition, desired, state)


class ManagedCodexComposition:
    def __init__(self, *, state_root: Path, workspace: StartupWorkspaceBinding,
                 config: ManagedCodexServerConfig | None,
                 lifecycle: Any,
                 disabled_reason: str | None = None,
                 held_composition: Any = None) -> None:
        self.state_root, self.workspace = Path(state_root), workspace
        self.config, self.lifecycle = config, lifecycle
        self.disabled_reason = disabled_reason
        self.held_composition = held_composition
        self.digest = _composition_digest(workspace, self.state_root, config)

    def account_client_for_owner(self, *, owner_ref: str) -> ManagedCodexAccountBinding:
        owner = checked_owner_ref(owner_ref)
        if self.disabled_reason:
            raise CodexAccountUnavailable("unavailable", reason=self.disabled_reason)
        if self.config is None:
            raise CodexAccountUnavailable("unavailable", reason="AGENT_NATIVE_RUNTIME_DISABLED")
        if self.lifecycle is None:
            raise CodexAccountUnavailable("baseline_pending", reason="AGENT_NATIVE_BASELINE_PENDING")
        client = self.lifecycle.account_client_for_owner(owner_ref=owner)
        if client is None:
            raise CodexAccountUnavailable("baseline_pending", reason="AGENT_NATIVE_BASELINE_PENDING")
        if not isinstance(client, ManagedCodexAccountBinding):
            raise CodexAccountUnavailable("baseline_failed", reason="AGENT_NATIVE_PROTOCOL_ERROR")
        return client

    def record_login_success(self, _ctx):
        if self.lifecycle is None:
            raise RuntimeError("managed inventory lifecycle pending")
        from .codex_managed_login_receipt_writer import record_login_success
        ref = record_login_success(_ctx)
        accept = getattr(self.lifecycle, "accept_verified_inventory", None)
        if not callable(accept):
            raise RuntimeError("managed inventory update hook pending")
        return accept(_ctx.owner_ref, ref)

    def runtime_registry(self):
        from .codex_managed_runtime_adapter import ManagedCodexRuntimeRegistry
        return ManagedCodexRuntimeRegistry(self)

    def shutdown(self) -> bool:
        close = getattr(self.lifecycle, "shutdown", None)
        return True if close is None else close()


class DisabledCodexAccountManager:
    def __init__(self, reason: str, *, state: str = "unavailable", status: int = 503) -> None:
        self.reason, self.state, self.status = reason, state, status

    def read_status(self, _owner_ref):
        return route_state(self.state, reason=self.reason), self.status

    def login_result(self, _owner_ref, _login_id):
        return route_state(self.state, reason=self.reason), self.status

    def start_login(self, _owner_ref, _mode, *, visible_ui_action=False):
        if not visible_ui_action: return rejected_response()
        return route_state(self.state, reason=self.reason), self.status

    def cancel_login(self, _owner_ref, _login_id, *, visible_ui_action=False):
        if not visible_ui_action: return rejected_response()
        return route_state(self.state, reason=self.reason), self.status

    def logout(self, _owner_ref, *, visible_ui_action=False):
        if not visible_ui_action: return rejected_response()
        return route_state(self.state, reason=self.reason), self.status

    def shutdown(self) -> bool:
        return True


def _account_manager(composition, config, disabled_reason):
    if disabled_reason:
        return DisabledCodexAccountManager(disabled_reason)
    if config is None:
        return DisabledCodexAccountManager("AGENT_NATIVE_RUNTIME_DISABLED")
    return CodexAccountSessionManager(
        owner_client_factory=composition.account_client_for_owner,
        login_success_hook=composition.record_login_success)


def _composition_digest(workspace, state_root: Path,
                        config: ManagedCodexServerConfig | None) -> str:
    return canonical_sha256({
        "schema": "flywheel.codex-managed-composition/v1",
        "state_root": str(Path(state_root)),
        "workspace": {
            "root": str(workspace.root),
            "workspace_ref": workspace.workspace_ref,
            "identity": workspace.identity,
        },
        "config": config.as_digest_material() if config else None,
    })


def _sha256_file(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _public_text(value: object) -> str | None:
    if type(value) is not str:
        return None
    value = value.strip()
    if not value or any(ord(ch) < 32 for ch in value):
        return None
    return value
