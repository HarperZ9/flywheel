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
import math
import re
from collections import Counter
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


_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def _sentences(text: str) -> list:
    return [s.strip() for s in _SENT_SPLIT.split(text or "") if s.strip()]


def _terms(sentence: str) -> "Counter":
    return Counter(re.findall(r"[a-z0-9]+", sentence.lower()))


def _cosine(a: "Counter", b: "Counter") -> float:
    common = set(a) & set(b)
    if not common:
        return 0.0
    num = sum(a[t] * b[t] for t in common)
    da = math.sqrt(sum(v * v for v in a.values()))
    db = math.sqrt(sum(v * v for v in b.values()))
    return num / (da * db) if da and db else 0.0


def lexrank_summary(messages: list, *, max_sentences: int = 8,
                    sim_threshold: float = 0.1) -> str:
    """Deterministic LexRank-style extractive summary (stdlib only): rank the
    folded turns' sentences by graph centrality over a cosine-similarity graph and
    keep the most central ones, emitted in original order. Strictly better signal
    than first-line-truncated, and fully re-derivable (no model, no randomness)."""
    labeled = [(m.get("role", "user"), s)
               for m in messages for s in _sentences(m.get("content", ""))]
    if not labeled:
        return ""
    if len(labeled) <= max_sentences:
        return "\n".join(f"- {r}: {s[:200]}" for r, s in labeled)
    vecs = [_terms(s) for _, s in labeled]
    n = len(vecs)
    scores = [0.0] * n
    for i in range(n):
        for j in range(i + 1, n):
            sim = _cosine(vecs[i], vecs[j])
            if sim >= sim_threshold:
                scores[i] += sim
                scores[j] += sim
    top = sorted(range(n), key=lambda i: (-scores[i], i))[:max_sentences]
    return "\n".join(f"- {labeled[k][0]}: {labeled[k][1][:200]}" for k in sorted(top))


@dataclass
class CompactionResult:
    messages: list
    compacted: bool
    receipt: dict


def _is_pinned(m: dict, pin_roles) -> bool:
    """A message is pinned (never folded away) if it is flagged, or its role is a
    pinned role (policy / gate / tool-permission text lives in these)."""
    return bool(m.get("pinned")) or m.get("role") in pin_roles


def _receipt(before, after, budget, keep_head, keep_recent, folded,
             span_hash, summary_hash, method, pinned_kept=0, pin_roles=None) -> dict:
    return {
        "schema": SCHEMA,
        "method": method,
        "token_budget": budget,
        "tokens_before": before,
        "tokens_after": after,
        "kept_head": keep_head,
        "kept_recent": keep_recent,
        "pinned_kept": pinned_kept,
        "pin_roles": list(pin_roles) if pin_roles else [],
        "folded_turns": folded,
        "summarized_span_sha256": span_hash,
        "summary_sha256": summary_hash,
    }


def compact(messages: list, *, token_budget: int, keep_recent: int = 6,
            keep_head: int = 1, summarize: Callable = lexrank_summary,
            count_tokens: Callable = approx_tokens,
            summary_role: str = "system", pin_roles=("system",)) -> CompactionResult:
    """Fold the middle of `messages` into one summary turn if the transcript
    exceeds `token_budget`. Keeps the first `keep_head` turns (the task anchor)
    and the last `keep_recent` turns verbatim. PINNED messages in the middle
    (role in `pin_roles`, or flagged `pinned`) are kept verbatim too and never
    folded away: policy / gate / tool-permission text must survive compaction
    (compaction otherwise raises policy-violation rate sharply). Returns the
    (possibly unchanged) messages, whether it compacted, and a re-checkable receipt.

    A no-op (within budget, too few turns, or nothing foldable) returns the input
    unchanged with a method="noop" receipt.
    """
    msgs = list(messages)
    before = total_tokens(msgs, count_tokens)
    pins = list(pin_roles)
    if before <= token_budget or len(msgs) <= keep_head + keep_recent + 1:
        return CompactionResult(msgs, False, _receipt(
            before, before, token_budget, keep_head, keep_recent, 0, None, None, "noop",
            0, pins))

    head = msgs[:keep_head]
    tail = msgs[len(msgs) - keep_recent:] if keep_recent else []
    middle = msgs[keep_head: len(msgs) - keep_recent] if keep_recent else msgs[keep_head:]
    pinned = [m for m in middle if _is_pinned(m, pins)]
    foldable = [m for m in middle if not _is_pinned(m, pins)]
    if not foldable:                                # nothing to fold (all pinned / empty)
        return CompactionResult(msgs, False, _receipt(
            before, before, token_budget, keep_head, keep_recent, 0, None, None, "noop",
            len(pinned), pins))

    span_hash = _sha_messages(foldable)
    summary_content = (f"[compacted: {len(foldable)} earlier turns folded to fit context]\n"
                       + summarize(foldable))
    summary_msg = {"role": summary_role, "content": summary_content}
    new_msgs = head + pinned + [summary_msg] + tail
    after = total_tokens(new_msgs, count_tokens)
    return CompactionResult(new_msgs, True, _receipt(
        before, after, token_budget, keep_head, keep_recent, len(foldable),
        span_hash, _sha_text(summary_content), "middle-fold", len(pinned), pins))


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
    pins = r.get("pin_roles", [])
    pc = r.get("pinned_kept", 0)
    head = orig[:kh]
    tail = orig[len(orig) - kr:] if kr else []
    middle = orig[kh: len(orig) - kr] if kr else orig[kh:]
    pinned = [m for m in middle if _is_pinned(m, pins)]
    foldable = [m for m in middle if not _is_pinned(m, pins)]
    res = result.messages

    checks = {
        "head_preserved": res[:kh] == head,
        "pinned_preserved": res[kh:kh + pc] == pinned,     # policy text kept verbatim, in order
        "tail_preserved": (res[len(res) - kr:] == tail) if kr else True,
        "span_hash": _sha_messages(foldable) == r["summarized_span_sha256"],
        "summary_hash": _sha_text(res[kh + pc].get("content", "")) == r["summary_sha256"],
    }
    return {"verdict": "MATCH" if all(checks.values()) else "DRIFT", "checks": checks}
