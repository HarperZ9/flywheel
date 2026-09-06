"""acp_turn.py -- what one delegated prompt turn amounted to.

An ACP agent reports its work as a stream of `session/update` notifications and
ends foreground work with an idle state carrying a stop reason. This module
folds that stream into one value the rest of Flywheel can hold: the text, the
thinking the agent chose to expose, the tool calls it made, and the reason it
stopped.

Two decisions worth naming. Every update is kept in order alongside the folded
view, because the fold is lossy and a receipt should be able to point at the
frame it summarized. And an update this module does not recognize is counted
rather than dropped, so a turn against a newer agent reports how much of itself
this reader could not account for instead of quietly reporting less work than
happened.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

END_TURN = "end_turn"
MAX_TOKENS = "max_tokens"
MAX_TURN_REQUESTS = "max_turn_requests"
REFUSAL = "refusal"
CANCELLED = "cancelled"
STOP_REASONS = (END_TURN, MAX_TOKENS, MAX_TURN_REQUESTS, REFUSAL, CANCELLED)

IDLE = "idle"

AGENT_MESSAGE = "agent_message"
AGENT_MESSAGE_CHUNK = "agent_message_chunk"
AGENT_THOUGHT = "agent_thought"
PLAN_UPDATE = "plan_update"
STATE_UPDATE = "state_update"
TOOL_CALL_UPDATE = "tool_call_update"
TOOL_CALL_CONTENT_CHUNK = "tool_call_content_chunk"
USAGE_UPDATE = "usage_update"
USER_MESSAGE = "user_message"


def text_of(content: Any) -> str:
    """The text a content block or list of blocks carries, and only the text."""
    if isinstance(content, list):
        return "".join(text_of(item) for item in content)
    if isinstance(content, dict):
        if content.get("type") == "text" and isinstance(content.get("text"), str):
            return content["text"]
        inner = content.get("content")
        if inner is not None:
            return text_of(inner)
    return ""


@dataclass(frozen=True)
class ToolCall:
    """One tool call as the agent last described it."""

    tool_call_id: str
    title: str = ""
    kind: str = ""
    status: str = ""
    text: str = ""


@dataclass
class Turn:
    """The result of one `session/prompt`.

    `stop_reason` is empty until the agent reports idle. A turn that ends with an
    empty stop reason ended some other way, and the caller is told which rather
    than being handed a default that reads like a clean finish.
    """

    session_id: str = ""
    stop_reason: str = ""
    text: str = ""
    thinking: str = ""
    tool_calls: dict[str, ToolCall] = field(default_factory=dict)
    plan: list = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    updates: list[dict] = field(default_factory=list)
    unrecognized: list[str] = field(default_factory=list)

    @property
    def refused(self) -> bool:
        """The agent declined to continue. A recorded outcome, not a failure."""
        return self.stop_reason == REFUSAL

    @property
    def complete(self) -> bool:
        return self.stop_reason == END_TURN

    def does_not_prove(self) -> list[str]:
        """What a reader must not conclude from this turn alone."""
        limits = [
            "the agent's own report of its work, not an independent observation",
            "tool calls are as the agent described them, not as executed",
        ]
        if self.unrecognized:
            kinds = ", ".join(sorted(set(self.unrecognized)))
            limits.append(f"updates this reader could not account for: {kinds}")
        if not self.stop_reason:
            limits.append("the turn never reported a stop reason")
        return limits


class TurnCollector:
    """Folds `session/update` payloads into one Turn."""

    def __init__(self, session_id: str = "") -> None:
        self.turn = Turn(session_id=session_id)

    def accept(self, params: dict) -> bool:
        """Take one update. Returns True when this update ended the turn."""
        update = params.get("update")
        if not isinstance(update, dict):
            self.turn.unrecognized.append("malformed")
            return False
        self.turn.updates.append(update)
        kind = update.get("sessionUpdate")
        handler = _HANDLERS.get(kind if isinstance(kind, str) else "")
        if handler is None:
            self.turn.unrecognized.append(str(kind))
            return False
        return bool(handler(self.turn, update))


def _message(turn: Turn, update: dict) -> bool:
    turn.text += text_of(update.get("content"))
    return False


def _thought(turn: Turn, update: dict) -> bool:
    turn.thinking += text_of(update.get("content"))
    return False


def _tool_call(turn: Turn, update: dict) -> bool:
    call_id = str(update.get("toolCallId", ""))
    if not call_id:
        return False
    previous = turn.tool_calls.get(call_id, ToolCall(call_id))
    turn.tool_calls[call_id] = ToolCall(
        call_id,
        title=str(update.get("title", previous.title)),
        kind=str(update.get("kind", previous.kind)),
        status=str(update.get("status", previous.status)),
        text=previous.text + text_of(update.get("content")))
    return False


def _plan(turn: Turn, update: dict) -> bool:
    entries = update.get("entries")
    if isinstance(entries, list):
        turn.plan = entries
    return False


def _usage(turn: Turn, update: dict) -> bool:
    turn.usage = {key: value for key, value in update.items()
                  if key != "sessionUpdate"}
    return False


def _state(turn: Turn, update: dict) -> bool:
    """Idle with a stop reason ends foreground work; any other state does not."""
    if update.get("state") != IDLE:
        return False
    reason = update.get("stopReason")
    if not isinstance(reason, str) or not reason:
        return False
    turn.stop_reason = reason
    return True


_HANDLERS = {
    AGENT_MESSAGE: _message,
    AGENT_MESSAGE_CHUNK: _message,
    USER_MESSAGE: lambda turn, update: False,
    AGENT_THOUGHT: _thought,
    TOOL_CALL_UPDATE: _tool_call,
    TOOL_CALL_CONTENT_CHUNK: _tool_call,
    PLAN_UPDATE: _plan,
    USAGE_UPDATE: _usage,
    STATE_UPDATE: _state,
}
