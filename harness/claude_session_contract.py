"""Typed Claude session contracts for the native-session transport slice.

The objects here model documented Claude Agent SDK/Claude Code stream-json
shapes. They do not grant authority or persist sessions.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from typing import Any

_ALLOWED_IMAGE_MEDIA_TYPES = frozenset({
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/webp",
})
_ALLOWED_PERMISSION_MODES = frozenset({
    "acceptEdits",
    "auto",
    "dontAsk",
    "manual",
    "plan",
})
_ALLOWED_SETTING_SOURCES = frozenset({"user", "project", "local"})


class ClaudeSessionContractError(ValueError):
    """Raised when a caller asks for an unsupported Claude session shape."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ClaudeSessionLaunchConfig:
    executable: str
    working_directory: str = ""
    model: str = ""
    permission_mode: str = "manual"
    permission_prompt_tool_name: str = "stdio"
    session_id: str = ""
    resume_session_id: str = ""
    fork_session: bool = False
    persist_session: bool = True
    replay_user_messages: bool = True
    strict_mcp_config: bool = False
    mcp_config: Mapping[str, Any] | None = None
    settings: Mapping[str, Any] | None = None
    allowed_tools: tuple[str, ...] = ()
    disallowed_tools: tuple[str, ...] = ()
    no_chrome: bool = False
    disable_slash_commands: bool = False
    safe_mode: bool = False
    restricted: bool = False
    setting_sources: tuple[str, ...] | None = None
    tools: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ClaudeSessionEvent:
    sequence: int
    kind: str
    raw: dict[str, Any]
    session_id: str = ""


@dataclass(frozen=True)
class ClaudeSessionProtocolEvent:
    sequence: int
    kind: str
    detail: str = ""


@dataclass(frozen=True)
class ClaudeControlRequest:
    request_id: str
    subtype: str
    request: Mapping[str, Any]
    raw: Mapping[str, Any]
    token: str = ""


@dataclass(frozen=True)
class ClaudePermissionDecision:
    behavior: str
    updated_input: dict[str, Any] | None = None
    message: str = ""

    @classmethod
    def allow(cls, updated_input: dict[str, Any]) -> "ClaudePermissionDecision":
        if not isinstance(updated_input, dict):
            raise ClaudeSessionContractError(
                "invalid_permission_input", "allow requires an input object")
        return cls("allow", dict(updated_input), "")

    @classmethod
    def deny(cls, message: str) -> "ClaudePermissionDecision":
        if not isinstance(message, str) or not message:
            raise ClaudeSessionContractError(
                "invalid_permission_message", "deny requires a message")
        return cls("deny", None, message)

    def to_typescript_callback_result(self) -> dict[str, Any]:
        if self.behavior == "allow":
            return {"behavior": "allow", "updatedInput": self.updated_input}
        if self.behavior == "deny":
            return {"behavior": "deny", "message": self.message}
        raise ClaudeSessionContractError(
            "invalid_permission_behavior", "permission behavior is unsupported")


def validate_launch_config(config: ClaudeSessionLaunchConfig) -> None:
    if not isinstance(config.executable, str) or not config.executable:
        raise ClaudeSessionContractError(
            "missing_executable", "Claude executable is required")
    if config.permission_mode not in _ALLOWED_PERMISSION_MODES:
        if config.permission_mode == "bypassPermissions":
            raise ClaudeSessionContractError(
                "permission_bypass_refused",
                "bypassPermissions is not allowed for managed sessions",
            )
        raise ClaudeSessionContractError(
            "unsupported_permission_mode", "permission mode is unsupported")
    if config.permission_prompt_tool_name != "stdio":
        raise ClaudeSessionContractError(
            "unsupported_permission_prompt_tool",
            "managed Claude sessions require SDK stdio permission custody",
        )
    if config.fork_session and not config.resume_session_id:
        raise ClaudeSessionContractError(
            "fork_requires_resume", "forking requires a resume session id")
    if config.resume_session_id and not config.persist_session:
        raise ClaudeSessionContractError(
            "resume_requires_persistence", "resume requires session persistence")
    _validate_json_mapping("mcp_config", config.mcp_config)
    _validate_json_mapping("settings", config.settings)
    _validate_tool_names("allowed_tools", config.allowed_tools, none_allowed=False)
    _validate_tool_names("disallowed_tools", config.disallowed_tools, none_allowed=False)
    _validate_tool_names("tools", config.tools, none_allowed=True)
    _validate_setting_sources(config.setting_sources)


