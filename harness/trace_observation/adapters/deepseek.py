"""deepseek.py -- Chat Completions with reasoning_content (documented raw).

Documented (DS-THINKING, read 2026-10-01, moderate): in thinking mode the
chain of thought comes back in reasoning_content; tool calls work in thinking
mode; logprobs cover output tokens in content and do not mention reasoning
tokens (DS-CHAT-REF, low). "Raw" is the provider's claim: which model served the
text is not checked here (the served-model probe does that), and a raw label
says nothing about faithfulness. Logprobs, where present, are recorded as
answer-token logprobs only, so they do not grant A3 over the reasoning span.
"""
from __future__ import annotations

from ..channel import NONE, RAW, ReasoningRecord, count_str
from ._common import UNVERIFIED, Capture, find_count, truncation_gap

PROVIDER = "deepseek"
FIELD_MAP = {
    "choices[0].message.reasoning_content": ("DS-THINKING", "moderate"),
    "choices[0].message.tool_calls": ("DS-THINKING", "moderate"),
    "choices[0].logprobs.content (answer tokens only)": ("DS-CHAT-REF", "low"),
    "usage.*.reasoning_tokens": (UNVERIFIED, "low"),
    "choices[0].finish_reason": (UNVERIFIED, "moderate"),
}


def capture(request: dict, response: dict, *, run_id: str, turn_index: int = 0) -> Capture:
    request = request or {}
    choice = (response.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    text = msg.get("reasoning_content") or ""
    answer = msg.get("content") or ""
    tools = [{"name": (t.get("function") or {}).get("name", ""),
              "arguments": (t.get("function") or {}).get("arguments", "")}
             for t in msg.get("tool_calls") or []]
    rec = ReasoningRecord(
        run_id=run_id, turn_index=turn_index, provider=PROVIDER, endpoint="chat.completions",
        requested_model=str(request.get("model", "")), served_model=str(response.get("model", "")),
        channel=RAW if text else NONE, display_mode="thinking_mode",
        summarizer="none_claimed" if text else "not_applicable", reasoning_text=text or None,
        reasoning_tokens_reported=count_str(find_count(response.get("usage") or {},
                                                       "reasoning_tokens")),
        truncated=choice.get("finish_reason") == "length" and not answer and not tools,
        answer=answer or None, tool_calls=tools,
        logprobs=((choice.get("logprobs") or {}).get("content")) or None,
        sampling={k: request.get(k, "unset") for k in ("temperature", "top_p", "max_tokens")})
    gaps = [truncation_gap(PROVIDER)] if rec.truncated else []
    return Capture(rec, gaps, FIELD_MAP)
