"""token_usage.py -- the token counts a provider reported, in one shape.

Each hosted API reports usage under its own names. These readers turn a raw
response into {"input_tokens", "output_tokens"} when, and only when, the
provider sent both as non-negative integers. Anything else is None: a missing
count stays missing rather than becoming an estimate that looks measured.
"""
from __future__ import annotations


def _pair(inp, out) -> "dict | None":
    if type(inp) is int and type(out) is int and inp >= 0 and out >= 0:
        return {"input_tokens": inp, "output_tokens": out}
    return None


def _get(obj, *keys):
    for key in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def from_openai(obj) -> "dict | None":
    """OpenAI-compatible chat completions: usage.prompt_tokens / completion_tokens."""
    return _pair(_get(obj, "usage", "prompt_tokens"), _get(obj, "usage", "completion_tokens"))


def from_anthropic(obj) -> "dict | None":
    """Anthropic messages: usage.input_tokens / output_tokens."""
    return _pair(_get(obj, "usage", "input_tokens"), _get(obj, "usage", "output_tokens"))


def from_gemini(obj) -> "dict | None":
    """Gemini generateContent: usageMetadata.promptTokenCount / candidatesTokenCount."""
    return _pair(_get(obj, "usageMetadata", "promptTokenCount"),
                 _get(obj, "usageMetadata", "candidatesTokenCount"))


def from_ollama(native) -> "dict | None":
    """Ollama native fields as kept by local_usage: prompt_eval_count / eval_count."""
    return _pair(_get(native, "prompt_eval_count"), _get(native, "eval_count"))


def field(usage: "dict | None") -> dict:
    """{"token_usage": usage} to merge into a generation, or {} when uncounted."""
    return {"token_usage": usage} if usage is not None else {}


def response_field(gen: dict) -> dict:
    """{"x_token_usage": ...} for a response built from `gen`, or {}."""
    counted = gen.get("token_usage") or from_ollama(gen.get("usage"))
    return {"x_token_usage": counted} if counted is not None else {}
