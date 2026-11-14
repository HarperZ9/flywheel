"""Replay helpers for the recorded provider streams in fixtures/provider_streams.

Each provider folder holds pairs: NAME.sse is a reply as the provider streams
it, and NAME.json is the same reply as the provider sends it without
streaming. The pairs were written by hand in each provider's documented wire
format; no provider was called to make them and none is called to replay them.

Wire formats, read 2026-11-13:
  Anthropic  https://platform.claude.com/docs/en/build-with-claude/streaming
             (event flow, delta types, the two full stream examples)
  OpenAI     https://github.com/openai/openai-openapi, branch manual_spec,
             openapi.yaml: CreateChatCompletionStreamResponse,
             ChatCompletionStreamResponseDelta,
             ChatCompletionMessageToolCallChunk, ChatCompletionStreamOptions
             (platform.openai.com refused the fetch, so the published spec
             was read instead)
  Gemini     https://aistudio.google.com/api-reference/generate-content
             (models.streamGenerateContent, GenerateContentResponse) and
             https://github.com/google-gemini/cookbook
             quickstarts/rest/Streaming_REST.ipynb (the alt=sse form)
"""
import json
from pathlib import Path

from harness.endpoints import AnthropicBackend, GeminiBackend, OpenAICompatBackend

ROOT = Path(__file__).parent / "fixtures" / "provider_streams"
PROVIDERS = ("openai", "anthropic", "gemini")
NATIVE = {"openai": "tool_call", "anthropic": "tool_use", "gemini": "function_call"}
TURNS = ("turn1", "turn2")
_MAKE = {
    "openai": lambda: OpenAICompatBackend(name="openai", base_url="http://provider.invalid/v1",
                                          model="gpt-5.3-codex-spark", api_key="test-key"),
    "anthropic": lambda: AnthropicBackend(name="anthropic", base_url="http://provider.invalid",
                                          model="claude-sonnet-5", api_key="test-key"),
    "gemini": lambda: GeminiBackend(name="gemini", base_url="http://provider.invalid/v1beta",
                                    model="gemini-2.5-flash", api_key="test-key"),
}


def stream_bytes(provider: str, name: str) -> bytes:
    return (ROOT / provider / f"{name}.sse").read_bytes()


def plain_object(provider: str, name: str) -> dict:
    return json.loads((ROOT / provider / f"{name}.json").read_text(encoding="utf-8"))


class Replay:
    """A stream transport that answers each request with the next recording."""

    def __init__(self, bodies):
        self.bodies, self.requests = list(bodies), []

    def __call__(self, method, url, headers, body, timeout):
        self.requests.append({"url": url, "headers": dict(headers), "body": json.loads(body)})
        answer = self.bodies.pop(0)
        if isinstance(answer, tuple):               # (status, error object)
            return answer
        return 200, answer.splitlines(keepends=True)


class Plain:
    """A plain transport that answers each request with the next object."""

    def __init__(self, objects):
        self.objects, self.requests = list(objects), []

    def __call__(self, method, url, headers, body, timeout):
        self.requests.append({"url": url, "headers": dict(headers), "body": json.loads(body)})
        answer = self.objects.pop(0)
        return answer if isinstance(answer, tuple) else (200, answer)


def backend(provider: str, *, streams=(), plain=()):
    """A hosted backend whose two transports replay the given recordings."""
    made = _MAKE[provider]()
    made.stream_transport = Replay(streams)
    made.transport = Plain(plain)
    return made


def drain(generator) -> tuple:
    """(pieces, returned value) of a `chat_streamed` generator."""
    pieces = []
    while True:
        try:
            pieces.append(next(generator))
        except StopIteration as done:
            return pieces, done.value


CALL = {"system": "be brief", "max_tokens": 64, "temperature": 0.0, "seed": 7}
MESSAGES = [{"role": "user", "content": "write a note"}]
