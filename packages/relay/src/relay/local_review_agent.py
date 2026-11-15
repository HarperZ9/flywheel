"""local_review_agent.py -- an independent, fresh-context reviewer.

A run's own review.py projection is derived from the SAME trajectory the author
produced, so it shares the author's blind spots. This adds a second opinion: a
fresh agent that sees ONLY the task and the diff, never the author's ledger,
receipts, or reasoning, and returns an independent APPROVE / REQUEST_CHANGES
verdict with findings. A reviewer without the author's context finds what the
author, and a projection of the author's own run, cannot.

The reviewer is one model call, so it is injected (a make_agent factory) and fully
testable without a backend. Honest null: the reviewer is itself a model and can be
wrong; its verdict is a second signal, never an oracle, and it never gates the run
(the witnessed accept gate does that). It reviews the recorded edit set, so a file
changed by a shell redirection outside the witnessed tools is not in its view.
"""
from __future__ import annotations

from .review import _field, _parse_call

SCHEMA = "relay.review-agent/v1"
APPROVE, REQUEST_CHANGES, UNCLEAR = "APPROVE", "REQUEST_CHANGES", "UNCLEAR"

_SYSTEM = (
    "You are a senior code reviewer. You see ONLY the task and the diff, not how it "
    "was produced. Review the diff for correctness, missed edge cases, and risk. "
    "Your first line must be exactly APPROVE or REQUEST_CHANGES. Then a short "
    "bulleted list of specific findings. Be terse and concrete.")


def witnessed_diff(ledger) -> str:
    """Reconstruct the diff a reviewer reads from the witnessed edits only."""
    blocks = []
    for entry in getattr(ledger, "entries", []):
        if _field(entry, "kind", "") != "tool_call":
            continue
        name, args = _parse_call(_field(entry, "content", ""))
        if name == "write_file" and args.get("path"):
            blocks.append(f"--- {args['path']} (written) ---\n{args.get('content', '')}")
        elif name == "edit_file" and args.get("path"):
            blocks.append(f"--- {args['path']} (edited) ---\n"
                          f"- {args.get('old', '')}\n+ {args.get('new', '')}")
        elif name == "edit_lines" and args.get("path"):
            span = args.get("at") or args.get("after") or "?"
            if args.get("end"):
                span = f"{args.get('at')}..{args['end']}"
            blocks.append(f"--- {args['path']} (edited @{span}) ---\n+ {args.get('new', '')}")
        elif name == "edit_plan":
            for op in args.get("ops", []):
                if isinstance(op, dict) and op.get("path"):
                    span = op.get("at") or op.get("after") or "?"
                    if op.get("end"):
                        span = f"{op.get('at')}..{op['end']}"
                    blocks.append(f"--- {op['path']} (edited @{span}) ---\n+ {op.get('new', '')}")
    return "\n\n".join(blocks)


def _goal(ledger) -> str:
    for entry in getattr(ledger, "entries", []):
        if _field(entry, "kind", "") == "user":
            return _field(entry, "content", "")
    return ""


def parse_verdict(text: str) -> str:
    """APPROVE / REQUEST_CHANGES / UNCLEAR, read from the reviewer's reply."""
    up = (text or "").upper()
    lines = [ln.strip() for ln in up.splitlines() if ln.strip()]
    head = lines[0] if lines else ""
    if "REQUEST_CHANGES" in head or "REQUEST CHANGES" in head:
        return REQUEST_CHANGES
    if "APPROVE" in head:
        return APPROVE
    if "REQUEST_CHANGES" in up or "REQUEST CHANGES" in up:
        return REQUEST_CHANGES
    if "APPROVE" in up:
        return APPROVE
    return UNCLEAR


def review_run(make_agent, ledger) -> dict:
    """Spawn a fresh reviewer over the goal + diff (never the author's ledger) and
    return its independent verdict + findings. ``make_agent()`` returns an agent with
    a settable ``.system`` and ``.send(text) -> {content:[{text}], backend}``."""
    diff = witnessed_diff(ledger)
    if not diff.strip():
        return {"schema": SCHEMA, "verdict": APPROVE, "reviewed": False,
                "findings": "no witnessed edits to review"}
    agent = make_agent()
    agent.system = _SYSTEM
    resp = agent.send(f"TASK:\n{_goal(ledger)}\n\nDIFF (review only this):\n{diff}")
    text = resp["content"][0]["text"] if resp.get("content") else ""
    return {"schema": SCHEMA, "verdict": parse_verdict(text), "reviewed": True,
            "findings": text.strip(), "backend": resp.get("backend")}
