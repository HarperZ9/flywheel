"""run_view.py -- visualize a witnessed relay run as a hash-chained trajectory.

Every competitor can print a log. Only relay can draw a run a stranger can SEE is
unbroken: each ledger entry is a node, and the edge into it carries the hash-chain
link. Each edge re-derives ``Entry.compute_hash`` against the stored ``entry_hash``
and ``prev_hash``; a matching edge renders solid green, and the instant a byte is
flipped that one edge snaps red and the verdict flips to REFUTED. The moat, made
visible -- competitors cannot draw this because they keep no re-derivable chain.

Overlaid on the timeline, from modules that already witness the run: the accept
certificate (verified / check_passed / check_trusted / accepted) when a run result
is supplied, the reward-hacking integrity flags (``integrity.trajectory_integrity``)
on the offending node, and the intent / claimed-history audit (``intent_audit``).
Stdlib only; ``--no-color`` emits a byte-stable plain-text timeline safe to snapshot.

  python -m relay.run_view <ledger.jsonl> [--no-color]
"""
from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import dataclass

from .local_session import GENESIS, Entry, SessionLedger

_RESET, _GREEN, _RED, _AMBER, _DIM, _BOLD = (
    "\x1b[0m", "\x1b[32m", "\x1b[31m", "\x1b[33m", "\x1b[2m", "\x1b[1m")

OK = "OK"
BROKEN = "BROKEN"
_PREVIEW = 68


@dataclass(frozen=True)
class EdgeStatus:
    seq: int
    status: str          # OK | BROKEN
    reason: str = ""


@dataclass
class RunView:
    ledger: SessionLedger
    result: dict | None = None


def load_run(path: str) -> RunView:
    """Load a saved run WITHOUT refusing a broken chain, so a tampered run can be
    inspected and shown broken instead of raising."""
    return RunView(SessionLedger.load(path, verify=False))


def verify_edges(ledger) -> list[EdgeStatus]:
    """Re-derive each entry's hash and prev-link per edge (vs SessionLedger.verify's
    single bool), so a break is localized to the entry whose hash or link fails."""
    out: list[EdgeStatus] = []
    prev = GENESIS
    for i, e in enumerate(ledger.entries):
        reason = ""
        if e.seq != i:
            reason = f"seq {e.seq} out of order at position {i}"
        elif e.prev_hash != prev:
            reason = "prev_hash does not match the previous entry"
        elif Entry.compute_hash(e.seq, e.kind, e.content, e.meta, e.prev_hash) != e.entry_hash:
            reason = "entry_hash does not re-derive from its fields"
        out.append(EdgeStatus(e.seq, BROKEN if reason else OK, reason))
        prev = e.entry_hash
    return out


def _paint(text: str, color: str, on: bool) -> str:
    return f"{color}{text}{_RESET}" if on else text


def _first_broken(edges: list[EdgeStatus]) -> EdgeStatus | None:
    return next((e for e in edges if e.status == BROKEN), None)


def _verdict(result: dict | None, edges: list[EdgeStatus],
             grounding: str | None = None) -> tuple[str, str, str]:
    """Return (label, ansi_color, detail). Verdict-only: ALLOW / UNGROUNDED /
    UNVERIFIABLE / REFUTED, never rounded up. A broken chain, a gamed grader, or a
    summary the ledger refutes each refutes the run."""
    broken = _first_broken(edges)
    if broken is not None:
        return "REFUTED", _RED, f"hash chain broken at seq {broken.seq} ({broken.reason})"
    if grounding == "REFUTED":
        return "REFUTED", _RED, "the final answer claims work the ledger refutes"
    if result is None:
        if grounding == "UNGROUNDED":
            return "UNGROUNDED", _AMBER, "the final answer claims work the ledger does not witness"
        return "CHAIN INTACT", _AMBER, f"{len(edges)} entries re-derive; no accept certificate attached"
    if not result.get("check_trusted", True):
        return "REFUTED", _RED, "acceptance check passed but the grader was tampered with"
    if grounding == "UNGROUNDED":
        return "UNGROUNDED", _AMBER, "the final answer claims work the ledger does not witness"
    if result.get("accepted"):
        return "ALLOW", _GREEN, "run accepted: verified, chain intact, check not gamed"
    return "UNVERIFIABLE", _AMBER, "chain intact but the run was not accepted"


