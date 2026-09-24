"""Owned Claude SDK runtime launcher custody; not production admission."""
from __future__ import annotations

from collections.abc import Mapping
from contextlib import ExitStack
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import threading
from types import MappingProxyType
from typing import Any

from .claude_managed_profile import (
    ClaudeManagedProfile,
    lease_claude_profile,
    prepare_claude_profile,
)
from .claude_session_client import ClaudeSessionCleanupError, ClaudeSessionClient
from .claude_session_contract import ClaudeSessionLaunchConfig
from .gateway_cli_runtime import session_env
from .provider_session_contract import ProviderSessionError
from .provider_session_process import ProviderSessionProcessError, start_provider_session_process


_DEFAULT_MCP_CONFIG = {"mcpServers": {}}
_DEFAULT_SETTINGS = {"disableAllHooks": True}
_LIMITATIONS = ("provider_policy_not_attested", "administrator_hooks_not_attested",
                "no_generation_runtime_check_not_run", "no_tool_initialization_only",
                "production_tool_approval_not_proven", "not_registry_admission")
_cleanup_holds: list[_HeldClaudeRuntime] = []
_custody_lock = threading.RLock()


@dataclass(frozen=True)
class ClaudeManagedSessionPolicy:
    permission_mode: str = "manual"
    permission_prompt_tool_name: str = "stdio"
    safe_mode: bool = True
    restricted: bool = True
    setting_sources: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    strict_mcp_config: bool = True
    mcp_config: Mapping[str, Any] = field(default_factory=lambda: {"mcpServers": {}})
    settings: Mapping[str, Any] = field(default_factory=lambda: {"disableAllHooks": True})
    allowed_tools: tuple[str, ...] = ()
    disallowed_tools: tuple[str, ...] = ("mcp__*",)


@dataclass(frozen=True)
class ClaudeRuntimeAdmission:
    profile: ClaudeManagedProfile
    policy: ClaudeManagedSessionPolicy

    @property
    def admitted(self) -> bool: return False

    @property
    def limitations(self) -> tuple[str, ...]: return _LIMITATIONS

    @property
    def profile_home(self) -> Path: return self.profile.profile_home

    @property
    def workspace(self) -> Path: return self.profile.workspace

    @property
    def auth_directory(self) -> Path: return self.profile.auth_directory

    @property
    def executable(self) -> Path: return self.profile.executable

    @property
    def config_digest(self) -> str: return self.profile.config_digest

    def environment(self) -> dict[str, str]: return session_env("claude-cli", str(self.auth_directory), self.profile_home / "runtime")

    def as_result(self) -> dict[str, Any]:
        return {"schema": "flywheel.claude-managed-runtime/v1", "provider": "claude",
                "admitted": False, "workspace_ref": str(self.workspace),
                "config_digest": self.config_digest, "limitations": list(self.limitations)}

    def start_client(self, *, model: str, launcher=None,
                     initialize_timeout: float = 5.0) -> ClaudeSessionClient:
        if not _valid_model(model):
            raise ProviderSessionError("MODEL_SELECTION_REQUIRED")
        with _custody_lock:
            if _cleanup_holds:
                raise ProviderSessionError("AGENT_NATIVE_CLEANUP_REQUIRED")
        stack = ExitStack()
        try:
            before_resume = stack.enter_context(lease_claude_profile(self.profile))

            def launch(argv, cwd, env):
                if launcher is not None:
                    return launcher(argv, cwd, env)
                return start_provider_session_process(
                    argv, cwd=Path(cwd), env=env, before_resume=before_resume)

            client = ClaudeSessionClient.start(
                self._launch_config(model), launcher=launch,
                env=self.environment(), initialize_timeout=initialize_timeout)
            client._runtime_release = stack.close
            return client
        except ClaudeSessionCleanupError as exc:
            _hold_cleanup(stack, exc.process)
            raise ProviderSessionError("AGENT_NATIVE_CLEANUP_REQUIRED") from None
        except ProviderSessionProcessError as exc:
            process = getattr(exc, "owned_process", None)
            if process is not None:
                if ClaudeSessionClient._close_process_object(process, initialize_timeout):
                    stack.close()
                    raise ProviderSessionError("AGENT_NATIVE_RUNTIME_DISABLED") from None
                _hold_cleanup(stack, process)
                raise ProviderSessionError("AGENT_NATIVE_CLEANUP_REQUIRED") from None
            stack.close()
            raise ProviderSessionError("AGENT_NATIVE_RUNTIME_DISABLED") from None
        except ProviderSessionError:
            stack.close()
            raise
        except Exception:
            stack.close()
            raise ProviderSessionError("AGENT_NATIVE_RUNTIME_DISABLED") from None

    def _launch_config(self, model: str) -> ClaudeSessionLaunchConfig:
        return ClaudeSessionLaunchConfig(
            executable=str(self.executable),
            working_directory=str(self.workspace),
            model=model,
            permission_mode=self.policy.permission_mode,
            permission_prompt_tool_name=self.policy.permission_prompt_tool_name,
            safe_mode=self.policy.safe_mode,
            restricted=self.policy.restricted,
            setting_sources=tuple(self.policy.setting_sources),
            tools=tuple(self.policy.tools),
            replay_user_messages=False,
            strict_mcp_config=self.policy.strict_mcp_config,
            mcp_config=_plain_json(self.policy.mcp_config),
            settings=_plain_json(self.policy.settings),
            allowed_tools=tuple(self.policy.allowed_tools),
            disallowed_tools=tuple(self.policy.disallowed_tools),
            no_chrome=True,
            disable_slash_commands=True,
        )


