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


def from_record(usage) -> "dict | None":
    """The pair from what a backend kept as `usage`: the normalized counts of
    an observation record, an Ollama native block, a proposer's normalized
    {"prompt", "completion"} block, or a provider's own block."""
    counts = _get(usage, "counts")
    return (_pair(_get(counts, "input"), _get(counts, "output"))
            or from_ollama(usage)
            or _pair(_get(usage, "prompt"), _get(usage, "completion"))
            or _pair(_get(usage, "prompt_tokens"), _get(usage, "completion_tokens"))
            or _pair(_get(usage, "input_tokens"), _get(usage, "output_tokens")))


def field(usage: "dict | None") -> dict:
    """{"token_usage": usage} to merge into a generation, or {} when uncounted."""
    return {"token_usage": usage} if usage is not None else {}


def reported(gen) -> "dict | None":
    """The provider's pair for a generation, or None when it reported none."""
    return _get(gen, "token_usage") or from_record(_get(gen, "usage"))


def response_field(gen: dict) -> dict:
    """{"x_token_usage": ...} for a response built from `gen`, or {}."""
    counted = reported(gen)
    return {"x_token_usage": counted} if counted is not None else {}


# The `usage` field of a served response, from 2.0 on. It carries the
# provider's token counts or it is None. The word counts that 1.x put in
# `usage` live under ESTIMATE_FIELD, named as the estimate they are.
ESTIMATE_FIELD = "x_usage_estimate"
ESTIMATE_METHOD = "whitespace_words"


def estimate(prompt, completion) -> dict:
    """Whitespace word counts of the prompt and the reply. Words, never tokens."""
    return {"method": ESTIMATE_METHOD, "prompt_words": len(str(prompt).split()),
            "completion_words": len(str(completion).split())}


def openai_usage(pair) -> "dict | None":
    """An OpenAI-shaped usage object from a provider pair, or None."""
    counted = _pair(_get(pair, "input_tokens"), _get(pair, "output_tokens"))
    if counted is None:
        return None
    inp, out = counted["input_tokens"], counted["output_tokens"]
    return {"prompt_tokens": inp, "completion_tokens": out, "total_tokens": inp + out}


def anthropic_usage(pair) -> "dict | None":
    """An Anthropic-shaped usage object from a provider pair, or None."""
    return _pair(_get(pair, "input_tokens"), _get(pair, "output_tokens"))


def chat_usage(gen, prompt) -> dict:
    """The usage fields of an OpenAI-shaped chat completion built from `gen`:
    the provider's counts or None, the named estimate, and the flag."""
    counted = openai_usage(reported(gen))
    return {"usage": counted, ESTIMATE_FIELD: estimate(prompt, _get(gen, "text") or ""),
            "x_flywheel": {"usage_reported": counted is not None}}
