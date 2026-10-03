"""anthropic.py -- Messages API responses: summarized thinking, never raw.

Documented (access-gap source ANT-THINKING, read 2026-10-01): no display
setting returns the raw chain of thought; display "summarized" returns text a
different model wrote, and the thinking model does not see it; display
defaults to "omitted" on current models; each thinking block carries a
signature holding an encrypted copy of the full reasoning; redacted_thinking
blocks also exist. Thinking token count: usage.output_tokens_details.thinking_tokens
(ANT-EXT-THINKING). Signatures and redacted data are digested, never read.
"""
from __future__ import annotations

from ..channel import NONE, PROGRESS, SUMMARY_SEPARATE, ReasoningRecord, count_str
from ._common import Capture, joined, omitted_gap, opaque_gap, opaque_ref, truncation_gap

PROVIDER = "anthropic"
FIELD_MAP = {
    "content[].thinking": ("ANT-THINKING", "high"),
    "content[].signature": ("ANT-THINKING", "high"),
    "content[].redacted_thinking.data": ("ANT-THINKING", "high"),
    "usage.output_tokens_details.thinking_tokens": ("ANT-EXT-THINKING", "high"),
    "content[].tool_use": ("ANT-THINKING", "high"),
    "request.thinking.display": ("ANT-THINKING", "high"),
    "stop_reason": ("ANT-STOP-REASONS", "moderate"),
}


def capture(request: dict, response: dict, *, run_id: str, turn_index: int = 0) -> Capture:
    thinking_cfg = (request or {}).get("thinking") or {}
    display = str(thinking_cfg.get("display", "unset"))
    texts, answers, tools, opaque, gaps = [], [], [], [], []
    for block in response.get("content") or []:
        kind = block.get("type")
        if kind == "thinking":
            texts.append(block.get("thinking"))
            if block.get("signature"):
                opaque.append(opaque_ref("signature", block["signature"]))
        elif kind == "redacted_thinking":
            opaque.append(opaque_ref("redacted_thinking.data", block.get("data", "")))
        elif kind == "text":
            answers.append(block.get("text"))
        elif kind == "tool_use":
            tools.append({"name": block.get("name", ""), "input": block.get("input", {})})
    text = joined(texts)
    channel = PROGRESS if display == "updates" else SUMMARY_SEPARATE
    usage = response.get("usage") or {}
    tokens = ((usage.get("output_tokens_details") or {}).get("thinking_tokens"))
    stopped_long = response.get("stop_reason") == "max_tokens"
    rec = ReasoningRecord(
        run_id=run_id, turn_index=turn_index, provider=PROVIDER, endpoint="messages",
        requested_model=str((request or {}).get("model", "")),
        served_model=str(response.get("model", "")),
        channel=channel if text else NONE, display_mode=display,
        summarizer="separate_model" if text else "not_applicable",
        reasoning_text=text or None, reasoning_tokens_reported=count_str(tokens),
        truncated=stopped_long and not joined(answers) and not tools,
        opaque_fields=opaque, answer=joined(answers) or None, tool_calls=tools,
        sampling={"max_tokens": (request or {}).get("max_tokens", "unset")})
    for ref in opaque:
        gaps.append(opaque_gap("capture", ref["name"], PROVIDER))
    if not text and display in ("unset", "omitted"):
        gaps.append(omitted_gap(PROVIDER, display))
    if rec.truncated:
        gaps.append(truncation_gap(PROVIDER))
    return Capture(rec, gaps, FIELD_MAP)
