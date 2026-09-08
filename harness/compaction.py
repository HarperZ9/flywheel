"""compaction.py — context auto-compaction for the agent loop, model-agnostic
and re-checkable.

When a conversation grows past its configured token-count budget, fold the
middle into one summary while keeping the task anchor and recent turns verbatim.
The default counter estimates four characters per token; callers can inject a
model tokenizer. The count excludes backend overhead and cannot guarantee fit.

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
SUMMARY_PREFIX = "[compacted:"


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


def _is_compaction_summary(m: dict) -> bool:
    return bool(m.get("compaction_summary")) or str(m.get("content", "")).startswith(SUMMARY_PREFIX)


def _is_pinned(m: dict, pin_roles) -> bool:
    """A message is pinned (never folded away) if it is flagged, or its role is a
    pinned role (policy / gate / tool-permission text lives in these)."""
    if bool(m.get("pinned")): return True
    if _is_compaction_summary(m):
        return False
    return m.get("role") in pin_roles


def _receipt(before, after, budget, keep_head, keep_recent, folded,
             span_hash, summary_hash, method, pinned_kept=0, pin_roles=None,
             budget_floor_tokens: int | None = None,
             budget_status: str | None = None) -> dict:
    return {
        "schema": SCHEMA,
        "method": method,
        "token_budget": budget,
        "tokens_before": before,
        "tokens_after": after,
        "budget_status": budget_status or ("fit" if after <= budget else "unachievable_pinned_floor"),
        "budget_floor_tokens": after if budget_floor_tokens is None else budget_floor_tokens,
        "kept_head": keep_head,
        "kept_recent": keep_recent,
        "pinned_kept": pinned_kept,
        "pin_roles": list(pin_roles) if pin_roles else [],
        "folded_turns": folded,
        "summarized_span_sha256": span_hash,
        "summary_sha256": summary_hash,
    }


def _summary_message(role: str, content: str) -> dict:
    return {"role": role, "content": content, "compaction_summary": True}


def _summary_content(prefix: str, body: str) -> str:
    body = (body or "").strip(); return prefix if not body else f"{prefix}\n{body}"


def _fit_summary_to_budget(fixed: list, prefix: str, body: str, *, token_budget: int,
                           count_tokens: Callable, summary_role: str) -> tuple[str, int, int, str]:
    floor_content = _summary_content(prefix, "")
    floor_tokens = total_tokens(fixed + [_summary_message(summary_role, floor_content)], count_tokens)
    if floor_tokens > token_budget:
        return floor_content, floor_tokens, floor_tokens, "unachievable_pinned_floor"

    full_content = _summary_content(prefix, body)
    full_tokens = total_tokens(fixed + [_summary_message(summary_role, full_content)], count_tokens)
    if full_tokens <= token_budget:
        return full_content, full_tokens, floor_tokens, "fit"

    low, high = 0, len(body or "")
    best_content, best_tokens = floor_content, floor_tokens
    while low <= high:
        mid = (low + high) // 2
        candidate = _summary_content(prefix, (body or "")[:mid])
        tokens = total_tokens(fixed + [_summary_message(summary_role, candidate)], count_tokens)
        if tokens <= token_budget:
            best_content, best_tokens = candidate, tokens
            low = mid + 1
        else:
            high = mid - 1
    return best_content, best_tokens, floor_tokens, "fit"


def _budget_checks(receipt: dict, original: list, rendered: list, fixed: list,
                   summary: dict | None, count_tokens: Callable) -> dict:
    before, after = total_tokens(original, count_tokens), total_tokens(rendered, count_tokens)
    checks = {
        "tokens_before": receipt.get("tokens_before") == before,
        "tokens_after": receipt.get("tokens_after") == after,
    }
    if "budget_status" not in receipt and "budget_floor_tokens" not in receipt:
        checks["budget_fields_legacy_absent"] = True
        return checks
    budget = receipt.get("token_budget")
    if not isinstance(budget, int):
        checks.update(budget_status=False, budget_floor_tokens=False)
        return checks
    if summary is None: floor = after
    else:
        floor_content = str(summary.get("content", "")).splitlines()[0] if str(summary.get("content", "")) else ""
        floor = total_tokens(fixed + [_summary_message(str(summary.get("role", "system")), floor_content)], count_tokens)
    checks["budget_floor_tokens"] = receipt.get("budget_floor_tokens") == floor
    checks["budget_status"] = receipt.get("budget_status") == ("fit" if after <= budget else "unachievable_pinned_floor" if floor > budget else "summary_over_budget")
    return checks


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
            0, pins, before))

    head = msgs[:keep_head]
    tail = msgs[len(msgs) - keep_recent:] if keep_recent else []
    middle = msgs[keep_head: len(msgs) - keep_recent] if keep_recent else msgs[keep_head:]
    pinned = [m for m in middle if _is_pinned(m, pins)]
    foldable = [m for m in middle if not _is_pinned(m, pins)]
    if not foldable:                                # nothing to fold (all pinned / empty)
        return CompactionResult(msgs, False, _receipt(
            before, before, token_budget, keep_head, keep_recent, 0, None, None, "noop",
            len(pinned), pins, before))

    span_hash = _sha_messages(foldable)
    prefix = f"[compacted: {len(foldable)} earlier turns folded to fit context]"
    fixed = head + pinned + tail
    summary_content, after, floor_tokens, budget_status = _fit_summary_to_budget(
        fixed, prefix, summarize(foldable), token_budget=token_budget,
        count_tokens=count_tokens, summary_role=summary_role)
    summary_msg = _summary_message(summary_role, summary_content)
    new_msgs = head + pinned + [summary_msg] + tail
    return CompactionResult(new_msgs, True, _receipt(
        before, after, token_budget, keep_head, keep_recent, len(foldable),
        span_hash, _sha_text(summary_content), "middle-fold", len(pinned), pins,
        floor_tokens, budget_status))


def verify_compaction(original_messages: list, result: CompactionResult,
                      count_tokens: Callable = approx_tokens) -> dict:
    """Re-check a fold against the messages it was computed from. Confirms the kept
    head and tail are byte-identical, the folded span hashes to the receipt value,
    and the inserted summary hashes to the receipt value. Returns a MATCH/DRIFT
    verdict with the per-check breakdown, so a caller can prove tampering."""
    r = result.receipt
    if not result.compacted or r.get("method") == "noop":
        ok = result.messages == list(original_messages)
        checks = {"noop_unchanged": ok}
        checks.update(_budget_checks(r, list(original_messages), result.messages, result.messages, None, count_tokens))
        return {"verdict": "MATCH" if all(checks.values()) else "DRIFT", "checks": checks}

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
    summary = res[kh + pc] if len(res) > kh + pc else {}

    checks = {
        "head_preserved": res[:kh] == head,
        "pinned_preserved": res[kh:kh + pc] == pinned,     # policy text kept verbatim, in order
        "tail_preserved": (res[len(res) - kr:] == tail) if kr else True,
        "span_hash": _sha_messages(foldable) == r["summarized_span_sha256"],
        "summary_hash": _sha_text(summary.get("content", "")) == r["summary_sha256"],
        "folded_turns": r.get("folded_turns") == len(foldable),
        "pinned_kept": pc == len(pinned),
    }
    checks.update(_budget_checks(r, orig, res, head + pinned + tail, summary, count_tokens))
    return {"verdict": "MATCH" if all(checks.values()) else "DRIFT", "checks": checks}