def prepare_claude_runtime(
        *, state_root: Path, workspace: Path, owner_ref: str,
        executable: Path, executable_sha256: str, auth_directory: Path,
        policy: ClaudeManagedSessionPolicy | None = None) -> ClaudeRuntimeAdmission:
    policy = _validated_policy(policy or ClaudeManagedSessionPolicy())
    profile = prepare_claude_profile(
        state_root=state_root,
        workspace=workspace,
        owner_ref=owner_ref,
        executable=executable,
        executable_sha256=executable_sha256,
        auth_directory=auth_directory,
        policy_payload=_policy_json(policy),
        settings=_plain_json(policy.settings),
        mcp_config=_plain_json(policy.mcp_config),
        limitations=_LIMITATIONS,
    )
    return ClaudeRuntimeAdmission(profile=profile, policy=policy)


def _validated_policy(policy: ClaudeManagedSessionPolicy) -> ClaudeManagedSessionPolicy:
    if not isinstance(policy, ClaudeManagedSessionPolicy):
        raise ProviderSessionError("AGENT_NATIVE_RUNTIME_DISABLED")
    mcp_config = _sealed_json_mapping(policy.mcp_config)
    settings = _sealed_json_mapping(policy.settings)
    setting_sources = _source_tuple(policy.setting_sources)
    tools = _tool_tuple(policy.tools, "tools")
    allowed_tools = _tool_tuple(policy.allowed_tools, "allowed_tools")
    disallowed_tools = _tool_tuple(policy.disallowed_tools, "disallowed_tools")
    if (policy.permission_mode != "manual" or policy.permission_prompt_tool_name != "stdio"
            or policy.safe_mode is not True or policy.restricted is not True
            or policy.strict_mcp_config is not True):
        raise ProviderSessionError("AGENT_NATIVE_RUNTIME_DISABLED")
    if _plain_json(mcp_config) != _DEFAULT_MCP_CONFIG or _plain_json(settings) != _DEFAULT_SETTINGS:
        raise ProviderSessionError("AGENT_NATIVE_RUNTIME_DISABLED")
    if setting_sources != () or tools != () or allowed_tools != () or "mcp__*" not in disallowed_tools:
        raise ProviderSessionError("AGENT_NATIVE_RUNTIME_DISABLED")
    return ClaudeManagedSessionPolicy(
        permission_mode=policy.permission_mode,
        permission_prompt_tool_name=policy.permission_prompt_tool_name,
        safe_mode=True,
        restricted=True,
        setting_sources=setting_sources,
        tools=tools,
        strict_mcp_config=True,
        mcp_config=mcp_config,
        settings=settings,
        allowed_tools=allowed_tools,
        disallowed_tools=disallowed_tools,
    )


