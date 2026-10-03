"""gemini.py -- generateContent responses with thought summaries.

Documented (GOO-THINKING, read 2026-10-01, moderate): thought summaries may be
empty depending on the thinking_summaries setting; a block may carry only a
signature with no summary; a thought signature is "an encrypted representation
of the model's internal reasoning state". The access-gap record did not read a
reasoning-token count, tool-call trace or logprob page for Google, so the paths
below for parts, thoughtsTokenCount and finishReason are adapter-unverified and
must be re-read from the raw page before a live run relies on them.
thoughtSignature is digested, never read.
"""
from __future__ import annotations

from ..channel import NONE, SUMMARY_UNKNOWN, ReasoningRecord, count_str
from ._common import (UNVERIFIED, Capture, joined, omitted_gap, opaque_gap, opaque_ref,
                      truncation_gap)

PROVIDER = "google"
FIELD_MAP = {
    "candidates[0].content.parts[thought=true].text": (UNVERIFIED, "low"),
    "parts[].thoughtSignature": ("GOO-THINKING", "moderate"),
    "usageMetadata.thoughtsTokenCount": (UNVERIFIED, "low"),
    "candidates[0].finishReason": (UNVERIFIED, "low"),
    "parts[].functionCall": (UNVERIFIED, "low"),
}


def capture(request: dict, response: dict, *, run_id: str, turn_index: int = 0) -> Capture:
    request = request or {}
    cand = (response.get("candidates") or [{}])[0]
    texts, answers, tools, opaque = [], [], [], []
    for part in (cand.get("content") or {}).get("parts") or []:
        if part.get("thoughtSignature"):
            opaque.append(opaque_ref("thoughtSignature", part["thoughtSignature"]))
        if part.get("functionCall"):
            tools.append(part["functionCall"])
        elif part.get("thought") is True:
            texts.append(part.get("text"))
        elif "text" in part:
            answers.append(part.get("text"))
    text, answer = joined(texts), joined(answers)
    cfg = ((request.get("generationConfig") or {}).get("thinkingConfig") or {})
    display = f"includeThoughts={cfg.get('includeThoughts', 'unset')}"
    usage = response.get("usageMetadata") or {}
    stopped_long = cand.get("finishReason") == "MAX_TOKENS"
    rec = ReasoningRecord(
        run_id=run_id, turn_index=turn_index, provider=PROVIDER, endpoint="generateContent",
        requested_model=str(request.get("model", "")),
        served_model=str(response.get("modelVersion", "")),
        channel=SUMMARY_UNKNOWN if text else NONE, display_mode=display,
        summarizer="unknown" if text else "not_applicable", reasoning_text=text or None,
        reasoning_tokens_reported=count_str(usage.get("thoughtsTokenCount")),
        truncated=stopped_long and not answer and not tools, opaque_fields=opaque,
        answer=answer or None, tool_calls=tools)
    gaps = [opaque_gap("capture", ref["name"], PROVIDER) for ref in opaque]
    if not text:
        gaps.append(omitted_gap(PROVIDER, display))
    if rec.truncated:
        gaps.append(truncation_gap(PROVIDER))
    return Capture(rec, gaps, FIELD_MAP)
