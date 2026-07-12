"""compaction.py — context auto-compaction for the agent loop, model-agnostic
and re-checkable.

The modern-harness feature the other local runners skip: when a conversation
grows past a token budget, fold the middle of the transcript into one summary
turn so the loop keeps running inside any model's context window, while keeping
the task anchor and the most recent turns verbatim.

The fold is witnessed. The receipt binds the sha256 of the exact messages that
were summarized and the sha256 of the summary that replaced them, so a stranger
can re-check (verify_compaction) that the compaction refers to the run that
happened and left the kept turns byte-identical. A view that cannot show that it
tampered is not shipped.

Loop-agnostic: operates on a plain list of {role, content} messages, the shape of
LocalAgent.history and SessionLedger.transcript(). Model-agnostic: the summarizer
is injected, so any routed model (or a deterministic stub in tests) produces the
fold; the default is a zero-model extractive fallback that always works offline.
Zero dependencies.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Callable

SCHEMA = "flywheel.compaction/v1"


def approx_tokens(text: str) -> int:
    """Zero-dep token estimate (~4 chars/token). No tokenizer dependency; the
    caller may inject a real counter for exactness."""
    return (len(text) + 3) // 4 if text else 0


def _line(m: dict) -> str:
    return f"{m.get('role', 'user')}: {m.get('content', '')}"


def total_tokens(messages: list, count_tokens: Callable = approx_tokens) -> int:
    """Tokens over the rendered transcript, matching how the backend flattens it."""
    return sum(count_tokens(_line(m)) for m in messages)


def _sha_messages(messages: list) -> str:
    blob = json.dumps(
        [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages],
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _sha_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def extractive_summary(messages: list) -> str:
    """Zero-model fallback: the first line of each folded turn, labelled by role.
    Deterministic and offline; a real summarizer can be injected in its place."""
    lines = []
    for m in messages:
        role = m.get("role", "user")
        body = (m.get("content", "") or "").strip().splitlines()
        lines.append(f"- {role}: {body[0][:200] if body else ''}")
    return "\n".join(lines)


@dataclass
class CompactionResult:
    messages: list
    compacted: bool
    receipt: dict


def _receipt(before, after, budget, keep_head, keep_recent, folded,
             span_hash, summary_hash, method) -> dict:
    return {
        "schema": SCHEMA,
        "method": method,
        "token_budget": budget,
        "tokens_before": before,
        "tokens_after": after,
        "kept_head": keep_head,
        "kept_recent": keep_recent,
        "folded_turns": folded,
        "summarized_span_sha256": span_hash,
        "summary_sha256": summary_hash,
    }


def compact(messages: list, *, token_budget: int, keep_recent: int = 6,
            keep_head: int = 1, summarize: Callable = extractive_summary,
            count_tokens: Callable = approx_tokens,
            summary_role: str = "system") -> CompactionResult:
    """Fold the middle of `messages` into one summary turn if the transcript
    exceeds `token_budget`. Keeps the first `keep_head` turns (the task anchor)
    and the last `keep_recent` turns verbatim. Returns the (possibly unchanged)
    messages, whether it compacted, and a re-checkable receipt.

    A no-op (already within budget, or too few turns to fold) returns the input
    unchanged with a method="noop" receipt.
    """
    msgs = list(messages)
    before = total_tokens(msgs, count_tokens)
    if before <= token_budget or len(msgs) <= keep_head + keep_recent + 1:
        return CompactionResult(msgs, False, _receipt(
            before, before, token_budget, keep_head, keep_recent, 0, None, None, "noop"))

    head = msgs[:keep_head]
    tail = msgs[len(msgs) - keep_recent:] if keep_recent else []
    middle = msgs[keep_head: len(msgs) - keep_recent] if keep_recent else msgs[keep_head:]
    if not middle:
        return CompactionResult(msgs, False, _receipt(
            before, before, token_budget, keep_head, keep_recent, 0, None, None, "noop"))

    span_hash = _sha_messages(middle)
    summary_content = (f"[compacted: {len(middle)} earlier turns folded to fit context]\n"
                       + summarize(middle))
    summary_msg = {"role": summary_role, "content": summary_content}
    new_msgs = head + [summary_msg] + tail
    after = total_tokens(new_msgs, count_tokens)
    return CompactionResult(new_msgs, True, _receipt(
        before, after, token_budget, keep_head, keep_recent, len(middle),
        span_hash, _sha_text(summary_content), "middle-fold"))


def verify_compaction(original_messages: list, result: CompactionResult) -> dict:
    """Re-check a fold against the messages it was computed from. Confirms the kept
    head and tail are byte-identical, the folded span hashes to the receipt value,
    and the inserted summary hashes to the receipt value. Returns a MATCH/DRIFT
    verdict with the per-check breakdown, so a caller can prove tampering."""
    r = result.receipt
    if not result.compacted or r.get("method") == "noop":
        ok = result.messages == list(original_messages)
        return {"verdict": "MATCH" if ok else "DRIFT", "checks": {"noop_unchanged": ok}}

    orig = list(original_messages)
    kh, kr = r["kept_head"], r["kept_recent"]
    head = orig[:kh]
    tail = orig[len(orig) - kr:] if kr else []
    middle = orig[kh: len(orig) - kr] if kr else orig[kh:]

    checks = {
        "head_preserved": result.messages[:kh] == head,
        "tail_preserved": (result.messages[len(result.messages) - kr:] == tail) if kr else True,
        "span_hash": _sha_messages(middle) == r["summarized_span_sha256"],
        "summary_hash": _sha_text(result.messages[kh].get("content", "")) == r["summary_sha256"],
    }
    return {"verdict": "MATCH" if all(checks.values()) else "DRIFT", "checks": checks}
