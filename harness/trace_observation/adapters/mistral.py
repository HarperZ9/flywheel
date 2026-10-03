"""mistral.py -- Chat Completions with ThinkChunk content.

Documented (MIS-REASONING, read 2026-10-01, moderate): a ThinkChunk "contains
the model's reasoning trace"; the page does not say whether the trace is raw or
post-processed, so the channel is unspecified_trace and components that need
raw reasoning refuse it. No opaque field is documented. The chunk layout below
is adapter-unverified.
"""
from __future__ import annotations

from ..channel import NONE, UNSPECIFIED, ReasoningRecord
from ._common import UNVERIFIED, Capture, joined, truncation_gap

PROVIDER = "mistral"
FIELD_MAP = {
    "choices[0].message.content[type=thinking].thinking[].text": ("MIS-REASONING", "moderate"),
    "choices[0].message.content[type=text].text": (UNVERIFIED, "low"),
    "choices[0].finish_reason": (UNVERIFIED, "low"),
}


def capture(request: dict, response: dict, *, run_id: str, turn_index: int = 0) -> Capture:
    request = request or {}
    choice = (response.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    content = msg.get("content")
    texts, answers = [], []
    if isinstance(content, str):
        answers.append(content)
    for chunk in content if isinstance(content, list) else []:
        if chunk.get("type") == "thinking":
            for inner in chunk.get("thinking") or []:
                texts.append(inner.get("text") if isinstance(inner, dict) else inner)
        elif chunk.get("type") == "text":
            answers.append(chunk.get("text"))
    text, answer = joined(texts), joined(answers)
    rec = ReasoningRecord(
        run_id=run_id, turn_index=turn_index, provider=PROVIDER, endpoint="chat.completions",
        requested_model=str(request.get("model", "")), served_model=str(response.get("model", "")),
        channel=UNSPECIFIED if text else NONE,
        display_mode=f"reasoning_effort={request.get('reasoning_effort', 'unset')}",
        summarizer="unknown" if text else "not_applicable", reasoning_text=text or None,
        truncated=choice.get("finish_reason") == "length" and not answer,
        answer=answer or None)
    return Capture(rec, [truncation_gap(PROVIDER)] if rec.truncated else [], FIELD_MAP)
