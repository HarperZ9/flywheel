"""ollama.py -- local open-weight models: raw reasoning plus token logprobs.

A local thinking model's reasoning text is its ordinary output, so the channel
is raw (A1r). Ollama returns the reasoning in a separate `thinking` field on
/api/generate and in message.thinking on /api/chat; in raw prompt mode a model
may also write it inline between <think> tags in `response`, which this adapter
splits. When `logprobs` came back the record also carries A3 (log
probabilities over the generated tokens). Shapes verified against recorded
qwen3:8b responses from the round-1 pilot (Ollama 0.35.0).
"""
from __future__ import annotations

from ..channel import A3, NONE, RAW, ReasoningRecord
from ._common import Capture, truncation_gap

PROVIDER = "ollama"
FIELD_MAP = {
    "thinking | message.thinking": ("recorded qwen3:8b, Ollama 0.35.0", "high"),
    "response | message.content": ("recorded qwen3:8b, Ollama 0.35.0", "high"),
    "logprobs[].token, logprobs[].logprob, top_logprobs": ("recorded qwen3:8b, Ollama 0.35.0", "high"),
    "done_reason": ("recorded qwen3:8b, Ollama 0.35.0", "high"),
    "message.tool_calls": ("Ollama API docs, not re-read here", "moderate"),
}


def split_inline(text: str) -> tuple:
    """(thinking, answer, closed) from text that may hold an inline think span."""
    if "<think>" not in text and "</think>" not in text:
        return "", text, True
    head, sep, tail = text.partition("</think>")
    thinking = head.split("<think>", 1)[-1]
    return thinking.strip("\n"), tail.strip(), bool(sep)


def capture(request: dict, response: dict, *, run_id: str, turn_index: int = 0) -> Capture:
    request = request or {}
    msg = response.get("message") or {}
    thinking = response.get("thinking") or msg.get("thinking") or ""
    answer = response.get("response") if "response" in response else msg.get("content", "")
    answer = answer or ""
    closed = True
    if not thinking:
        thinking, answer, closed = split_inline(answer)
    logprobs = response.get("logprobs") or None
    stopped_long = response.get("done_reason") == "length"
    opts = request.get("options") or {}
    rec = ReasoningRecord(
        run_id=run_id, turn_index=turn_index, provider=PROVIDER,
        endpoint="chat" if "message" in response else "generate",
        requested_model=str(request.get("model", "")), served_model=str(response.get("model", "")),
        channel=RAW if thinking else NONE, display_mode="raw" if request.get("raw") else "template",
        summarizer="none" if thinking else "not_applicable", reasoning_text=thinking or None,
        reasoning_tokens_reported="unknown",
        truncated=stopped_long and (not answer.strip() or not closed),
        logprobs=logprobs, answer=answer or None,
        tool_calls=list(msg.get("tool_calls") or []),
        sampling={k: opts.get(k, "unset") for k in ("temperature", "top_k", "top_p", "seed",
                                                    "num_predict")},
        extra_classes=(A3,) if logprobs else ())
    return Capture(rec, [truncation_gap(PROVIDER)] if rec.truncated else [], FIELD_MAP)