def _header(result: dict | None, edges: list[EdgeStatus], grounding: str | None,
            color: bool) -> list[str]:
    label, ansi, detail = _verdict(result, edges, grounding)
    lines = [_paint(f"{label}", _BOLD + ansi, color) + "  " + _paint(detail, _DIM, color)]
    if result is not None:
        cert = "  ".join(f"{k}={result.get(k)}" for k in
                         ("verified", "check_passed", "check_trusted", "accepted"))
        lines.append(_paint("  " + cert, _DIM, color))
    lines.append("")
    return lines


def _preview(content: str) -> str:
    head = (content or "").splitlines()[0] if (content or "").strip() else ""
    return head[:_PREVIEW] + ("…" if len(head) > _PREVIEW else "")


def _seq_of_where(where: str) -> int | None:
    parts = (where or "").split()
    if len(parts) >= 2 and parts[0] == "seq" and parts[1].isdigit():
        return int(parts[1])
    return None


def _overlays(seq: int, integrity: dict, intent: dict, color: bool) -> list[str]:
    lines = []
    for flag in integrity.get(seq, []):
        lines.append(_paint(f"      ! integrity: {flag['kind']} — {flag['detail']}", _RED, color))
    for finding in intent.get(seq, []):
        ansi = _RED if finding["severity"] == "critical" else _AMBER
        lines.append(_paint(f"      ! {finding['detector']}: {finding['summary']}", ansi, color))
    return lines


def _footer(ledger, color: bool) -> list[str]:
    from .review import run_review
    rv = run_review(ledger.entries)
    parts = [f"reviewability {rv['reviewability']:.2f}",
             f"edited-unread {len(rv['edited_unread'])}",
             f"unverified {len(rv['unverified_edits'])}",
             f"gate-denials {len(rv['gate_denials'])}",
             f"failed-calls {rv['failed_calls']}"]
    return ["", _paint("review  " + " | ".join(parts), _DIM, color)]


def _index_flags(ledger) -> tuple[dict, dict]:
    from .integrity import integrity_report, trajectory_integrity
    from .intent_audit import audit_intent
    integrity: dict = defaultdict(list)
    for flag in integrity_report(trajectory_integrity(ledger))["flags"]:
        seq = _seq_of_where(flag["where"])
        if seq is not None:
            integrity[seq].append(flag)
    intent: dict = defaultdict(list)
    for finding in audit_intent(ledger)["findings"]:
        intent[finding["seq"]].append(finding)
    return integrity, intent


def render(ledger, result: dict | None = None, *, color: bool = True) -> str:
    """A vertical timeline: accept-certificate header, then one node per entry with
    its hash-chain edge (green intact / red broken) and any integrity/intent flag."""
    from .claim_grounding import ground_final_answer
    edges = verify_edges(ledger)
    integrity, intent = _index_flags(ledger)
    grounding = ground_final_answer(ledger)
    lines = _header(result, edges, grounding["verdict"], color)
    for i, e in enumerate(ledger.entries):
        edge = edges[i]
        glyph = ("|" if not color else (_GREEN + "│" + _RESET if edge.status == OK
                                        else _RED + "╳" + _RESET))
        if i > 0:
            lines.append(f"  {glyph}")
        marker = "*" if not color else ("●" if edge.status == OK else _RED + "●" + _RESET)
        node = f"  {marker} [{e.seq}] {e.kind:<12} {_preview(e.content)}"
        if edge.status == BROKEN:
            node += _paint(f"   <- {edge.reason}", _RED, color) if color else f"   <- {edge.reason}"
        lines.append(node)
        lines += _overlays(e.seq, integrity, intent, color)
        if e.seq == grounding.get("seq") and grounding["verdict"] in ("REFUTED", "UNGROUNDED"):
            ansi = _RED if grounding["verdict"] == "REFUTED" else _AMBER
            lines.append(_paint(f"      ! grounding: the summary is {grounding['verdict']} "
                                "against the ledger", ansi, color))
    lines += _footer(ledger, color)
    return "\n".join(lines) + "\n"


def _main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    color = "--no-color" not in argv
    paths = [a for a in argv if not a.startswith("-")]
    if not paths:
        print("usage: python -m relay.run_view <ledger.jsonl> [--no-color]", file=sys.stderr)
        return 2
    try:
        view = load_run(paths[0])
    except (OSError, ValueError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(render(view.ledger, view.result, color=color))
    # exit non-zero when the chain does not re-derive, so --view is a CI-usable check
    return 0 if all(e.status == OK for e in verify_edges(view.ledger)) else 1


if __name__ == "__main__":
    raise SystemExit(_main())
