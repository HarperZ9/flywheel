"""Grounding check — the rigor-not-relativism guardrail against the over-build failure mode.

The live demonstration found that a reconciliation can ADD claims not supported by the subject
(it "over-builds" — completeness bought with invention). This penalizes the `grounded` dimension when
a candidate asserts tokens the subject's perceptible forms do not contain. Minimal + honest: it flags
unsupported salient tokens, not a semantic proof — a real witness does deeper, behind the same call.
"""
from __future__ import annotations
import re

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_-]{3,}")


def _salient(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text)}


# Common English words carry no claim — flagging them as "unsupported" is noise, not grounding.
# (The live run surfaced this: words like must/pass/execute were over-flagged.) A real semantic
# grounding witness does better; this heuristic only catches *salient* unsupported tokens.
_STOP = {
    "text", "diagram", "from", "reconciled", "mine", "theirs", "this", "that", "with", "into",
    "toward", "telos", "proposal", "channel", "must", "pass", "passes", "execute", "executes",
    "executing", "generalize", "consequential", "producer", "pluggable", "before", "after", "then",
    "every", "each", "into", "onto", "through", "across", "where", "which", "would", "could", "should",
    "their", "them", "they", "what", "when", "while", "about", "above", "below", "between", "single",
    "best", "form", "result", "action", "actions", "decision", "decisions", "system", "value", "values",
    "make", "makes", "made", "take", "takes", "using", "used", "uses", "have", "having", "been", "into",
}


def unsupported_tokens(candidate: str, subject_views: dict[str, str]) -> set[str]:
    """SALIENT tokens in the candidate absent from every perceptible form of the subject — i.e. the
    candidate asserting nouns/terms the subject does not contain (the over-build signal). Excludes
    common English words (which carry no claim) so the flag means something."""
    corpus = _salient(" ".join(subject_views.values()))
    return {t for t in _salient(candidate) if t not in corpus and t not in _STOP}


def grounding_penalty(candidate: str, subject_views: dict[str, str]) -> float:
    """0.0 (fully grounded) → up to ~0.6 penalty as unsupported salient tokens accumulate.
    Subtract from the candidate's `grounded` score; record the offenders as evidence."""
    bad = unsupported_tokens(candidate, subject_views)
    return min(0.6, 0.15 * len(bad))