def build_claude_session_argv(config: ClaudeSessionLaunchConfig) -> list[str]:
    validate_launch_config(config)
    argv = [config.executable, "--print", "--output-format", "stream-json",
            "--verbose", "--input-format", "stream-json",
            f"--permission-mode={config.permission_mode}",
            "--permission-prompt-tool", config.permission_prompt_tool_name]
    if config.model:
        argv.append(f"--model={config.model}")
    if config.safe_mode:
        argv.append("--safe-mode")
    if config.restricted:
        argv.append("--restricted")
    if config.setting_sources is not None:
        argv.append("--setting-sources=" + ",".join(config.setting_sources))
    if config.tools is not None:
        argv.append("--tools=" + ",".join(config.tools))
    if config.session_id:
        argv.append(f"--session-id={config.session_id}")
    if config.resume_session_id:
        argv.append(f"--resume={config.resume_session_id}")
    if config.fork_session:
        argv.append("--fork-session")
    if config.strict_mcp_config:
        argv.append("--strict-mcp-config")
    if config.mcp_config is not None:
        argv.extend(["--mcp-config", _compact_json(config.mcp_config)])
    if config.allowed_tools:
        argv.extend(["--allowedTools", ",".join(config.allowed_tools)])
    if config.disallowed_tools:
        argv.extend(["--disallowedTools", ",".join(config.disallowed_tools)])
    if config.settings is not None:
        argv.extend(["--settings", _compact_json(config.settings)])
    if config.no_chrome:
        argv.append("--no-chrome")
    if config.disable_slash_commands:
        argv.append("--disable-slash-commands")
    if not config.persist_session:
        argv.append("--no-session-persistence")
    if config.replay_user_messages:
        argv.append("--replay-user-messages")
    return argv


def _validate_json_mapping(name: str, value: Mapping[str, Any] | None) -> None:
    if value is None:
        return
    if not isinstance(value, Mapping):
        raise ClaudeSessionContractError(
            f"invalid_{name}", f"{name} must be a JSON object")
    _compact_json(value)


def _compact_json(value: Mapping[str, Any]) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ClaudeSessionContractError(
            "invalid_json_policy", "launch policy must be finite JSON") from exc


def _validate_tool_names(name: str, values: tuple[str, ...] | None, *,
                         none_allowed: bool) -> None:
    if values is None and none_allowed:
        return
    if type(values) is not tuple:
        raise ClaudeSessionContractError(f"invalid_{name}", f"{name} must be a tuple")
    if any(type(item) is not str or not item or any(ord(c) < 32 for c in item)
           for item in values):
        raise ClaudeSessionContractError(f"invalid_{name}", f"{name} contains invalid tool names")


def _validate_setting_sources(values: tuple[str, ...] | None) -> None:
    if values is None:
        return
    if type(values) is not tuple or any(item not in _ALLOWED_SETTING_SOURCES for item in values):
        raise ClaudeSessionContractError(
            "invalid_setting_sources", "setting sources must be user, project or local")


def build_user_message(
        content: str | list[dict[str, Any]], *,
        parent_tool_use_id: str | None = None) -> dict[str, Any]:
    return {
        "type": "user",
        "message": {"role": "user", "content": _normalize_content(content)},
        "parent_tool_use_id": parent_tool_use_id,
    }


def _normalize_content(content: str | list[dict[str, Any]]):
    if isinstance(content, str):
        return content
    if not isinstance(content, list) or not content:
        raise ClaudeSessionContractError(
            "invalid_content", "content must be text or content blocks")
    return [_normalize_block(block) for block in content]


def _normalize_block(block: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(block, dict):
        raise ClaudeSessionContractError(
            "invalid_content_block", "content block must be an object")
    kind = block.get("type")
    if kind == "text":
        text = block.get("text")
        if not isinstance(text, str):
            raise ClaudeSessionContractError(
                "invalid_text_block", "text block requires text")
        return {"type": "text", "text": text}
    if kind == "image":
        source = block.get("source")
        if not isinstance(source, dict):
            raise ClaudeSessionContractError(
                "invalid_image_source", "image block requires source")
        if source.get("type") != "base64":
            raise ClaudeSessionContractError(
                "unsupported_image_source", "only base64 image sources are supported")
        media_type = source.get("media_type")
        data = source.get("data")
        if media_type not in _ALLOWED_IMAGE_MEDIA_TYPES:
            raise ClaudeSessionContractError(
                "unsupported_image_media_type", "image media type is unsupported")
        if not isinstance(data, str) or not data:
            raise ClaudeSessionContractError(
                "invalid_image_data", "base64 image data is required")
        return {"type": "image", "source": {
            "type": "base64", "media_type": media_type, "data": data}}
    raise ClaudeSessionContractError(
        "unsupported_content_block", "content block type is unsupported")


def session_id_from_event(raw: dict[str, Any]) -> str:
    value = raw.get("session_id")
    if isinstance(value, str):
        return value
    data = raw.get("data")
    if isinstance(data, dict) and isinstance(data.get("session_id"), str):
        return data["session_id"]
    return ""
