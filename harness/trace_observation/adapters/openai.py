"""openai.py -- Responses and Chat Completions shapes; also serves xAI's Responses API.

Documented (OAI-REASONING, read 2026-10-01): reasoning tokens are not visible
through the API; summaries come back on reasoning items when the request sets
reasoning.summary; reasoning items may carry encrypted_content for passing back
to the API. The reasoning-token path (output_tokens_details.reasoning_tokens on
Responses, completion_tokens_details.reasoning_tokens on Chat Completions)
rests on Microsoft's Azure page (AZ-OAI-REASONING), a reseller source, so its
confidence is moderate. xAI (XAI-REASONING, XAI-API-REF) documents summaries
on grok-4.7 and reasoning.encrypted_content on every Responses API response.
encrypted_content is digested, never read.
"""
from __future__ import annotations

from ..channel import NONE, SUMMARY_UNKNOWN, ReasoningRecord, count_str
from ._common import (UNVERIFIED, Capture, find_count, joined, omitted_gap, opaque_gap, opaque_ref,
                      truncation_gap)

FIELD_MAP = {
    "output[type=reasoning].summary[].text": ("OAI-REASONING", "high"),
    "output[type=reasoning].encrypted_content": ("OAI-REASONING", "high"),
    "usage.*.reasoning_tokens": ("AZ-OAI-REASONING (reseller)", "moderate"),
    "output[type=function_call]": ("AZ-OAI-REASONING (reseller)", "moderate"),
    "output[type=message].content[].text": (UNVERIFIED, "moderate"),
    "status/incomplete_details.reason": (UNVERIFIED, "low"),
    "choices[0].message (chat completions)": (UNVERIFIED, "moderate"),
}


def _responses(response: dict):
    texts, answers, tools, opaque = [], [], [], []
    for item in response.get("output") or []:
        kind = item.get("type")
        if kind == "reasoning":
            for part in item.get("summary") or []:
                texts.append(part.get("text"))
            if item.get("encrypted_content"):
                opaque.append(opaque_ref("encrypted_content", item["encrypted_content"]))
        elif kind == "message":
            for part in item.get("content") or []:
                answers.append(part.get("text"))
        elif kind == "function_call":
            tools.append({"name": item.get("name", ""), "arguments": item.get("arguments", "")})
    reason = (response.get("incomplete_details") or {}).get("reason", "")
    return texts, answers, tools, opaque, reason == "max_output_tokens"


def _chat(response: dict):
    choice = (response.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    tools = [{"name": (t.get("function") or {}).get("name", ""),
              "arguments": (t.get("function") or {}).get("arguments", "")}
             for t in msg.get("tool_calls") or []]
    return [], [msg.get("content")], tools, [], choice.get("finish_reason") == "length"


def capture(request: dict, response: dict, *, run_id: str, turn_index: int = 0,
            provider: str = "openai") -> Capture:
    request = request or {}
    chat = "choices" in response
    texts, answers, tools, opaque, stopped_long = (_chat if chat else _responses)(response)
    text, answer = joined(texts), joined(answers)
    summary_setting = str((request.get("reasoning") or {}).get("summary", "unset"))
    rec = ReasoningRecord(
        run_id=run_id, turn_index=turn_index, provider=provider,
        endpoint="chat.completions" if chat else "responses",
        requested_model=str(request.get("model", "")), served_model=str(response.get("model", "")),
        channel=SUMMARY_UNKNOWN if text else NONE, display_mode=f"summary={summary_setting}",
        summarizer="unknown" if text else "not_applicable", reasoning_text=text or None,
        reasoning_tokens_reported=count_str(find_count(response.get("usage") or {},
                                                       "reasoning_tokens")),
        truncated=stopped_long and not answer and not tools, opaque_fields=opaque,
        answer=answer or None, tool_calls=tools,
        sampling={k: request.get(k, "unset") for k in ("temperature", "top_p", "max_output_tokens")})
    gaps = [opaque_gap("capture", ref["name"], provider) for ref in opaque]
    if not text and not chat:
        gaps.append(omitted_gap(provider, f"summary={summary_setting}"))
    if rec.truncated:
        gaps.append(truncation_gap(provider))
    return Capture(rec, gaps, FIELD_MAP)


def capture_xai(request: dict, response: dict, *, run_id: str, turn_index: int = 0) -> Capture:
    cap = capture(request, response, run_id=run_id, turn_index=turn_index, provider="xai")
    cap.field_map = {"output[type=reasoning].summary[].text": ("XAI-REASONING", "moderate"),
                     "reasoning.encrypted_content": ("XAI-REASONING", "moderate"),
                     "usage.*.reasoning_tokens": ("XAI-REASONING", "moderate"),
                     "output[type=message].content[].text": (UNVERIFIED, "low")}
    return cap
