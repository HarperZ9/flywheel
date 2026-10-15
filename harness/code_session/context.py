"""context.py -- keep a long session inside the model's window, and @-mentions.

Compaction: before each model call, when the conversation's estimated size
passes the budget (`--compact-budget`, default 60,000 estimated tokens; 0 turns
it off), the middle of the conversation is folded into one summary by the
existing extractive compactor (harness/compaction.py). The first request and the
most recent turns stay verbatim. The summary goes in as a user turn and any two
neighbouring turns of the same role are merged, so the conversation still
alternates the way every provider accepts. The compactor's receipt (what was
folded, hashes of before and after) goes on the session ledger; the full
untruncated record stays on the ledger, which compaction never touches.

Mentions: `@path` in a request attaches that file's text (inside the project
folder only, at most 64 KiB each and 5 files per request), and the ledger
records each attached path with its sha256.

Sizes are estimates (about 4 characters per token), and are labeled as such.
"""
from __future__ import annotations

import hashlib
import json
import os
import re

from harness.compaction import approx_tokens, compact

DEFAULT_BUDGET = 60000
KEEP_RECENT = 8
MENTION = re.compile(r"(?<!\S)@([^\s@]+)")
MAX_MENTION_BYTES = 64 * 1024
MAX_MENTIONS = 5


def estimate(system: str, history: list) -> int:
    return approx_tokens(system) + sum(approx_tokens(str(m.get("content", ""))) for m in history)


def _alternate(messages: list) -> list:
    """Only role and content, user/assistant only, neighbouring same roles merged."""
    out: list = []
    for m in messages:
        role = "assistant" if m.get("role") == "assistant" else "user"
        content = str(m.get("content", ""))
        if out and out[-1]["role"] == role:
            out[-1]["content"] += "\n\n" + content
        else:
            out.append({"role": role, "content": content})
    return out


def would_fold(agent, budget: int) -> bool:
    return (budget > 0 and len(agent.history) > KEEP_RECENT + 1
            and estimate(agent.system, agent.history) > budget)


def maybe_fold(agent, budget: int) -> "dict | None":
    """Fold the conversation if it is over budget; returns the receipt or None."""
    if budget <= 0 or len(agent.history) <= KEEP_RECENT + 1:
        return None
    if estimate(agent.system, agent.history) <= budget:
        return None
    res = compact(agent.history, token_budget=budget, keep_recent=KEEP_RECENT,
                  summary_role="user", pin_roles=())
    if not res.compacted:
        return None
    agent.history = _alternate(res.messages)
    return res.receipt


def expand_mentions(root: str, text: str) -> "tuple[str, list]":
    """Attach the files a request names with @path; returns (text, records)."""
    from harness.local_tools import _safe_path
    blocks, records = [], []
    for rel in MENTION.findall(text)[:MAX_MENTIONS]:
        path = _safe_path(root, rel.rstrip(".,;:)"))
        if path is None or not os.path.isfile(path):
            continue
        with open(path, "rb") as f:
            raw = f.read(MAX_MENTION_BYTES + 1)
        cut = len(raw) > MAX_MENTION_BYTES
        body = raw[:MAX_MENTION_BYTES].decode("utf-8", errors="replace")
        shown = os.path.relpath(path, root).replace("\\", "/")
        blocks.append(f"--- FILE: {shown}{' (truncated)' if cut else ''} ---\n{body}")
        records.append({"path": shown, "sha256": hashlib.sha256(raw).hexdigest(),
                        "truncated": cut})
    if not blocks:
        return text, []
    return text + "\n\n" + "\n\n".join(blocks), records


def report(session) -> str:
    agent = session.agent
    used = estimate(agent.system, agent.history)
    budget = session.compact_budget
    folds = sum(1 for e in session.ledger.entries if e.kind == "compaction")
    lines = [f"conversation: about {used} tokens (estimated at 4 characters per token), "
             f"{len(agent.history)} messages",
             f"system prompt: about {approx_tokens(agent.system)} tokens",
             f"compaction: {'off' if budget <= 0 else f'at about {budget} tokens'}; "
             f"{folds} fold(s) so far",
             "instruction files: " + (", ".join(os.path.basename(i.path) for i in session.loaded)
                                      or "none")]
    return "\n".join(lines)


def record_fold(ledger, receipt: dict) -> None:
    ledger.append("compaction", json.dumps(receipt, sort_keys=True, default=str),
                  {"folded": True})
