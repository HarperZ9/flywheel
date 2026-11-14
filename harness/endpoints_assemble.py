"""endpoints_assemble.py -- rebuild a provider's response from its stream.

A streamed reply arrives as many small events. Each assembler here takes them
one at a time, hands back the text an event adds (so it can be shown at once),
and at the end returns the response object the provider would have sent for
the same reply without streaming. That object goes to the same reader a plain
reply goes to (endpoints_reply), so both record the same thing.

An assembler also knows whether the stream finished. `complete()` is true only
after the provider's own end marker: Anthropic's `message_stop` with every
content block closed, an OpenAI chunk with a `finish_reason`, a Gemini chunk
with a `finishReason`. A stream that stops earlier has no reply, whatever text
it carried, and a tool call it was in the middle of never runs.

Wire formats, read 2026-11-13:
  Anthropic  https://platform.claude.com/docs/en/build-with-claude/streaming
  OpenAI     https://github.com/openai/openai-openapi (manual_spec branch,
             CreateChatCompletionStreamResponse and its delta schemas)
  Gemini     https://aistudio.google.com/api-reference/generate-content
             (models.streamGenerateContent, GenerateContentResponse)
"""
from __future__ import annotations

import json

from .endpoints_sse import DONE


class Assembler:
    """Shared state: whether anything arrived, and an error the provider sent."""

    def __init__(self):
        self.began, self.error = False, None

    def feed(self, event: str, data) -> str:
        raise NotImplementedError

    def complete(self) -> bool:
        raise NotImplementedError

    def response(self) -> dict:
        raise NotImplementedError


class AnthropicAssembler(Assembler):
    """Messages API events -> the Message object. Unknown events are ignored,
    as the provider's versioning policy asks."""

    _KINDS = ("message_start", "content_block_start", "content_block_delta",
              "content_block_stop", "message_delta", "message_stop")

    def __init__(self):
        super().__init__()
        self.message, self.blocks, self.open = None, {}, set()
        self.partial, self.stopped = {}, False

    def feed(self, event: str, data) -> str:
        kind = data.get("type") or event
        if kind == "error":
            self.error = data
            return ""
        if kind not in self._KINDS:
            return ""
        return getattr(self, "_" + kind)(data) or ""

    def _message_start(self, data):
        self.began, self.message = True, dict(data["message"])

    def _content_block_start(self, data):
        index, block = data["index"], dict(data["content_block"])
        self.blocks[index] = block
        self.open.add(index)
        if block.get("type") == "tool_use":
            self.partial[index] = ""

    def _content_block_delta(self, data):
        index, delta = data["index"], data["delta"]
        block, kind = self.blocks[index], delta.get("type")
        if kind == "text_delta":
            block["text"] = block.get("text", "") + delta["text"]
            return delta["text"]
        if kind == "input_json_delta":
            self.partial[index] += delta["partial_json"]
        elif kind == "thinking_delta":
            block["thinking"] = block.get("thinking", "") + delta["thinking"]
        elif kind == "signature_delta":
            block["signature"] = delta["signature"]

    def _content_block_stop(self, data):
        index = data["index"]
        if index in self.partial:           # a tool call's arguments, now whole
            raw = self.partial.pop(index)
            parsed = json.loads(raw) if raw.strip() else {}
            if not isinstance(parsed, dict):
                raise ValueError("tool input is not a JSON object")
            self.blocks[index]["input"] = parsed
        self.open.discard(index)

    def _message_delta(self, data):
        self.message.update(data.get("delta") or {})
        usage = data.get("usage")
        if isinstance(usage, dict):         # cumulative counts replace the first ones
            self.message["usage"] = {**(self.message.get("usage") or {}), **usage}

    def _message_stop(self, data):
        self.stopped = True

    def complete(self) -> bool:
        return self.stopped and self.message is not None and not self.open

    def response(self) -> dict:
        return {**self.message, "content": [self.blocks[i] for i in sorted(self.blocks)]}


class OpenAIAssembler(Assembler):
    """chat.completion.chunk objects -> a chat.completion object."""

    _HEAD = ("id", "created", "model", "system_fingerprint", "service_tier")
    _EXTRA = ("reasoning_content", "reasoning", "refusal")

    def __init__(self):
        super().__init__()
        self.head, self.text, self.calls, self.extra = {}, [], {}, {}
        self.finish, self.usage = None, None

    def feed(self, event: str, data) -> str:
        if data == DONE:
            return ""
        if "error" in data and not data.get("choices"):
            self.error = data
            return ""
        self.began = True
        for key in self._HEAD:
            if key in data and key not in self.head:
                self.head[key] = data[key]
        if isinstance(data.get("usage"), dict):
            self.usage = data["usage"]
        piece = ""
        for choice in data.get("choices") or []:
            if choice.get("index", 0) == 0:
                piece += self._choice(choice)
        return piece

    def _choice(self, choice: dict) -> str:
        delta = choice.get("delta") or {}
        for call in delta.get("tool_calls") or []:
            slot = self.calls.setdefault(call["index"], {
                "id": "", "type": "function", "function": {"name": "", "arguments": ""}})
            slot["id"] = call.get("id") or slot["id"]
            function = call.get("function") or {}
            slot["function"]["name"] += function.get("name") or ""
            slot["function"]["arguments"] += function.get("arguments") or ""
        for key in self._EXTRA:
            if isinstance(delta.get(key), str):
                self.extra[key] = self.extra.get(key, "") + delta[key]
        if choice.get("finish_reason"):
            self.finish = choice["finish_reason"]
        content = delta.get("content")
        if isinstance(content, str) and content:
            self.text.append(content)
            return content
        return ""

    def complete(self) -> bool:
        return self.finish is not None

    def response(self) -> dict:
        message = {"role": "assistant", "content": "".join(self.text) or None, **self.extra}
        if self.calls:
            message["tool_calls"] = [self.calls[i] for i in sorted(self.calls)]
        out = {**self.head, "object": "chat.completion",
               "choices": [{"index": 0, "message": message, "finish_reason": self.finish}]}
        if self.usage is not None:
            out["usage"] = self.usage
        return out


class GeminiAssembler(Assembler):
    """GenerateContentResponse chunks -> one GenerateContentResponse.

    A prompt the provider blocked ends the stream with `promptFeedback` and no
    candidate. That is a finished stream with no reply, and the reader turns
    it into the same error a plain call gives.
    """

    _LAST = ("usageMetadata", "modelVersion", "responseId", "promptFeedback")

    def __init__(self):
        super().__init__()
        self.parts, self.finish, self.last, self.blocked = [], None, {}, False

    def feed(self, event: str, data) -> str:
        if "error" in data and not data.get("candidates"):
            self.error = data
            return ""
        self.began = True
        for key in self._LAST:
            if key in data:
                self.last[key] = data[key]
        feedback = data.get("promptFeedback")
        self.blocked = self.blocked or bool(
            isinstance(feedback, dict) and feedback.get("blockReason"))
        piece = ""
        for candidate in (data.get("candidates") or [])[:1]:
            for part in (candidate.get("content") or {}).get("parts") or []:
                self.parts.append(part)
                if isinstance(part.get("text"), str) and part.get("thought") is not True:
                    piece += part["text"]
            if candidate.get("finishReason"):
                self.finish = candidate["finishReason"]
        return piece

    def complete(self) -> bool:
        return self.finish is not None or (self.blocked and not self.parts)

    def response(self) -> dict:
        if self.finish is None:
            return dict(self.last)
        candidate = {"content": {"role": "model", "parts": self.parts},
                     "finishReason": self.finish, "index": 0}
        return {"candidates": [candidate], **self.last}