def retry_managed_claude_cleanup() -> bool:
    with _custody_lock:
        held = list(_cleanup_holds)
    for item in held:
        item.close()
    with _custody_lock:
        return not _cleanup_holds


class _HeldClaudeRuntime:
    def __init__(self, stack: ExitStack, process):
        self.stack = stack
        self.process = process
        self.closed = False

    def close(self) -> bool:
        if self.closed:
            return True
        if self.process is not None and not ClaudeSessionClient._close_process_object(
                self.process, 2.0):
            return False
        self.stack.close()
        self.closed = True
        with _custody_lock:
            if self in _cleanup_holds:
                _cleanup_holds.remove(self)
        return True


def _hold_cleanup(stack: ExitStack, process) -> None:
    with _custody_lock:
        _cleanup_holds.append(_HeldClaudeRuntime(stack, process))


def _sealed_json_mapping(value: Mapping[str, Any]):
    if not isinstance(value, Mapping):
        raise ProviderSessionError("AGENT_NATIVE_RUNTIME_DISABLED")
    try:
        normalized = json.loads(json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False))
    except (TypeError, ValueError):
        raise ProviderSessionError("AGENT_NATIVE_RUNTIME_DISABLED") from None
    if type(normalized) is not dict:
        raise ProviderSessionError("AGENT_NATIVE_RUNTIME_DISABLED")
    return _freeze_json(normalized)


def _freeze_json(value):
    if type(value) is dict:
        return MappingProxyType({str(k): _freeze_json(v) for k, v in value.items()})
    if type(value) is list:
        return tuple(_freeze_json(v) for v in value)
    return value


def _plain_json(value):
    if isinstance(value, Mapping):
        return {str(k): _plain_json(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_plain_json(v) for v in value]
    if isinstance(value, list):
        return [_plain_json(v) for v in value]
    return value


def _tool_tuple(value, name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (tuple, list)):
        raise ProviderSessionError("AGENT_NATIVE_RUNTIME_DISABLED")
    items = tuple(value)
    if any(type(item) is not str or not item or any(ord(c) < 32 for c in item)
           for item in items):
        raise ProviderSessionError("AGENT_NATIVE_RUNTIME_DISABLED")
    return items


def _source_tuple(value) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (tuple, list)):
        raise ProviderSessionError("AGENT_NATIVE_RUNTIME_DISABLED")
    items = tuple(value)
    if any(item not in ("user", "project", "local") for item in items):
        raise ProviderSessionError("AGENT_NATIVE_RUNTIME_DISABLED")
    return items


def _policy_json(policy: ClaudeManagedSessionPolicy) -> dict[str, Any]:
    return {
        "permission_mode": policy.permission_mode,
        "permission_prompt_tool_name": policy.permission_prompt_tool_name,
        "safe_mode": policy.safe_mode,
        "restricted": policy.restricted,
        "setting_sources": list(policy.setting_sources),
        "tools": list(policy.tools),
        "strict_mcp_config": policy.strict_mcp_config,
        "mcp_config": _plain_json(policy.mcp_config),
        "settings": _plain_json(policy.settings),
        "allowed_tools": list(policy.allowed_tools),
        "disallowed_tools": list(policy.disallowed_tools),
    }


def _valid_model(model: str) -> bool:
    return type(model) is str and 0 < len(model) <= 256 and re.search(r"\s|[\x00-\x1f\x7f]", model) is None
