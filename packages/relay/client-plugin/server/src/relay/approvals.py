"""approvals.py -- re-derivable per-step approval of mutating tool calls.

Cline shows each proposed write or command for approval, then forgets it. relay
records the decision as a hash-chained ledger entry bound to the exact bytes of the
call, so a stranger re-derives from the run alone that a human (or a policy) gated
every mutating step, and that the approved bytes equal the executed bytes. Opt-in:
with no approve callback the loop records nothing and behaves exactly as before.
"""
from __future__ import annotations

import hashlib
import json

from .local_tools import WRITE_TOOLS

GATED, UNGATED, NOT_GATED = "GATED", "UNGATED", "NOT_GATED"


def is_mutating(name: str) -> bool:
    """A call that can change the tree: a file write or a shell command."""
    return name in WRITE_TOOLS or name == "run"


def call_hash(name: str, args: dict) -> str:
    """sha256 of the canonical tool_call content, so an approval binds to the exact
    bytes the ledger records for that call (approved bytes == executed bytes)."""
    return hashlib.sha256(
        f"{name} {json.dumps(args, sort_keys=True)}".encode("utf-8")).hexdigest()


def _parse(content: str) -> tuple:
    name, _, rest = (content or "").partition(" ")
    try:
        return name, (json.loads(rest) if rest else {})
    except (json.JSONDecodeError, ValueError):
        return name, {}


def approval_verdict(ledger) -> str:
    """Re-derive the gating verdict from the ledger alone:
      NOT_GATED -- no approval entries (the run was not gated; nothing to verify),
      UNGATED   -- a mutating tool_call has no matching approval decision at all,
      GATED     -- every mutating tool_call carries a matching approval (allow or deny).
    A denied call is still gated: a human saw it. UNGATED means a mutation slipped
    through with no decision bound to its bytes, which fails closed."""
    decided: dict = {}          # call_hash -> decision seen so far
    saw_approval = False
    for e in getattr(ledger, "entries", []):
        kind = getattr(e, "kind", "")
        if kind == "approval":
            saw_approval = True
            decided[getattr(e, "content", "")] = (getattr(e, "meta", {}) or {}).get("decision")
        elif kind == "tool_call":
            name, args = _parse(getattr(e, "content", ""))
            if is_mutating(name) and call_hash(name, args) not in decided:
                return UNGATED if saw_approval else NOT_GATED
    return GATED if saw_approval else NOT_GATED
